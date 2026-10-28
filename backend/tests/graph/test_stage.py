from app.content.loader import load_content
from app.graph.stage import build_stage
from app.graph.state import GradedAnswer
from app.graph.state import TestState as RunningTest
from app.settings import REPO_ROOT, Settings

SETTINGS = Settings(
    _env_file=None,
    env="test",
    database_url="sqlite:///:memory:",
    content_dir=REPO_ROOT / "content",
    personas_dir=REPO_ROOT / "personas",
)
CONTENT = load_content(SETTINGS.content_dir, SETTINGS.personas_dir)


def test_stage_before_anything() -> None:
    stage = build_stage(CONTENT, SETTINGS.personas_dir, {"locale": "de"})

    assert stage["persona"] is None
    assert stage["mood"] == "neutral"
    assert stage["streak"] == 0
    assert len(stage["chapters"]) == 8
    assert stage["chapters"][0]["state"] == "current"
    assert stage["chapters"][1]["state"] == "locked"
    assert stage["attempt"] is None


def test_stage_after_chapter_and_during_test() -> None:
    values = {
        "locale": "de",
        "persona_id": "marvin",
        "mood": "happy",
        "streak": 2,
        "chapters_done": ["01-warum-es-dich-betrifft"],
        "chapter_idx": 1,
        "test": RunningTest(
            question_ids=[f"q{i}" for i in range(10)],
            index=2,
            answers=[
                GradedAnswer(
                    question_id="q0",
                    answer="a",
                    correct=True,
                    matched=[],
                    missing=[],
                    tries=1,
                    hint_shown=False,
                ),
                GradedAnswer(
                    question_id="q1",
                    answer="b",
                    correct=False,
                    matched=[],
                    missing=[],
                    tries=1,
                    hint_shown=False,
                ),
            ],
        ),
    }

    stage = build_stage(CONTENT, SETTINGS.personas_dir, values)

    # Depressobot carries no reaction frames: whatever the mood, his portrait stays
    # neutral.
    assert stage["persona"] == {
        "id": "marvin",
        "name": "Depressobot",
        "image_url": "/api/personas/marvin/images/neutral",
        "neutral_image_url": "/api/personas/marvin/images/neutral",
        "scene_url": "/api/personas/marvin/images/scene",
        "scene_light_url": "/api/personas/marvin/images/scene-light",
    }
    assert stage["mood"] == "happy"
    assert stage["streak"] == 2
    by_id = {c["id"]: c for c in stage["chapters"]}
    assert by_id["01-warum-es-dich-betrifft"]["state"] == "done"
    assert by_id["02-was-du-hineingeben-darfst"]["state"] == "current"
    assert stage["attempt"] == {"kind": "test", "index": 2, "results": [True, False], "total": 10}


def _bar(values: dict) -> list[tuple[str, int, int | None]]:
    stage = build_stage(CONTENT, SETTINGS.personas_dir, {"locale": "de", **values})
    return [(c["state"], c["steps"], c["step"]) for c in stage["chapters"][:3]]


def test_a_taught_step_counts_only_once_its_case_is_settled() -> None:
    case = RunningTest(question_ids=["q-01-01"], practice=True)

    assert _bar({"step_idx": 1, "pending_case": "q-01-01"})[0] == ("current", 6, 0)
    assert _bar({"step_idx": 1, "practice": case})[0] == ("current", 6, 0)
    assert _bar({"step_idx": 1, "practice": None})[0] == ("current", 6, 1)
    assert _bar({})[0] == ("current", 6, 0)


def test_only_the_current_chapter_carries_its_step() -> None:
    values = {
        "chapters_done": ["01-warum-es-dich-betrifft"],
        "chapter_idx": 1,
        "step_idx": 3,
        "pending_case": "q-02-03",
    }

    assert _bar(values) == [("done", 6, None), ("current", 5, 2), ("locked", 4, None)]


def test_a_finished_chapter_waiting_for_its_click_is_done_and_none_is_current() -> None:
    values = {"chapters_done": ["01-warum-es-dich-betrifft"], "chapter_idx": 0, "step_idx": 6}

    assert _bar(values) == [("done", 6, None), ("locked", 5, None), ("locked", 4, None)]


def test_a_persona_without_a_drawn_scene_carries_none() -> None:
    values = {"locale": "de", "persona_id": "marvin", "mood": "happy"}

    stage = build_stage(CONTENT, SETTINGS.personas_dir / "nowhere", values)

    assert stage["persona"]["scene_url"] is None
    assert stage["persona"]["image_url"] is None


def test_stage_shows_a_running_practice_as_the_attempt() -> None:
    values = {
        "locale": "de",
        "test": None,
        "practice": RunningTest(
            question_ids=["q-02-01", "q-02-04"],
            index=1,
            answers=[GradedAnswer(question_id="q-02-01", answer="Ja.", correct=True)],
            practice=True,
        ),
    }

    stage = build_stage(CONTENT, SETTINGS.personas_dir, values)

    assert stage["attempt"] == {"kind": "practice", "index": 1, "results": [True], "total": 2}


def test_the_name_plate_follows_the_display_locale() -> None:
    values = {"locale": "de", "display_locale": "en", "persona_id": "marvin", "mood": "happy"}

    stage = build_stage(CONTENT, SETTINGS.personas_dir, values)

    assert stage["persona"]["name"] == "Depressobot"
    values["persona_id"] = "pirate"
    assert build_stage(CONTENT, SETTINGS.personas_dir, values)["persona"]["name"] == "The Privateer"


def test_the_chapter_titles_follow_the_display_locale() -> None:
    values = {"locale": "de", "display_locale": "en", "persona_id": "clerk"}
    titles = {chapter.id: f"EN {chapter.id}" for chapter in CONTENT.locales["de"].chapters.values()}

    stage = build_stage(CONTENT, SETTINGS.personas_dir, values, titles_en=titles)

    assert stage["chapters"] and all(c["title"].startswith("EN ") for c in stage["chapters"])
    german = build_stage(
        CONTENT, SETTINGS.personas_dir, {**values, "display_locale": "de"}, titles_en=titles
    )
    assert not any(c["title"].startswith("EN ") for c in german["chapters"])
