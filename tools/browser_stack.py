"""Serve the real app to the browser suite with scripted models.

The graph, the API, the content and the built frontend are the production ones.
Only the two chat models are replaced, so a click path runs end to end without a
proxy, a key or a model that answers differently twice:

    cd backend && uv run python ../tools/browser_stack.py --port 4173

The script the models follow is the turn order frontend/e2e/chat.spec.ts drives:
the start of the test, the "Ja" that confirms it, and one answer to its first
question. The chip that answers the first step's own question takes no model call
(D130).

With BROWSER_STACK_BUDGET=exhausted the stack is the public demo with its money spent:
the guest door is open, budgets are on, and a fake proxy reports the guest pool's day
budget used up until two hours after start.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import uvicorn
from fastapi import FastAPI

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from app.graph.critic import Critique  # noqa: E402
from app.graph.deps import GraphDeps  # noqa: E402
from app.graph.grade import Verdict  # noqa: E402
from app.graph.graph import build_graph  # noqa: E402
from app.graph.triage import Triage  # noqa: E402
from app.main import create_app  # noqa: E402
from app.settings import Settings  # noqa: E402
from app.storage.repository import SqlAlchemyRepository  # noqa: E402
from tests.fakes.proxy import ADMIN_KEY, BASE_URL, FakeProxy  # noqa: E402
from tests.fakes.scripted import ScriptedChatModel  # noqa: E402

EXHAUSTED = os.environ.get("BROWSER_STACK_BUDGET") == "exhausted"

# The persona echoes the draft and the critics ship it, so the student reads the curated
# German text: one fixed screen per step.
SCRIPT = {
    "triage": [
        # The nod that opens the step's own case runs through /continue (D85, D96), and the
        # chip that answers it is the answer itself (D130): neither takes a triage call.
        Triage(guard="ok", intent="start_test"),
        # The "Ja" that confirms the test start is its own turn: triage runs on
        # it too, though pending_start_test makes the intent it returns moot.
        Triage(guard="ok", intent="continue"),
        Triage(guard="ok", intent="choose"),
    ],
    "grade": Verdict(correct=True),
    "reply": "Genau, das darfst du.",
    "persona": "<echo>",
    "critic": Critique(verdict="ship", score=5),
    "voice_critic": Critique(verdict="ship", score=5),
    # Only reached once a test flips the display-locale flag; a fixed reply
    # keeps that turn from crashing without needing to know its exact fields.
    "translate": "This step, in English.",
    "translate_fields": "1: Continue",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=4173)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dist = REPO_ROOT / "frontend" / "dist"
    if not (dist / "index.html").is_file():
        raise SystemExit(f"no built frontend at {dist}: run `pnpm build` first")

    # A throwaway database that leaves with the process; earlier runs left 35 of these in /tmp.
    with tempfile.TemporaryDirectory(prefix="browser-stack-") as scratch:
        serve(args, dist, Path(scratch) / "browser.db")


def spend_the_pool(app: FastAPI) -> None:
    """The guest pool as `tools/account.py pool` leaves it, its day spent."""
    proxy = FakeProxy()
    key = proxy.add("pool-demo", day=2.0, month=6.0)
    reset = datetime.now(UTC) + timedelta(hours=2)
    proxy.keys[key].update(spend=2.0, budget_reset_at=reset.isoformat())
    app.state.budget.close()
    app.state.budget = proxy.client()
    with app.state.session_factory() as db:
        SqlAlchemyRepository(db).add_account(
            "pool-demo", "pool", "Demo-Pool", key, "pool-demo", None, 2.0, 6.0
        )


def serve(args: argparse.Namespace, dist: Path, database: Path) -> None:
    budgets = (
        {"guest_access": True, "litellm_admin_key": ADMIN_KEY, "llm_base_url": BASE_URL}
        if EXHAUSTED
        else {}
    )
    settings = Settings(
        _env_file=None,
        env="development",
        database_url=f"sqlite:///{database}",
        content_dir=REPO_ROOT / "content",
        personas_dir=REPO_ROOT / "personas",
        corpus_dir=REPO_ROOT / "corpus",
        frontend_dist=dist,
        **budgets,
    )
    app = create_app(settings)
    started = app.router.lifespan_context

    @asynccontextmanager
    async def scripted(running: FastAPI) -> AsyncIterator[None]:
        async with started(running):
            model = ScriptedChatModel(script=SCRIPT)
            running.state.deps = GraphDeps(
                library=running.state.library,
                content=running.state.content,
                search=running.state.search,
                models={"strong": model, "fast": model},
                settings=running.state.settings,
                law_version="browser",
            )
            running.state.graph = build_graph(running.state.deps, InMemorySaver())
            if EXHAUSTED:
                spend_the_pool(running)
            yield

    app.router.lifespan_context = scripted
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
