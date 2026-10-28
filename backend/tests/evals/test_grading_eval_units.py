from pathlib import Path

import pytest
from pydantic import ValidationError

from app.content.loader import load_content
from tests.evals.grading_eval import (
    EvalCase,
    QuestionCases,
    load_cases,
    render_report,
    summarize,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_every_free_text_question_has_a_case_file():
    bundle = load_content(REPO_ROOT / "content", REPO_ROOT / "personas")
    free = {qid for qid, q in bundle.locales["de"].questions.items() if q.type == "free_text"}
    cases = load_cases()
    assert set(cases) == free
    for question_cases in cases.values():
        assert len(question_cases.cases) >= 5
        fairs = [case.fair for case in question_cases.cases]
        assert fairs.count("correct") >= 3 and fairs.count("wrong") >= 2
        assert all(case.note.strip() for case in question_cases.cases)


def _result(question: str, case_id: str, fair: str, graded_correct: bool):
    case = EvalCase(id=case_id, answer="x", fair=fair, note="n")
    from tests.evals.grading_eval import CaseResult

    return CaseResult(question=question, case=case, graded_correct=graded_correct)


def test_the_metrics_count_fairness_the_way_the_ruling_demands():
    results = [
        _result("q", "clean", "correct", True),
        _result("q", "sloppy", "correct", True),
        _result("q", "meant-right", "correct", False),
        _result("q", "plausible-miss", "wrong", False),
        _result("q", "confidently-wrong", "wrong", True),
    ]
    report = summarize("strong", "strong-alias", results)
    assert report.accuracy == 3 / 5
    assert report.fnr == 1 / 3
    assert report.fpr == 1 / 2


def test_metrics_with_no_wrong_cases_report_none_rather_than_dividing_by_zero():
    results = [_result("q", "clean", "correct", True)]
    report = summarize("strong", "strong-alias", results)
    assert report.fpr is None and report.fnr == 0.0


def test_the_report_names_the_floor_and_the_failures():
    results = [
        _result("q", "clean", "correct", True),
        _result("q", "meant-right", "correct", False),
        _result("q", "plausible-miss", "wrong", False),
        _result("q2", "confidently-wrong", "wrong", True),
    ]
    text = render_report([summarize("strong", "alias-s", results)])
    assert "0.9" in text and "0.1" in text
    assert "meant-right" in text and "confidently-wrong" in text
    assert "| q | 3 | 2 |" in text and "| q2 | 1 | 0 |" in text


def test_an_unknown_fair_label_is_rejected():
    with pytest.raises(ValidationError):
        QuestionCases.model_validate(
            {"question": "q", "cases": [{"id": "x", "answer": "y", "fair": "maybe"}]}
        )
