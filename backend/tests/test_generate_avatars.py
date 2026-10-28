"""The from-neutral prompts of the avatar generator: one drawing, one changed feature."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "generate_avatars", Path(__file__).resolve().parents[2] / "tools" / "generate_avatars.py"
)
ga = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ga)

PERSONAS = Path(__file__).resolve().parents[2] / "personas"


def manifest(persona_id: str) -> dict:
    return ga.personas(PERSONAS)[[m["id"] for m in ga.personas(PERSONAS)].index(persona_id)]


def test_from_neutral_prompts_pin_the_same_drawing_and_change_only_the_mouth():
    jester = manifest("jester")
    body = ga.build_prompt(jester, "neutral").rsplit(". calm neutral expression.", 1)[0]
    happy = ga.build_from_neutral_prompt(jester, "happy")
    disappointed = ga.build_from_neutral_prompt(jester, "disappointed")
    assert happy.startswith(f"{body}.")
    assert disappointed.startswith(f"{body}.")
    assert "smile" in happy
    assert "frown" in disappointed


def test_depressobot_does_not_smile_its_happy_is_the_raised_eyebrow():
    marvin = manifest("marvin")
    happy = ga.build_from_neutral_prompt(marvin, "happy")
    assert "eyebrow" in happy
    assert "smile" not in happy
    assert "frown" in ga.build_from_neutral_prompt(marvin, "disappointed")
