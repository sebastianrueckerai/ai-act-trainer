"""What the page shows beside the typing dots: the step that runs now, in the
character's words."""

import random
from collections.abc import Callable
from typing import Any

from langgraph.config import get_stream_writer

from app.content.models import WORKING_STEPS
from app.graph.deps import GraphDeps
from app.graph.state import SessionState
from app.i18n import t

Writer = Callable[[dict[str, Any]], None]


def working_line(
    deps: GraphDeps,
    persona_id: str | None,
    locale: str,
    step: str,
    pick: Callable[[list[str]], str] = random.choice,
) -> str:
    if step not in WORKING_STEPS:
        raise ValueError(f"unknown working step {step!r}")
    persona = deps.persona(persona_id) if persona_id else None
    lines = persona.working.get(step, []) if persona else []
    return pick(lines) if lines else t(locale, f"working_{step}")


def announce(deps: GraphDeps, state: SessionState, step: str, writer: Writer | None = None) -> None:
    """Tell the page which step runs now. Outside a graph run there is no stream and
    nothing is said."""
    if writer is None:
        try:
            writer = get_stream_writer()
        except RuntimeError:
            return
    text = working_line(deps, state.get("persona_id"), state.get("locale", "de"), step)
    writer({"type": "working", "step": step, "text": text})
