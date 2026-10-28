from typing import Any

from app.api.chat_events import part_out
from app.graph.state import TurnScratch


def ui_events(turn: TurnScratch) -> list[dict[str, Any]]:
    return [
        {"type": "ui", "name": event.name, "payload": dict(event.payload)}
        for event in turn.ui_events
    ]


def settle_out(parts: list[dict[str, Any]], hint: dict[str, Any]) -> list[dict[str, Any]]:
    """The settle events of one rendering: each part in its display form, then the hint.
    A part event carries what the page shows, so nothing is re-localised on the way out."""
    events: list[dict[str, Any]] = [{"type": "part", "out": part} for part in parts]
    events.append({"type": "input_hint", "hint": hint})
    return events


def settle_events(turn: TurnScratch) -> list[dict[str, Any]]:
    return settle_out(
        [part_out(part).model_dump(mode="json") for part in turn.parts],
        turn.input_hint.model_dump(mode="json"),
    )
