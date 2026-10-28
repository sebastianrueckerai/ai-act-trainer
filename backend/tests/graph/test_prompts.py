from app.graph.prompts import CITE_RULE


def test_the_citation_forms_are_not_a_menu():
    # The tutor pointed a student at Art. 26(7) for a question no act answers from that
    # article; the form list was the menu it ordered from (2026-10-01).
    assert "not pointers" in CITE_RULE
    assert "only when the tools or the brief put" in CITE_RULE
