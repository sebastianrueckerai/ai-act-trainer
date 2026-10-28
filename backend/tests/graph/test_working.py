import pytest

from app.content.models import WORKING_STEPS
from app.graph.state import initial_state
from app.graph.working import announce, working_line


def test_the_line_is_the_characters_own_when_it_has_one(make_deps):
    deps = make_deps()
    first = working_line(deps, "jester", "de", "grading", pick=lambda lines: lines[0])
    assert first == deps.persona("jester").working["grading"][0]


def test_the_line_falls_back_to_the_plain_one_without_a_character(make_deps):
    deps = make_deps()
    assert working_line(deps, None, "de", "grading") == "prüft deine Antwort"


def test_every_step_has_a_plain_line(make_deps):
    deps = make_deps()
    for step in WORKING_STEPS:
        assert working_line(deps, None, "de", step)


def test_an_unknown_step_is_refused(make_deps):
    with pytest.raises(ValueError):
        working_line(make_deps(), None, "de", "dreaming")


def test_announce_writes_the_step_and_the_line_to_the_stream(make_deps):
    deps = make_deps()
    written: list[dict] = []
    state = initial_state("clerk")
    announce(deps, state, "checking", writer=written.append)
    assert written == [{"type": "working", "step": "checking", "text": written[0]["text"]}]
    assert written[0]["text"] in deps.persona("clerk").working["checking"]


def test_announce_outside_a_graph_run_says_nothing(make_deps):
    announce(make_deps(), initial_state("clerk"), "reading")
