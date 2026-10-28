from app.graph.state import InputHint, Phase, TurnScratch, hint_for_question, initial_state


def test_initial_state_starts_the_first_lesson_in_german():
    state = initial_state("clerk")
    assert state["phase"] is Phase.lesson
    assert state["locale"] == "de"
    assert state["messages"] == []


def test_initial_state_carries_the_persona_identity_and_seed():
    state = initial_state("jester", user_id=7, session_seed="abc")
    assert state["persona_id"] == "jester"
    assert state["user_id"] == 7
    assert state["session_seed"] == "abc"


def test_a_fresh_turn_scratch_is_neutral():
    scratch = TurnScratch()
    assert scratch.draft == ""
    assert scratch.input_hint == InputHint(kind="text")
    assert scratch.parts == []


def test_input_hint_defaults_to_not_asking():
    assert InputHint(kind="confirm").asks is False


def test_hint_for_question_always_asks(make_deps):
    deps = make_deps(script={})
    assert hint_for_question(deps.question("q-01-01")).asks is True
    assert hint_for_question(deps.question("q-01-03")).asks is True
    assert hint_for_question(deps.question("q-02-04")).asks is True
