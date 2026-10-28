from app.content.loader import load_content
from tests.conftest import REPO_ROOT


def test_the_pool_covers_the_fixed_test_mix():
    bundle = load_content(REPO_ROOT / "content", REPO_ROOT / "personas")
    questions = bundle.locales["de"].questions
    by_type = {"yes_no": [], "multiple_choice": [], "free_text": []}
    for question in questions.values():
        by_type[question.type].append(question.id)
    assert len(by_type["yes_no"]) >= 3
    assert len(by_type["multiple_choice"]) >= 3
    assert len(by_type["free_text"]) >= 4


def test_the_new_questions_cite_resolvable_law():
    from app.content.citations import parse_citation

    bundle = load_content(REPO_ROOT / "content", REPO_ROOT / "personas")
    for qid in ("q-01-09", "q-01-10"):
        for ref in bundle.locales["de"].questions[qid].citations:
            assert parse_citation(ref).node_id
