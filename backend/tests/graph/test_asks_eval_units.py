from app.graph.grade import Verdict
from tests.evals.asks_eval import AskResult, render, run_asks


def test_every_ask_is_pasted_back_and_graded_by_the_model(make_deps):
    deps = make_deps(script={"grade": Verdict(correct=False, matched=[1], missing=[2])})
    results = run_asks(deps, ["q-01-05"])
    # q-01-05 is picked, not typed: its first point carries no ask, only the why is pasted.
    assert [r.point_index for r in results] == [2]
    assert results[0].own is False
    assert results[0].others == [1]
    assert deps.models["strong"].calls == ["grade"]


def test_render_names_the_failing_asks():
    results = [
        AskResult(question_id="q-01-05", point_index=1, ask="Darf sie?", own=True, others=[]),
        AskResult(question_id="q-01-05", point_index=2, ask="Worauf?", own=False, others=[1]),
    ]
    text = render(results)
    assert "q-01-05 1 LEAK: Darf sie?" in text
    assert "q-01-05 2 ok (earns 1)" in text
    assert "1 of 2 asks earn their own point" in text
