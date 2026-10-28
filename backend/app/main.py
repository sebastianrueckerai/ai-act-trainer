import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from datetime import timedelta

import structlog
from fastapi import FastAPI

from app.api import auth, chat, health, me, personas, theme, version
from app.api.static import mount_frontend
from app.api.version import law_version
from app.auth.factory import build_identity, build_session_cookie
from app.content.lint import lint, lint_persona_images
from app.content.loader import load_content
from app.content.manifest import load_manifest
from app.corpus.build import load_library
from app.corpus.search import SearchIndex
from app.files.router import router as files_router
from app.graph.checkpointer import open_checkpointer
from app.graph.deps import CompletionRecord, GraphDeps
from app.graph.graph import build_graph
from app.llm.budget import ProxyClient
from app.llm.models import CallerModels
from app.logging import configure_logging
from app.settings import Settings, get_settings
from app.storage.db import make_engine, make_session_factory
from app.storage.migrate import run_migrations
from app.storage.models import utcnow
from app.storage.repository import SqlAlchemyRepository
from app.version import APP_VERSION

log = structlog.get_logger()


def _record_completion(session_factory) -> Callable[[CompletionRecord], None]:
    def record(completion: CompletionRecord) -> None:
        with session_factory() as session:
            SqlAlchemyRepository(session).record_completion(
                user_id=completion.user_id,
                course_version=completion.course_version,
                law_version=completion.law_version,
                locale=completion.locale,
                persona_id=completion.persona_id,
                passed_at=completion.passed_at,
            )
            session.commit()

    return record


async def _delete_threads(app: FastAPI, threads: list[str]) -> None:
    for thread_id in threads:
        await app.state.graph.checkpointer.adelete_thread(thread_id)
        app.state.thread_locks.pop(thread_id, None)
        app.state.translating_failed.pop(thread_id, None)


async def clean_guests(app: FastAPI) -> int:
    """Delete every guest idle past the retention, their rows and their threads."""
    before = utcnow() - timedelta(hours=app.state.settings.guest_retention_hours)
    with app.state.session_factory() as session:
        repo = SqlAlchemyRepository(session)
        idle = repo.idle_guests(before)
        for uid in idle:
            await _delete_threads(app, repo.delete_user_rows(uid))
    return len(idle)


async def purge_transcripts(app: FastAPI) -> int:
    """Named users idle past the retention lose their threads and turn rows; the
    account and its pass records stay."""
    before = utcnow() - timedelta(days=app.state.settings.retention_days)
    with app.state.session_factory() as session:
        repo = SqlAlchemyRepository(session)
        idle = repo.idle_named_users(before)
        for uid in idle:
            await _delete_threads(app, repo.delete_transcript_rows(uid))
    return len(idle)


async def _clean_hourly(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(3600)
        try:
            log.info(
                "stale data cleaned",
                guests=await clean_guests(app),
                transcripts=await purge_transcripts(app),
            )
        except Exception as error:
            log.warning("cleaning failed", error=str(error), exc_info=True)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.run_migrations:
            run_migrations(settings.database_url)
        app.state.engine = make_engine(settings.database_url)
        app.state.session_factory = make_session_factory(app.state.engine)
        app.state.manifest = load_manifest(settings.content_dir)
        app.state.library = load_library(settings.corpus_dir)
        app.state.search = SearchIndex.build(app.state.library)
        app.state.content = load_content(
            settings.content_dir, settings.personas_dir, settings.content_overlay_dir
        )
        problems = lint(app.state.content, app.state.library)
        if problems:
            raise RuntimeError(
                "content lint failed: " + "; ".join(f"{p.where}: {p.message}" for p in problems)
            )
        missing_images = lint_persona_images(
            app.state.content.personas.values(), settings.personas_dir
        )
        if missing_images:
            raise RuntimeError("persona images missing: " + ", ".join(missing_images))
        app.state.budget = (
            ProxyClient(settings.llm_base_url, settings.litellm_admin_key)
            if settings.litellm_admin_key
            else None
        )
        async with open_checkpointer(settings) as checkpointer:
            deps = GraphDeps(
                library=app.state.library,
                content=app.state.content,
                search=app.state.search,
                models=CallerModels(settings),
                settings=settings,
                law_version=law_version(app.state.library, app.state.manifest.law.amended_by).celex,
                record_completion=_record_completion(app.state.session_factory),
            )
            app.state.deps = deps
            app.state.graph = build_graph(deps, checkpointer)
            app.state.ready = True
            log.info("startup complete", course=app.state.manifest.course_version, env=settings.env)
            cleaner = asyncio.create_task(_clean_hourly(app))
            yield
            cleaner.cancel()
            with suppress(asyncio.CancelledError):
                await cleaner
            app.state.ready = False
        if app.state.budget is not None:
            app.state.budget.close()
        app.state.engine.dispose()

    # The API surface is not for anonymous visitors in production.
    private = settings.is_production
    app = FastAPI(
        title="AI Act Trainer",
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url=None if private else "/docs",
        redoc_url=None if private else "/redoc",
        openapi_url=None if private else "/openapi.json",
    )
    app.state.settings = settings
    # One lock per thread serialises a turn, a flag flip and the history translations
    # landing behind it; `translating` holds the one running translation task per thread.
    app.state.thread_locks = defaultdict(asyncio.Lock)
    app.state.translating = {}
    # Per thread, the message ids whose rendering failed since the last flip.
    app.state.translating_failed = {}
    app.state.ready = False
    app.state.session_cookie = build_session_cookie(settings)
    identity = build_identity(settings, app.state.session_cookie)
    app.include_router(identity.router(), prefix="/api")
    app.include_router(auth.router, prefix="/api")
    if settings.guest_access:
        app.include_router(auth.guest_router, prefix="/api")
    app.include_router(me.router, prefix="/api")
    app.include_router(health.router, prefix="/api")
    app.include_router(version.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(theme.router)
    app.include_router(personas.router)
    app.include_router(files_router)
    mount_frontend(app, settings.frontend_dist)
    return app
