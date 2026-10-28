from app.content.citations import scan_citations
from app.graph.tools import (
    citations_from_text,
    law_tools,
    library_brief,
    without_inline_citations,
)


def test_open_law_lists_the_children_of_a_chapter_with_summaries(make_deps):
    deps = make_deps()
    tools = {tool.name: tool for tool in law_tools(deps)}
    result = tools["open_law"].invoke({"node_id": "ai_act:cpt_III"})
    assert "ai_act:cpt_III.sct_3" in result or "sct_3" in result
    assert "Pflichten der Anbieter und Betreiber von Hochrisiko-KI-Systemen" in result
    assert "Es legt Pflichten für Anbieter" in result


def test_open_law_lists_the_articles_of_a_section(make_deps):
    deps = make_deps()
    tools = {tool.name: tool for tool in law_tools(deps)}
    result = tools["open_law"].invoke({"node_id": "ai_act:cpt_III.sct_3"})
    assert "ai_act:art_26" in result
    assert "Artikel 26" in result


def test_open_law_on_an_unknown_node_says_so(make_deps):
    deps = make_deps()
    tools = {tool.name: tool for tool in law_tools(deps)}
    result = tools["open_law"].invoke({"node_id": "ai_act:nope"})
    assert "no children" in result


def test_read_law_returns_the_excerpts_text_and_dropped_note(make_deps):
    deps = make_deps()
    tools = {tool.name: tool for tool in law_tools(deps)}
    result = tools["read_law"].invoke({"citation": "Art. 26(7)"})
    assert "Arbeitnehmervertreter" in result
    assert "ai_act:art_26.7" in result
    whole = tools["read_law"].invoke({"citation": "Art. 26"})
    assert "Dropped:" in whole


def test_read_law_on_an_unparseable_citation_returns_the_error(make_deps):
    deps = make_deps()
    tools = {tool.name: tool for tool in law_tools(deps)}
    result = tools["read_law"].invoke({"citation": "nonsense"})
    assert "unrecognized" in result or "CitationError" in result


def test_search_law_returns_ranked_hits(make_deps):
    deps = make_deps()
    tools = {tool.name: tool for tool in law_tools(deps)}
    result = tools["search_law"].invoke({"query": "Betreiberpflichten"})
    assert "ai_act" in result


def test_library_brief_carries_every_act_and_the_ai_act_sections(make_deps):
    deps = make_deps()
    brief = library_brief(deps.library, deps.content)
    for act_id in ("ai_act", "gdpr", "bdsg", "betrvg", "geschgehg", "kimig", "qa"):
        assert act_id in brief
    assert "ai_act:cpt_III" in brief
    assert "ai_act:art_26" not in brief  # articles arrive through open_law, not the brief


def test_scan_citations_finds_forms_in_prose_and_dedupes():
    text = "Siehe Art. 26(7) und GDPR Art. 5(1)(a); nochmal Art. 26(7), plus BDSG § 26(1)."
    found = scan_citations(text)
    ids = [c.node_id for c in found]
    assert ids == ["ai_act:art_26.7", "gdpr:art_5.1.a", "bdsg:sec_26.1"]


def test_scan_citations_ignores_german_prose_forms():
    assert scan_citations("Nach Art. 26 Abs. 7 gilt das.") == []


def test_scan_citations_survives_a_capitalized_word_before_the_citation():
    assert [c.node_id for c in scan_citations("Nach Art. 26(7) gilt das.")] == ["ai_act:art_26.7"]
    assert [c.node_id for c in scan_citations("Gemäß BDSG § 26(1) bleibt es dabei.")] == [
        "bdsg:sec_26.1"
    ]
    assert [c.node_id for c in scan_citations("Siehe Annex III pt. 4(a).")] == [
        "ai_act:anx_III.4.a"
    ]
    assert [c.node_id for c in scan_citations("Laut Rec. 20 ist KI-Kompetenz Pflicht.")] == [
        "ai_act:rct_20"
    ]
    assert [c.node_id for c in scan_citations("Nach DSGVO Art. 6(1) gilt das.")] == ["gdpr:art_6.1"]


def test_scan_citations_attributes_an_unknown_act_prefix_to_the_default_act():
    found = scan_citations("FOO Art. 5(1) nennt die Ausnahme.")
    assert [c.node_id for c in found] == ["ai_act:art_5.1"]


def test_citations_from_text_builds_parts_with_title_and_url(make_deps):
    deps = make_deps()
    parts = citations_from_text(deps, "Geregelt in Art. 5(1)(f).")
    assert parts[0].ref == "Art. 5(1)(f)"
    assert "Artikel 5" in parts[0].title
    assert parts[0].url.startswith("https://")
    assert parts[0].quote.startswith("das Inverkehrbringen")


def test_citations_from_text_cuts_the_quote_at_the_last_sentence_end_within_budget(make_deps):
    deps = make_deps()
    parts = citations_from_text(deps, "Siehe Art. 13(1).")
    assert parts[0].ref == "Art. 13(1)"
    assert parts[0].quote == (
        "Hochrisiko-KI-Systeme werden so konzipiert und entwickelt, dass ihr Betrieb "
        "hinreichend transparent ist, damit die Betreiber die Ausgaben eines Systems "
        "angemessen interpretieren und verwenden können.…"
    )
    assert not parts[0].quote.endswith(" …")


def test_citations_from_text_dedupes_a_citation_repeated_in_the_text(make_deps):
    deps = make_deps()
    parts = citations_from_text(deps, "Siehe Art. 13(1) und noch einmal Art. 13(1).")
    assert [part.ref for part in parts] == ["Art. 13(1)"]


def test_citations_from_text_also_finds_the_spelled_out_article(make_deps):
    deps = make_deps()
    text = (
        "Artikel 5 verbietet das. Artikel 5 Absatz 1 zählt die Ausnahmen auf. "
        "Artikel 5 gilt für jedes KI-System."
    )
    parts = citations_from_text(deps, text)
    assert [part.ref for part in parts] == ["Art. 5", "Art. 5(1)"]


def test_citations_from_text_also_finds_the_parenthesised_spelled_out_paragraph(make_deps):
    deps = make_deps()
    parts = citations_from_text(deps, "Artikel 26 (7) trifft die Meldepflicht.")
    assert [part.ref for part in parts] == ["Art. 26(7)"]


def test_citations_from_text_reads_a_citation_written_the_german_way(make_deps):
    deps = make_deps()
    parts = citations_from_text(deps, "Fundstellen: Art. 26 Abs. 7, § 26 Abs. 1 BDSG")
    assert [part.ref for part in parts] == ["Art. 26(7)", "BDSG § 26(1)"]


def test_without_inline_citations_drops_a_parenthesised_citation_group():
    assert without_inline_citations("Das ist erlaubt (Art. 4 Abs. 1).") == "Das ist erlaubt."
    assert (
        without_inline_citations("Verboten ist es (Art. 5 Abs. 1 Buchst. f und EG 44).")
        == "Verboten ist es."
    )


def test_without_inline_citations_keeps_a_group_that_carries_prose():
    text = "Das ist erlaubt (siehe Art. 4 Abs. 1)."
    assert without_inline_citations(text) == text


def test_without_inline_citations_drops_the_trailing_sources_line():
    assert (
        without_inline_citations("Das ist erlaubt.\n\nFundstellen: Art. 4 Abs. 1")
        == "Das ist erlaubt."
    )
    assert without_inline_citations("Das ist erlaubt.\nQuelle: Art. 4 Abs. 1") == "Das ist erlaubt."


def test_without_inline_citations_leaves_a_citation_a_sentence_carries_itself():
    text = "Art. 5 verbietet das Ableiten von Emotionen am Arbeitsplatz."
    assert without_inline_citations(text) == text


def test_without_inline_citations_tidies_the_space_the_cut_leaves():
    assert (
        without_inline_citations("Erlaubt ist das (Art. 4 Abs. 1) , weil du kein Betreiber bist.")
        == "Erlaubt ist das, weil du kein Betreiber bist."
    )
