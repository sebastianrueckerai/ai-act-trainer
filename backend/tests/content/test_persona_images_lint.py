from pathlib import Path

from app.content.lint import lint_persona_images
from app.content.models import PersonaManifest


def _persona(persona_id: str = "marvin") -> PersonaManifest:
    return PersonaManifest(
        id=persona_id,
        name={"de": "Marvin"},
        tagline={"de": "..."},
        voice="...",
        style_rules=["..."],
        reactions={
            "cheat": "...",
            "insult": "...",
            "profanity": "...",
            "humor": "...",
            "offtopic": "...",
        },
        verdicts={"right": ["..."], "wrong": ["..."]},
        milestones={"chapter": ["...", "...", "..."], "course": ["..."]},
        emotions=["neutral", "happy"],
        image_prompt="a robot",
    )


def test_lint_lists_every_missing_image(tmp_path: Path):
    missing = lint_persona_images([_persona()], tmp_path)

    assert missing == ["marvin/images/neutral.png", "marvin/images/happy.png"]


def test_lint_passes_when_every_emotion_has_its_file(tmp_path: Path):
    for emotion in ("neutral", "happy"):
        path = tmp_path / "marvin" / "images" / f"{emotion}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG\r\n\x1a\n")

    assert lint_persona_images([_persona()], tmp_path) == []
