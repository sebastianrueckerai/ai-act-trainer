from app.content.citations import parse_citation, written_ref
from app.corpus.excerpt import excerpt


def test_a_paragraph_that_fits_comes_back_whole(library):
    result = excerpt(library, parse_citation("Art. 4(1)"), budget=4000)
    assert result.dropped == []
    assert result.text == library.node("ai_act:art_4.1").text


def test_an_article_over_budget_drops_whole_paragraphs_and_names_them(library):
    # Article 26 runs to about 8000 characters over twelve paragraphs, and its first four
    # come to 988, so a budget of 1200 keeps a few whole paragraphs and drops the rest.
    result = excerpt(library, parse_citation("Art. 26"), budget=1200)
    assert result.dropped != []
    assert len(result.text) <= 1200
    assert all(ref.startswith("Art. 26(") for ref in result.dropped)
    assert "Art. 26(1)" not in result.dropped


def test_a_cut_never_lands_inside_a_paragraph(library):
    for ref in ("Art. 5", "Art. 6", "Art. 26", "Annex III"):
        result = excerpt(library, parse_citation(ref), budget=800)
        for paragraph_text in result.text.split("\n\n"):
            assert paragraph_text.strip()
            assert not paragraph_text.endswith("…")


def test_the_first_paragraph_survives_even_when_it_alone_exceeds_the_budget(library):
    # Article 5(1) alone runs to 6418 characters, so this proves the rule that the first
    # paragraph is kept whole: returning nothing is worse than returning one long paragraph.
    result = excerpt(library, parse_citation("Art. 5"), budget=50)
    assert result.text == library.node("ai_act:art_5.1").text
    assert result.dropped != []


def test_the_excerpt_carries_the_acts_url(library):
    result = excerpt(library, parse_citation("BDSG § 26(1)"))
    assert "gesetze-im-internet.de" in result.url


def test_a_dropped_entrys_written_reference_names_a_child_of_the_cited_node(library):
    # Every article and annex in the library, cut at budget 0 so nothing past its first
    # paragraph survives: each dropped reference must parse back to a node the library lists
    # as a child of the node the citation names. This is the round trip the grammar promises,
    # and it is what caught Annex XIII, whose top-level points are lettered rather than
    # numbered, which the old grammar could not read back.
    nodes = [node for node in library.index().values() if node.kind in ("article", "annex")]
    assert nodes
    for node in nodes:
        citation = parse_citation(written_ref(node.id))
        assert citation.node_id == node.id
        result = excerpt(library, citation, budget=0)
        children = {child.id for child in library.children(citation.node_id)}
        for dropped_ref in result.dropped:
            assert parse_citation(dropped_ref).node_id in children
