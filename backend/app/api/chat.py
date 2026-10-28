import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from random import choice
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.errors import InvalidUpdateError
from langgraph.graph.state import CompiledStateGraph
from pydantic import TypeAdapter, ValidationError

from app.api.chat_events import (
    ChatEvent,
    ErrorEvent,
    InputHintEvent,
    MessageEvent,
    PartEvent,
    PartOut,
    StatusEvent,
    TokenEvent,
    UiPayloadEvent,
    WorkingEvent,
    format_sse,
)
from app.api.deps import current_principal, get_repository, user_id
from app.api.models import (
    ChatMessageOut,
    DisplayLocaleRequest,
    SessionRequest,
    SessionResponse,
    TurnRequest,
)
from app.auth.identity import Principal, is_guest
from app.graph.stage import build_stage
from app.graph.state import (
    Guard,
    InputHint,
    Intent,
    Mood,
    TurnScratch,
    initial_state,
)
from app.graph.translate import chapter_titles_en, parts_from_dumps, render_en, translate_text
from app.llm.budget import GLOBAL, SEATS, BudgetState, caller_state, is_budget_error
from app.llm.models import caller_key
from app.settings import Settings
from app.storage.models import TrainingSession
from app.storage.repository import Repository

router = APIRouter(tags=["chat"])

log = structlog.get_logger(__name__)

# A guest with a turn this recent holds a seat.
GUEST_ACTIVE = timedelta(minutes=10)


@dataclass(frozen=True)
class _Caller:
    """Whose money a request spends: the key its model calls carry and, with budgets on,
    the proxy user whose month that key counts against. No key: the caller is refused."""

    guest: bool
    key: str | None
    proxy_user: str | None = None


def _bind_caller(request: Request, repo: Repository, principal: Principal) -> _Caller:
    """The caller's key, bound for every model call this request makes: an account's own,
    the pool's for a guest, the deployment's when budgets are off."""
    settings: Settings = request.app.state.settings
    guest = is_guest(principal)
    if not settings.litellm_admin_key:
        caller = _Caller(guest, settings.llm_api_key)
    else:
        account = repo.pool_account() if guest else repo.account_by_subject(principal.subject)
        if account is None or account.revoked_at is not None:
            caller = _Caller(guest, None)
        else:
            caller = _Caller(guest, account.litellm_key, account.litellm_user_id)
    if caller.key is not None:
        caller_key.set(caller.key)
    return caller


async def _budget(request: Request, caller: _Caller, fresh: bool = False) -> BudgetState:
    """The caller's budget as the proxy keeps it. A read that fails shows ok: the proxy
    still refuses what it must, and the turn then says so."""
    if caller.key is None:
        return GLOBAL
    if caller.proxy_user is None:
        return BudgetState()
    try:
        return await asyncio.to_thread(
            caller_state,
            request.app.state.budget,
            caller.key,
            caller.proxy_user,
            caller.guest,
            fresh,
        )
    except (httpx.HTTPError, KeyError, ValueError) as error:
        log.warning("budget read failed", error=str(error))
        return BudgetState()


async def seed_thread(
    request: Request,
    graph: CompiledStateGraph,
    config: dict,
    user_id: int,
    persona_id: str,
    display_locale: str = "de",
) -> None:
    state = await graph.aget_state(config)
    if not state.values:
        try:
            persona = request.app.state.content.personas.get(persona_id)
            await graph.aupdate_state(
                config,
                initial_state(persona_id=persona_id, user_id=user_id, display_locale=display_locale)
                | {
                    "opening_line": choice(persona.openings)
                    if persona is not None and persona.openings
                    else ""
                },
            )
        except InvalidUpdateError:
            # A concurrent bootstrap seeded this thread between the read and the write.
            state = await graph.aget_state(config)
            if not state.values:
                raise


_PART = TypeAdapter(PartOut)


def _readable(parts: list[Any]) -> list[PartOut]:
    """The parts of a stored turn that this build can still render.

    A part is written once and read for as long as its thread lives, so one whose shape has
    moved on since would fail the response model and take the whole thread down with it. It
    is dropped instead: an old turn loses a card, not the student their course.
    """
    kept = []
    for part in parts:
        try:
            kept.append(_PART.validate_python(part))
        except ValidationError as error:
            log.info("part_unreadable", error=str(error).splitlines()[0])
    return kept


def _hint_from(dump: dict[str, Any] | None) -> InputHint | None:
    return InputHint.model_validate(dump) if dump else None


def _message_out(
    message: AnyMessage, locale: str, failed: frozenset[str] = frozenset()
) -> ChatMessageOut:
    """One message as the page shows it: the German record, or its English rendering
    under `en`, or the German marked `translating` while the rendering is on its way.
    A message whose rendering failed this round shows its German unmarked, readable."""
    kwargs = message.additional_kwargs
    if message.type != "ai":
        return ChatMessageOut(
            id=message.id, role="user", text=kwargs.get("shown") or str(message.content)
        )
    rendering = kwargs.get("en")
    if locale == "en" and rendering is not None:
        return ChatMessageOut(
            id=message.id,
            role="assistant",
            text=rendering["text"],
            parts=_readable(rendering["parts"]),
            hint=_hint_from(rendering["hint"]),
        )
    return ChatMessageOut(
        id=message.id,
        role="assistant",
        text=str(message.content),
        parts=_readable(kwargs.get("parts", [])),
        hint=_hint_from(kwargs.get("hint")),
        translating=locale == "en" and message.id not in failed,
    )


def _failed(app: FastAPI, config: dict[str, Any]) -> set[str]:
    """The ids whose rendering failed since the thread's last flip."""
    return app.state.translating_failed.setdefault(config["configurable"]["thread_id"], set())


async def _titles_en(request: Request, values: dict[str, Any]) -> dict[str, str] | None:
    """The English chapter titles for an English session's stage, rendered once per process
    off the event loop; German when the rendering fails."""
    if values.get("display_locale", "de") != "en":
        return None
    return await asyncio.to_thread(chapter_titles_en, request.app.state.deps)


def _current_hint(messages: list[ChatMessageOut], turn: TurnScratch | None) -> InputHint:
    """The hint the composer offers: the last tutor message's, in the display locale, else
    the turn's German one (a thread from before hints were stored on messages)."""
    last = next((m for m in reversed(messages) if m.role == "assistant"), None)
    if last is not None and last.hint is not None:
        return last.hint
    return turn.input_hint if turn is not None else InputHint(kind="text")


def _session_response(
    request: Request,
    training_session: TrainingSession,
    config: dict[str, Any],
    values: dict[str, Any],
    titles_en: dict[str, str] | None,
    budget: BudgetState,
) -> SessionResponse:
    locale = values.get("display_locale", "de")
    turn = values.get("turn")
    failed = frozenset(_failed(request.app, config))
    messages = [_message_out(m, locale, failed) for m in values.get("messages", [])]
    return SessionResponse(
        id=training_session.id,
        persona_id=values.get("persona_id", ""),
        phase=values.get("phase", "lesson"),
        display_locale=locale,
        hint=_current_hint(messages, turn),
        messages=messages,
        stage=build_stage(
            request.app.state.content,
            request.app.state.settings.personas_dir,
            values,
            titles_en=titles_en,
        ),
        budget=budget,
    )


# Async for the graph's async API; the repository calls are quick single-row queries.
@router.get("/session", response_model=SessionResponse)
async def get_active_session(
    request: Request,
    principal: Principal = Depends(current_principal),
    repo: Repository = Depends(get_repository),
) -> SessionResponse:
    uid = user_id(principal, repo)
    training_session = repo.active_session(uid)
    if training_session is None:
        raise HTTPException(status_code=404, detail="no active session")
    config = {"configurable": {"thread_id": training_session.thread_id}}
    values = (await request.app.state.graph.aget_state(config)).values
    if not values:
        raise HTTPException(status_code=404, detail="no active session")
    caller = _bind_caller(request, repo, principal)
    _ensure_translated(request, config, values)
    titles = await _titles_en(request, values)
    budget = await _budget(request, caller)
    return _session_response(request, training_session, config, values, titles, budget)


@router.post("/session", response_model=SessionResponse)
async def post_session(
    body: SessionRequest,
    request: Request,
    principal: Principal = Depends(current_principal),
    repo: Repository = Depends(get_repository),
) -> SessionResponse:
    if body.persona_id not in request.app.state.content.personas:
        raise HTTPException(status_code=422, detail="unknown persona")
    uid = user_id(principal, repo)
    training_session = repo.get_or_create_session(uid)
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": training_session.thread_id}}
    await seed_thread(request, graph, config, uid, body.persona_id, body.display_locale)
    values = (await graph.aget_state(config)).values
    caller = _bind_caller(request, repo, principal)
    titles = await _titles_en(request, values)
    budget = await _budget(request, caller)
    return _session_response(request, training_session, config, values, titles, budget)


@router.put("/session/{session_id}/display-locale", response_model=SessionResponse)
async def set_display_locale(
    session_id: int,
    body: DisplayLocaleRequest,
    request: Request,
    principal: Principal = Depends(current_principal),
    repo: Repository = Depends(get_repository),
) -> SessionResponse:
    config, training_session, _ = await _live_thread(session_id, request, principal, repo)
    caller = _bind_caller(request, repo, principal)
    graph = request.app.state.graph
    # A turn in flight holds the lock: the flip lands after it, not under it.
    async with _thread_lock(request, config):
        await graph.aupdate_state(
            config, {"display_locale": body.display_locale}, as_node="__start__"
        )
        values = (await graph.aget_state(config)).values
    # A flip is a fresh try for every rendering that failed before it.
    _failed(request.app, config).clear()
    _ensure_translated(request, config, values)
    titles = await _titles_en(request, values)
    budget = await _budget(request, caller)
    return _session_response(request, training_session, config, values, titles, budget)


def _thread_lock(request: Request, config: dict[str, Any]) -> asyncio.Lock:
    """One lock per thread. A turn, a flag flip and a translation landing all write the
    same checkpoint chain, and without it the last writer silently wins over the others."""
    return request.app.state.thread_locks[config["configurable"]["thread_id"]]


def _untranslated(values: dict[str, Any], failed: set[str]) -> list[AIMessage]:
    return [
        m
        for m in values.get("messages", [])
        if isinstance(m, AIMessage) and "en" not in m.additional_kwargs and m.id not in failed
    ]


def _ensure_translated(request: Request, config: dict[str, Any], values: dict[str, Any]) -> None:
    """Every German turn gets an English rendering, once, in the background: the flip
    answers at once, the thread follows as each rendering lands, and a later flip finds
    them cached in the thread. A rendering that failed waits for the next flip."""
    if values.get("display_locale", "de") != "en":
        return
    if not _untranslated(values, _failed(request.app, config)):
        return
    thread_id = config["configurable"]["thread_id"]
    running: dict[str, asyncio.Task] = request.app.state.translating
    if thread_id in running:
        return
    running[thread_id] = asyncio.create_task(_translate_history(request.app, config))
    running[thread_id].add_done_callback(lambda _: running.pop(thread_id, None))


async def _translate_history(app: FastAPI, config: dict[str, Any]) -> None:
    graph = app.state.graph
    model = app.state.deps.models["fast"]
    lock = app.state.thread_locks[config["configurable"]["thread_id"]]
    failed = _failed(app, config)
    async with lock:
        pending = _untranslated((await graph.aget_state(config)).values, failed)
    at_once = asyncio.Semaphore(3)

    async def one(m: AIMessage) -> None:
        kwargs = m.additional_kwargs
        try:
            async with at_once:
                rendering = await asyncio.to_thread(
                    render_en,
                    model,
                    str(m.content),
                    parts_from_dumps(kwargs.get("parts", [])),
                    _hint_from(kwargs.get("hint")),
                )
        except Exception as error:
            failed.add(m.id)
            log.warning("history rendering failed", message_id=m.id, error=str(error))
            return
        translated = AIMessage(
            id=m.id, content=m.content, additional_kwargs={**kwargs, "en": rendering}
        )
        async with lock:
            # The thread moved on while this rendered: a turn may have compacted the
            # message away, and writing it back would append it at the end.
            current = (await graph.aget_state(config)).values.get("messages", [])
            if any(c.id == m.id and "en" not in c.additional_kwargs for c in current):
                await graph.aupdate_state(config, {"messages": [translated]})

    # Newest first: the student is reading the end of the thread.
    await asyncio.gather(*(one(m) for m in reversed(pending)))


@router.post("/session/close", status_code=204)
async def close_session(
    principal: Principal = Depends(current_principal),
    repo: Repository = Depends(get_repository),
) -> None:
    uid = user_id(principal, repo)
    training_session = repo.active_session(uid)
    if training_session is None:
        raise HTTPException(status_code=404, detail="no active session")
    repo.close_session(training_session.id, "abandoned")


def _stream(
    request: Request,
    config: dict,
    graph_input: Any,
    caller: _Caller,
    seed: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    """The turn, under the thread's lock from its seed to its last frame. `seed` is a
    state written as the triage node first, which resumes the graph below it (D40)."""
    graph: CompiledStateGraph = request.app.state.graph
    lock = _thread_lock(request, config)
    failed = frozenset(_failed(request.app, config))

    async def events() -> AsyncIterator[str]:
        try:
            async with lock:
                if seed is not None:
                    await graph.aupdate_state(config, seed, as_node="triage")
                async for mode, chunk in graph.astream(
                    graph_input, config, stream_mode=["updates", "custom"]
                ):
                    if mode == "updates":
                        for node in chunk:
                            yield format_sse(StatusEvent(node=node))
                    elif mode == "custom":
                        # The nodes stream what the turn settles into: a token is the
                        # final text, so nothing the student read ever changes later.
                        if chunk["type"] == "token":
                            yield format_sse(TokenEvent(text=chunk["text"]))
                        elif chunk["type"] == "working":
                            yield format_sse(WorkingEvent(step=chunk["step"], text=chunk["text"]))
                        elif chunk["type"] == "ui":
                            yield format_sse(
                                UiPayloadEvent(name=chunk["name"], payload=chunk["payload"])
                            )
                        elif chunk["type"] == "part":
                            yield format_sse(PartEvent(part=_PART.validate_python(chunk["out"])))
                        elif chunk["type"] == "input_hint":
                            yield format_sse(
                                InputHintEvent(hint=InputHint.model_validate(chunk["hint"]))
                            )
                values = (await graph.aget_state(config)).values
            turn = values.get("turn")
            # The locale as it stands now: a flip that waited on the lock has landed, and
            # the turn that ran in German settles marked, so the page asks for its rendering.
            locale = values.get("display_locale", "de")
            outs = [_message_out(m, locale, failed) for m in values.get("messages", [])]
            last = next((m for m in reversed(outs) if m.role == "assistant"), None)
            yield format_sse(
                MessageEvent(
                    id=last.id if last else None,
                    text=last.text if last else "",
                    parts=last.parts if last else [],
                    hint=_current_hint(outs, turn),
                    translating=last.translating if last else False,
                )
            )
        except Exception as error:
            if is_budget_error(error):
                # Spend the proxy can read is the caller's own budget; anything else that
                # refuses is the proxy-wide cap.
                state = await _budget(request, caller, fresh=True)
                state = state if state.state == "exhausted" else GLOBAL
                log.warning("budget_hit", scope=state.scope)
                yield format_sse(ErrorEvent(code="limit", message="chat.limit", budget=state))
                return
            detail = str(error) or error.__class__.__name__
            log.warning("turn failed", error=detail, exc_info=True)
            yield format_sse(ErrorEvent(code="turn_failed", message="chat.error"))

    return events()


def _sse_response(stream: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _live_thread(
    session_id: int, request: Request, principal: Principal, repo: Repository
) -> tuple[dict, TrainingSession, dict[str, Any]]:
    uid = user_id(principal, repo)
    training_session = repo.get_session(session_id, uid)
    if training_session is None:
        raise HTTPException(status_code=404, detail="session not found")
    config = {"configurable": {"thread_id": training_session.thread_id}}
    values = (await request.app.state.graph.aget_state(config)).values
    if not values:
        raise HTTPException(status_code=409, detail="session not started")
    return config, training_session, values


def _refusal(
    settings: Settings, repo: Repository, principal: Principal, caller: _Caller
) -> BudgetState | None:
    """The gates before a streamed turn, none of them a model call: a caller without a key,
    every guest seat taken, and the spend guard, where every streamed turn is metered and a
    rolling day closes at the global or the caller's own cap, whichever comes first."""
    uid = user_id(principal, repo)
    if caller.key is None:
        log.warning("caller_without_key", user_id=uid)
        return GLOBAL
    now = datetime.now(UTC)
    if caller.guest:
        active = repo.active_guest_ids(now - GUEST_ACTIVE)
        if len(active) >= settings.guest_seats and uid not in active:
            log.warning("guest_seats_full", seats=len(active), user_id=uid)
            return SEATS
    since = now - timedelta(days=1)
    own_cap = settings.turn_limit_guest_day if caller.guest else settings.turn_limit_user_day
    if (
        repo.turns_since(since) >= settings.turn_limit_global_day
        or repo.turns_since(since, uid) >= own_cap
    ):
        log.warning("turn_limit_hit", global_turns=repo.turns_since(since), user_id=uid)
        return GLOBAL
    repo.log_turn(uid)
    return None


def _sse_limit(state: BudgetState) -> StreamingResponse:
    async def _refused():
        yield format_sse(ErrorEvent(code="limit", message="chat.limit", budget=state))

    return _sse_response(_refused())


_SSE_RESPONSES = {
    200: {"model": ChatEvent, "description": "Server-sent events; each data line is one ChatEvent"}
}


@router.post("/chat/{session_id}/opening", responses=_SSE_RESPONSES)
async def post_opening(
    session_id: int,
    request: Request,
    principal: Principal = Depends(current_principal),
    repo: Repository = Depends(get_repository),
) -> StreamingResponse:
    config, _, values = await _live_thread(session_id, request, principal, repo)
    if values.get("messages"):
        raise HTTPException(status_code=409, detail="session already opened")
    caller = _bind_caller(request, repo, principal)
    refused = _refusal(request.app.state.settings, repo, principal, caller)
    if refused is not None:
        return _sse_limit(refused)
    # The first lesson step belongs to the tutor: a fresh scratch seeded as triage
    # means the step arrives in the persona's voice with no student message and no
    # triage call.
    # The canned greeting leaves before the graph runs: the student reads the
    # character at once while the real first turn generates behind it. It waits a
    # beat first: a greeting at the first millisecond reads as a system message, not
    # a character typing. An English session renders the greeting during that beat
    # and seeds the rendering, so the translate node stores the first message with
    # this line, once.
    greeting = values.get("opening_line", "")
    english = values.get("display_locale", "de") == "en"
    seed: dict[str, Any] = {"turn": TurnScratch()}
    model = request.app.state.deps.models["fast"]

    async def _render_greeting() -> str:
        # Best effort: a greeting the model cannot render greets in German once, and the
        # translate node renders the whole first message instead.
        try:
            return await asyncio.to_thread(translate_text, model, greeting)
        except Exception as error:
            log.warning("greeting rendering failed", error=str(error))
            return ""

    async def _opened():
        if greeting:
            shown = greeting
            if english:
                _, rendered = await asyncio.gather(asyncio.sleep(0.7), _render_greeting())
                if rendered:
                    seed["opening_line_en"] = rendered
                    shown = rendered
            else:
                await asyncio.sleep(0.7)
            yield format_sse(TokenEvent(text=f"{shown}\n\n"))
        async for frame in _stream(request, config, None, caller, seed=seed):
            yield frame

    return _sse_response(_opened())


@router.post("/chat/{session_id}/continue", responses=_SSE_RESPONSES)
async def post_continue(
    session_id: int,
    request: Request,
    principal: Principal = Depends(current_principal),
    repo: Repository = Depends(get_repository),
) -> StreamingResponse:
    config, _, values = await _live_thread(session_id, request, principal, repo)
    if not values.get("messages"):
        raise HTTPException(status_code=409, detail="session not opened")
    last_hint = values.get("last_hint")
    if last_hint is None or last_hint.kind != "confirm":
        raise HTTPException(status_code=409, detail="not a confirm turn")
    caller = _bind_caller(request, repo, principal)
    refused = _refusal(request.app.state.settings, repo, principal, caller)
    if refused is not None:
        return _sse_limit(refused)
    # The Weiter click carries no new content, so it needs no triage call: seeding the
    # triage decision, as post_opening does, resumes the graph exactly where a typed
    # "weiter" message would, with no student message added.
    seed = {"turn": TurnScratch(guard=Guard.ok, intent=Intent.continue_), "mood": Mood.neutral}
    return _sse_response(_stream(request, config, None, caller, seed=seed))


@router.post("/chat/{session_id}/turns", responses=_SSE_RESPONSES)
async def post_turn(
    session_id: int,
    body: TurnRequest,
    request: Request,
    principal: Principal = Depends(current_principal),
    repo: Repository = Depends(get_repository),
) -> StreamingResponse:
    config, _, _ = await _live_thread(session_id, request, principal, repo)
    caller = _bind_caller(request, repo, principal)
    refused = _refusal(request.app.state.settings, repo, principal, caller)
    if refused is not None:
        return _sse_limit(refused)
    said = HumanMessage(body.text, additional_kwargs={"shown": body.shown} if body.shown else {})
    return _sse_response(_stream(request, config, {"messages": [said]}, caller))
