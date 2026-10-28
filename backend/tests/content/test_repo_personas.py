import re
from pathlib import Path

from app.content.citations import scan_citations, with_raw_citations
from app.content.loader import _load_personas
from app.content.models import WORKING_STEPS

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_every_persona_loads_complete_and_german():
    personas = _load_personas(REPO_ROOT / "personas")
    assert set(personas) == {"clerk", "jester", "marvin", "pirate", "sergeant"}
    # Reaction frames exist only where a human blessed them: Depressobot reacts to
    # nothing, the jester has no happy frame.
    emotions = {
        "clerk": ["neutral", "happy", "disappointed"],
        "jester": ["neutral", "disappointed"],
        "marvin": ["neutral"],
        "pirate": ["neutral", "happy", "disappointed"],
        "sergeant": ["neutral", "happy", "disappointed"],
    }
    for persona in personas.values():
        assert "de" in persona.name and "de" in persona.tagline
        assert set(persona.reactions) == {"cheat", "insult", "profanity", "humor", "offtopic"}
        assert persona.emotions == emotions[persona.id]
        # Twelve set greetings: the course opens on one of them, instantly.
        assert len(persona.openings) == 12
        assert len(set(persona.openings)) == 12
        assert set(persona.prompts) == {"de"}
        assert persona.prompts["de"].strip()
        # The English demo locale shows the name plate and the picker card in English
        # (D77); the voice itself stays German and is translated at the edge.
        assert set(persona.name) == set(persona.tagline) == {"de", "en"}
        # A line for every step beside the typing dots, in the character's voice.
        assert set(persona.working) == set(WORKING_STEPS)
        assert all(len(lines) >= 2 for lines in persona.working.values())


def test_every_persona_reacts_to_a_finished_chapter_and_course_without_a_legal_claim():
    for persona in _load_personas(REPO_ROOT / "personas").values():
        chapter, course = persona.milestones["chapter"], persona.milestones["course"]
        assert len(chapter) == len(set(chapter)) == 3, persona.id
        assert len(course) == 1, persona.id
        # A chapter line names its chapter; the course line has no number to name.
        assert all("{n}" in line for line in chapter), persona.id
        assert "{" not in course[0], persona.id
        for line in [*chapter, *course]:
            first = re.sub(r"[^\wäöüß ]", " ", line.lower()).split()[0]
            assert first not in ("ja", "nein"), line
            assert not scan_citations(with_raw_citations(line)), line
            assert not any(phrase.rstrip("!, ") in line for phrase in persona.banned_phrases)
        if persona.id in ("clerk", "marvin"):
            assert "!" not in "".join([*chapter, *course]), persona.id


def test_no_persona_may_address_the_student_as_a_gendered_noun():
    """D60: the prompt bans it and the small models write one anyway, so it is enforced."""
    for persona in _load_personas(REPO_ROOT / "personas").values():
        banned = {phrase.rstrip("!, ").lower() for phrase in persona.banned_phrases}
        assert {"kamerad"} <= banned or persona.id == "clerk"
        assert all(
            phrase.endswith(("!", ", ")) or " " in phrase for phrase in persona.banned_phrases
        )


def test_the_clerk_stands_last_and_is_the_one_human():
    personas = _load_personas(REPO_ROOT / "personas")

    assert list(personas) == ["jester", "marvin", "pirate", "sergeant", "clerk"]
    assert [p.id for p in personas.values() if not p.machine] == ["clerk"]
