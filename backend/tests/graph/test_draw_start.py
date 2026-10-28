import random

from langchain_core.messages import HumanMessage

from app.graph.draw import TEST_MIX, draw_questions
from app.graph.state import (
    Intent,
    Phase,
    TurnScratch,
    UiEvent,
    hint_for_question,
    initial_state,
)
from app.graph.test_flow import start_test_node
from app.i18n import t

# Frozen from the one declared run of draw_questions(pool, random.Random("seed:1")).
FROZEN_SEED_1: list[str] = [
    "q-05-03",
    "q-06-04",
    "q-06-02",
    "q-04-02",
    "q-04-03",
    "q-03-02",
    "q-08-01",
    "q-02-03",
    "q-01-06",
    "q-07-03",
]


def _pool(deps) -> dict:
    return deps.locale_content("de").questions


def _free_state(session_seed: str = "seed") -> dict:
    state = initial_state("clerk")
    state["phase"] = Phase.free
    state["chapters_done"] = ["01-warum-es-dich-betrifft"]
    state["attempts"] = 0
    state["session_seed"] = session_seed
    state["messages"] = [HumanMessage("Ich bin bereit für den Test.")]
    state["turn"] = TurnScratch(intent=Intent.start_test)
    return state


def test_the_draw_with_a_frozen_seed_returns_the_exact_ten_ids(make_deps):
    deps = make_deps(script={})
    assert draw_questions(_pool(deps), random.Random("seed:1")) == FROZEN_SEED_1


def test_the_draw_keeps_the_fixed_mix_and_stays_inside_the_pool(make_deps):
    deps = make_deps(script={})
    pool = _pool(deps)
    ids = draw_questions(pool, random.Random("seed:1"))
    assert len(ids) == sum(TEST_MIX.values())
    assert set(ids) <= set(pool)
    for question_type, count in TEST_MIX.items():
        drawn = [question_id for question_id in ids if pool[question_id].type == question_type]
        assert len(drawn) == count


def test_two_draw_seeds_give_different_orders(make_deps):
    deps = make_deps(script={})
    pool = _pool(deps)
    first = draw_questions(pool, random.Random("seed:1"))
    second = draw_questions(pool, random.Random("seed:2"))
    assert first != second


def test_start_test_draws_ten_moves_to_the_test_phase_and_asks_the_first_question(make_deps):
    deps = make_deps(script={})
    pool = _pool(deps)
    expected_ids = draw_questions(pool, random.Random("seed:1"))
    first = pool[expected_ids[0]]
    result = start_test_node(deps)(_free_state())
    intro = t("de", "test_intro", total=10)
    assert result["phase"] is Phase.test
    assert result["attempts"] == 1
    assert result["test"].question_ids == expected_ids
    assert result["test"].index == 0
    assert result["turn"].draft == f"{intro}\n\n{first.question}"
    assert result["turn"].input_hint == hint_for_question(first)
    assert result["turn"].context_question == first.id
    assert result["turn"].closing_line == ""
    assert UiEvent(name="test_started", payload={"total": 10}) in result["turn"].ui_events
    assert result["pending_prompt"] == first.question
    assert "messages" not in result
    assert deps.models["strong"].calls == []


def test_two_session_seeds_draw_different_question_orders(make_deps):
    deps = make_deps(script={})
    first = start_test_node(deps)(_free_state("seed-a"))
    second = start_test_node(deps)(_free_state("seed-b"))
    assert first["test"].question_ids != second["test"].question_ids


def test_the_draw_spreads_over_the_chapters(make_deps):
    deps = make_deps(script={})
    content = deps.content.locales["de"]
    questions = content.questions
    seen: set[str] = set()
    for seed in range(20):
        ids = draw_questions(questions, random.Random(seed))
        assert len(ids) == sum(TEST_MIX.values())
        # Every chapter holds at least one question of every type, and the draw takes one
        # id per chapter per pass, so a type's picks come from that many chapters.
        for question_type, count in TEST_MIX.items():
            drawn = [qid for qid in ids if questions[qid].type == question_type]
            assert len({questions[qid].chapter for qid in drawn}) == count
        seen |= {questions[qid].chapter for qid in ids}
    assert seen == set(content.chapters)
