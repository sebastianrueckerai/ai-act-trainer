import time
from collections.abc import Callable
from dataclasses import dataclass, field

import structlog

from app.graph.critic import Critique
from app.graph.state import SessionState
from app.settings import Settings

log = structlog.get_logger(__name__)

RETRIES = 2


@dataclass
class Governed:
    """What the loop ships: the text, whether a critic passed it, and the faults it still
    carried when the budget ran out."""

    text: str
    shipped: bool
    faults: list[str] = field(default_factory=list)


def deadline(state: SessionState, settings: Settings) -> float:
    return state["turn"].started_at + settings.turn_budget_seconds


def govern(
    stage: str,
    produce: Callable[[str | None, str | None], str],
    judge: Callable[[str], Critique],
    deadline: float,
    announce: Callable[[str], None] | None = None,
) -> Governed:
    """Produce a draft, have it judged, and send it back with the notes until a critic
    ships it. After RETRIES retries or past the deadline the best-scored draft ships.
    announce, when given, is told the step that starts: writing, then checking, then
    rewriting and checking again on a retry."""
    previous: str | None = None
    notes: str | None = None
    best: tuple[int, str, list[str]] | None = None
    drafts = 0
    error = ""
    for _ in range(RETRIES + 1):
        try:
            if announce is not None:
                announce("writing" if previous is None else "rewriting")
            draft = produce(previous, notes)
            drafts += 1
            if announce is not None:
                announce("checking")
            critique = judge(draft)
        except Exception as failure:
            # A failed retry is the budget spent: the draft in hand ships, as on the clock.
            # A failure before any draft is the turn's failure.
            if best is None:
                raise
            error = f"{type(failure).__name__}: {failure}"
            break
        if critique.verdict == "ship":
            return Governed(text=draft, shipped=True)
        if best is None or critique.score >= best[0]:
            best = (critique.score, draft, list(critique.faults))
        if time.monotonic() >= deadline:
            break
        previous, notes = draft, critique.notes
    score, text, faults = best
    log.info("critic_budget", stage=stage, faults=faults, score=score, drafts=drafts, error=error)
    return Governed(text=text, shipped=False, faults=faults)
