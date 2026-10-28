from app.graph.critic import Critique
from tests.evals.critic_eval import CASES_DIR, load_cases, render, run_calibration


def test_every_case_file_loads_and_names_a_pool_question(make_deps):
    deps = make_deps()
    cases = load_cases(CASES_DIR)
    assert len(cases) >= 15
    for case in cases:
        question = deps.question(case.question)
        assert case.expect in ("ship", "retry")
        if case.expect == "retry":
            assert case.faults
        assert all(1 <= i <= len(question.rubric.must) for i in case.met)


def test_a_case_is_a_hit_when_the_verdict_and_a_named_fault_match(make_deps):
    deps = make_deps(
        script={
            "critic": [
                Critique(verdict="ship", score=5),
                Critique(verdict="retry", faults=["leak", "question"], score=2),
                Critique(verdict="retry", faults=["verdict"], score=2),
            ]
        }
    )
    cases = [c for c in load_cases(CASES_DIR) if c.question == "q-02-05"][:3]
    assert [c.expect for c in cases] == ["ship", "retry", "retry"]
    results = run_calibration(deps, cases)
    # The third case expects repeat or unhelpful; verdict alone is a miss.
    assert [r.hit for r in results] == [True, True, False]
    report = render(results)
    assert "summary: 2 of 3 hits" in report
    assert "MISS q-02-05" in report


def test_the_brief_of_a_case_carries_its_history_and_try(make_deps):
    deps = make_deps(script={"critic": Critique(verdict="ship", score=5)})
    case = next(c for c in load_cases(CASES_DIR) if c.question == "q-02-05" and c.tries == 2)
    run_calibration(deps, [case])
    prompt = deps.models["strong"].prompts[-1]
    assert "Student: Weil man die nur fürs Arbeitsverhältnis nutzen darf." in prompt
    assert "Try 2 of 5" in prompt
    assert "Outcome: partial." in prompt
    assert case.draft.strip() in prompt


def test_every_ship_draft_ends_on_the_ask_its_case_calls_for(make_deps):
    deps = make_deps()
    for case in load_cases(CASES_DIR):
        if case.expect != "ship":
            continue
        if case.outcome in ("right", "settled"):
            assert "?" not in case.draft, case.name
            continue
        rubric = deps.question(case.question).rubric
        met = [rubric.must[i - 1].point for i in case.met]
        ask = " ".join(rubric.next_ask(met).split())
        assert " ".join(case.draft.split()).endswith(ask), case.name
