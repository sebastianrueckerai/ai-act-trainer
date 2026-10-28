from __future__ import annotations

from pathlib import Path
from typing import Any

from app.content.loader import ContentBundle
from app.content.models import Chapter
from app.graph.state import TestState

SCENE = "scene"
SCENE_LIGHT = "scene-light"


def persona_image_url(personas_dir: Path, persona_id: str, image: str) -> str | None:
    """The route that serves one persona image, or None when it was never drawn."""
    if (personas_dir / persona_id / "images" / f"{image}.png").is_file():
        return f"/api/personas/{persona_id}/images/{image}"
    return None


def _persona_block(
    content: ContentBundle, personas_dir: Path, persona_id: str, locale: str, mood: str
) -> dict[str, Any] | None:
    manifest = content.personas.get(persona_id)
    if manifest is None:
        return None
    name = manifest.name.get(locale) or manifest.name["de"]
    return {
        "id": manifest.id,
        "name": name,
        "image_url": persona_image_url(personas_dir, manifest.id, mood)
        or persona_image_url(personas_dir, manifest.id, "neutral"),
        "neutral_image_url": persona_image_url(personas_dir, manifest.id, "neutral"),
        "scene_url": persona_image_url(personas_dir, manifest.id, SCENE),
        "scene_light_url": persona_image_url(personas_dir, manifest.id, SCENE_LIGHT),
    }


def _attempt_block(attempt: TestState) -> dict[str, Any]:
    return {
        "kind": "practice" if attempt.practice else "test",
        "index": attempt.index,
        "results": [answer.correct for answer in attempt.answers],
        "total": len(attempt.question_ids),
    }


def _steps_done(values: dict[str, Any], steps: int) -> int:
    """Teaching a step moves step_idx past it, but it counts only once its case is settled."""
    taught = values.get("step_idx", 0)
    open_case = values.get("pending_case") is not None or values.get("practice") is not None
    return min(max(taught - 1 if open_case else taught, 0), steps)


def _chapter_block(
    chapter: Chapter, title: str, state: str, values: dict[str, Any]
) -> dict[str, Any]:
    steps = len(chapter.steps)
    return {
        "id": chapter.id,
        "title": title,
        "stub": chapter.stub,
        "state": state,
        "steps": steps,
        "step": _steps_done(values, steps) if state == "current" else None,
    }


def build_stage(
    content: ContentBundle,
    personas_dir: Path,
    values: dict[str, Any],
    titles_en: dict[str, str] | None = None,
) -> dict[str, Any]:
    """The stage as the page shows it. `titles_en` is the chapter titles' English rendering,
    used only under the `en` display locale."""
    locale = values.get("locale", "de")
    chapters = content.locales[locale].chapters
    done = set(values.get("chapters_done", []))
    chapter_idx = values.get("chapter_idx", 0)
    persona_id = values.get("persona_id")
    mood = values.get("mood", "neutral")
    # A live practice attempt lives under "practice"; "test" holds the real test.
    attempt = values.get("practice") or values.get("test")

    shown = values.get("display_locale", locale)
    titles = titles_en if shown == "en" and titles_en else {}
    return {
        "persona": (
            _persona_block(content, personas_dir, persona_id, shown, mood) if persona_id else None
        ),
        "mood": mood,
        "streak": values.get("streak", 0),
        "chapters": [
            _chapter_block(
                chapter,
                titles.get(chapter.id, chapter.title),
                "done" if chapter.id in done else ("current" if i == chapter_idx else "locked"),
                values,
            )
            for i, chapter in enumerate(sorted(chapters.values(), key=lambda c: c.id))
        ],
        "attempt": _attempt_block(attempt) if attempt else None,
    }
