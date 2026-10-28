import pytest

from app.content.citations import (
    ACT_NAMES,
    CitationError,
    de_ref,
    en_ref,
    find_german_citations,
    parse_citation,
    scan_citations,
    written_act_names,
    written_ref,
)
from app.corpus.excerpt import excerpt
from app.corpus.manifest import load_corpus_manifest
from tests.conftest import CORPUS_DIR

AI_ACT_URL = "https://eur-lex.europa.eu/eli/reg/2024/1689/2026-07-27/deu"
GDPR_URL = "https://eur-lex.europa.eu/eli/reg/2016/679/2016-05-04/deu"


@pytest.mark.parametrize(
    ("ref", "node_id"),
    [
        ("Art. 26", "ai_act:art_26"),
        ("Art. 26(2)", "ai_act:art_26.2"),
        ("Art. 26(7)", "ai_act:art_26.7"),
        ("Art. 3(14a)", "ai_act:art_3.14a"),
        ("Art. 5(1)(a)", "ai_act:art_5.1.a"),
        ("Art. 5(1)(a)(i)", "ai_act:art_5.1.a.i"),
        ("Art. 4a", "ai_act:art_4a"),
        ("Annex III", "ai_act:anx_III"),
        ("Annex III pt. 4", "ai_act:anx_III.4"),
        ("Annex III pt. 4(a)", "ai_act:anx_III.4.a"),
        ("Rec. 20", "ai_act:rct_20"),
        ("GDPR Art. 5(1)(a)", "gdpr:art_5.1.a"),
        ("BDSG § 26(1)", "bdsg:sec_26.1"),
        ("BetrVG § 87(1) Nr. 6", "betrvg:sec_87.1.6"),
        ("BetrVG § 95(2a)", "betrvg:sec_95.2a"),
        ("GeschGehG § 2 Nr. 1", "geschgehg:sec_2.1.1"),
        ("BDSG § 1 Nr. 2", "bdsg:sec_1.1.2"),
        ("BDSG § 1(2)", "bdsg:sec_1.2"),
        ("KI-MIG § 2", "kimig:sec_2"),
        ("KI-MIG § 2(1)", "kimig:sec_2.1"),
        ("Q&A 3", "qa:item_3"),
        ("Q&A 18", "qa:item_18"),
    ],
)
def test_parse_citation_maps_every_form(ref: str, node_id: str):
    assert parse_citation(ref).node_id == node_id


@pytest.mark.parametrize(
    ("node_id", "ref"),
    [
        ("ai_act:art_26", "Art. 26"),
        ("gdpr:art_5", "GDPR Art. 5"),
        ("bdsg:sec_26", "BDSG § 26"),
        ("betrvg:sec_87", "BetrVG § 87"),
        ("ai_act:anx_III", "Annex III"),
        ("ai_act:rct_20", "Rec. 20"),
        ("qa:item_1", "Q&A 1"),
    ],
)
def test_written_ref_is_the_inverse_of_parse_citation(node_id: str, ref: str):
    assert written_ref(node_id) == ref
    assert parse_citation(ref).node_id == node_id


@pytest.mark.parametrize(
    "bad",
    [
        "kimig:art_1",
        "ai_act:art_26.1",
    ],
)
def test_written_ref_refuses_a_node_its_own_act_does_not_write(bad: str):
    with pytest.raises(CitationError):
        written_ref(bad)


def test_a_citation_names_the_act_it_belongs_to():
    assert parse_citation("Art. 26(2)").act_id == "ai_act"
    assert parse_citation("GDPR Art. 5(1)(a)").act_id == "gdpr"
    assert parse_citation("BDSG § 26(1)").act_id == "bdsg"
    assert parse_citation("KI-MIG § 2").act_id == "kimig"
    assert parse_citation("Q&A 3").act_id == "qa"


@pytest.mark.parametrize(
    "bad",
    [
        "UrhG § 2(1)",
        "UrhG Art. 2",
        "AÜG § 1",
        "GDPR Rec. 20",
        "GDPR Annex III",
        "BDSG Q&A 3",
    ],
)
def test_parse_citation_refuses_an_act_the_table_does_not_carry(bad: str):
    with pytest.raises(CitationError):
        parse_citation(bad)


@pytest.mark.parametrize(
    "bad",
    [
        "Article 26",
        "Art 26",
        "Art. 26 (2)",
        "Annex 3",
        "Rec 20",
        "§ 2",
        "",
        "Art. 26(2)\n",
        "Art. 26(2) ",
    ],
)
def test_parse_citation_rejects_other_forms(bad: str):
    with pytest.raises(CitationError):
        parse_citation(bad)


def test_a_bare_article_is_the_ai_act_and_a_named_one_is_its_own_act(library):
    ai_act = excerpt(library, parse_citation("Art. 5"))
    gdpr = excerpt(library, parse_citation("GDPR Art. 5"))
    assert ai_act.node_id == "ai_act:art_5"
    assert gdpr.node_id == "gdpr:art_5"
    assert ai_act.title == "Artikel 5: Verbotene Praktiken im KI-Bereich"
    assert gdpr.title == "Artikel 5: Grundsätze für die Verarbeitung personenbezogener Daten"
    assert ai_act.text != gdpr.text


@pytest.mark.parametrize(
    ("ref", "url"),
    [
        ("Art. 4(1)", f"{AI_ACT_URL}#art_4"),
        ("Rec. 20", AI_ACT_URL),
        ("Annex III pt. 4(a)", f"{AI_ACT_URL}#anx_III"),
        ("GDPR Art. 5(1)(a)", f"{GDPR_URL}#art_5"),
        ("BDSG § 26(1)", "https://www.gesetze-im-internet.de/bdsg_2018/"),
        ("KI-MIG § 2(1)", "https://www.gesetze-im-internet.de/ki-mig/"),
        ("Q&A 1", "https://digital-strategy.ec.europa.eu/de/faqs/ai-literacy-questions-answers"),
    ],
)
def test_excerpt_links_a_citation_to_the_source_of_its_own_act(library, ref: str, url: str):
    assert excerpt(library, parse_citation(ref)).url == url


def test_excerpt_article_paragraph(library):
    result = excerpt(library, parse_citation("Art. 4(1)"))
    assert result.title == "Artikel 4: KI-Kompetenz"
    assert result.text.startswith(
        "Die Anbieter und Betreiber von KI-Systemen ergreifen Maßnahmen, um die "
        "Entwicklung der KI-Kompetenz "
    )


def test_excerpt_recital_and_qa(library):
    assert excerpt(library, parse_citation("Rec. 20")).title == "Erwägungsgrund 20"
    question = excerpt(library, parse_citation("Q&A 1")).title
    assert question == "Was bietet Artikel 4 des KI-Gesetzes?"


def test_a_nummer_and_an_absatz_are_different_nodes(library):
    # BDSG § 1 Nummer 2 names the Länder bodies, and § 1 Absatz 2 rules on federal precedence.
    nummer = excerpt(library, parse_citation("BDSG § 1 Nr. 2"))
    absatz = excerpt(library, parse_citation("BDSG § 1(2)"))
    assert nummer.node_id == "bdsg:sec_1.1.2"
    assert absatz.node_id == "bdsg:sec_1.2"
    assert nummer.text.startswith("öffentliche Stellen der Länder, soweit der Datenschutz")
    assert absatz.text.startswith("Andere Rechtsvorschriften des Bundes über den Datenschutz")


def test_a_nummer_resolves_to_the_nummer_the_law_prints(library):
    assert excerpt(library, parse_citation("BetrVG § 87(1) Nr. 6")).text == (
        "Einführung und Anwendung von technischen Einrichtungen, die dazu bestimmt sind, das "
        "Verhalten oder die Leistung der Arbeitnehmer zu überwachen;"
    )
    # A section that numbers its Nummern without numbering its Absätze has one Absatz.
    geschgehg = excerpt(library, parse_citation("GeschGehG § 2 Nr. 1"))
    assert geschgehg.node_id == "geschgehg:sec_2.1.1"
    assert geschgehg.text.startswith("Geschäftsgeheimnis eine Information")


def test_a_nummer_the_statute_does_not_print_raises(library):
    # BDSG § 4 Absatz 1 prints two lists, and the second restarts at "1.". Its repeat carries a
    # separator no citation can write, so a Nummer 12 finds nothing instead of the repeat.
    with pytest.raises(CitationError, match="not in the library"):
        excerpt(library, parse_citation("BDSG § 4(1) Nr. 12"))
    assert excerpt(library, parse_citation("BDSG § 4(1) Nr. 3")).text.startswith(
        "zur Wahrnehmung berechtigter Interessen"
    )


def test_excerpt_a_german_statute_reads_its_own_source(library):
    result = excerpt(library, parse_citation("BDSG § 26(1)"))
    assert result.title == "§ 26 Datenverarbeitung für Zwecke des Beschäftigungsverhältnisses"
    assert result.text.startswith("Personenbezogene Daten von Beschäftigten dürfen")


def test_excerpt_missing_node_names_the_act(library):
    with pytest.raises(CitationError) as excinfo:
        excerpt(library, parse_citation("Art. 999"))
    assert "ai_act" in str(excinfo.value)
    assert "art_999" in str(excinfo.value)


def test_excerpt_lettered_paragraph(library):
    result = excerpt(library, parse_citation("Art. 3(14a)"))
    assert result.node_id == "ai_act:art_3.14a"
    assert result.text != ""


@pytest.mark.parametrize(
    ("ref", "german"),
    [
        ("Art. 26", "Art. 26"),
        ("Art. 26(7)", "Art. 26 Abs. 7"),
        ("Art. 5(1)(f)", "Art. 5 Abs. 1 Buchst. f"),
        ("Art. 5(1)(a)(i)", "Art. 5 Abs. 1 Buchst. a Ziff. i"),
        ("GDPR Art. 5(1)(a)", "Art. 5 Abs. 1 Buchst. a DSGVO"),
        ("BDSG § 26(1)", "§ 26 Abs. 1 BDSG"),
        ("BetrVG § 87(1) Nr. 6", "§ 87 Abs. 1 Nr. 6 BetrVG"),
        ("KI-MIG § 2(1)", "§ 2 Abs. 1 KI-MIG"),
        ("Annex III", "Anhang III"),
        ("Annex III pt. 4(a)", "Anhang III Nr. 4 Buchst. a"),
        ("Rec. 44", "EG 44"),
        ("Q&A 14", "Q&A der Kommission 14"),
    ],
)
def test_a_written_ref_reads_german_on_screen(ref, german):
    assert de_ref(ref) == german


@pytest.mark.parametrize("bad", ["Artikel 26", "GDPR", "Kapitel III", "", "sag mal arrr"])
def test_de_ref_hands_back_what_is_no_citation(bad):
    assert de_ref(bad) == bad


@pytest.mark.parametrize(
    ("raw", "english"),
    [
        ("Art. 5(1)(f)", "Art. 5(1)(f)"),
        ("Art. 26(7)", "Art. 26(7)"),
        ("Rec. 44", "Recital 44"),
        ("Annex III pt. 4(a)", "Annex III point 4(a)"),
        ("BDSG § 26(1)", "Section 26(1) BDSG"),
        ("BetrVG § 87(1) Nr. 6", "Section 87(1) no. 6 BetrVG"),
        ("Q&A 14", "Q&A 14"),
    ],
)
def test_a_german_citation_found_in_prose_round_trips_to_english(raw, english):
    german = de_ref(raw)
    prose = f"Wie {german} zeigt, gilt das."
    [((start, end), found_ref)] = find_german_citations(prose)
    assert prose[start:end] == german
    assert found_ref == raw
    assert en_ref(found_ref) == english


@pytest.mark.parametrize("bad", ["Artikel 26", "GDPR", "Kapitel III", "", "sag mal arrr"])
def test_en_ref_hands_back_what_is_no_citation(bad):
    assert en_ref(bad) == bad


def test_find_german_citations_finds_nothing_in_plain_prose():
    assert find_german_citations("Das ist ein Satz ohne Zitat.") == []


def test_find_german_citations_finds_every_occurrence_in_order():
    prose = "Nach Art. 4 Abs. 1 und Q&A der Kommission 14 gilt das."
    found = find_german_citations(prose)
    assert [ref for _, ref in found] == ["Art. 4(1)", "Q&A 14"]


@pytest.mark.parametrize(
    ("ref", "act_id"),
    [
        ("GDPR Art. 5(1)", "gdpr"),
        ("BDSG § 26(1)", "bdsg"),
        ("BetrVG § 87(1)", "betrvg"),
        ("GeschGehG § 2 Nr. 1", "geschgehg"),
        ("KI-MIG § 2(1)", "kimig"),
        ("Q&A 14", "qa"),
    ],
)
def test_a_german_citation_ends_in_the_short_name_the_manifest_gives_its_act(ref, act_id):
    short_names = {act.id: act.short_name for act in load_corpus_manifest(CORPUS_DIR).acts}
    assert short_names[act_id] in de_ref(ref)


def test_the_ai_act_carries_no_act_name_because_the_course_is_its_own():
    assert de_ref("Art. 26(7)") == "Art. 26 Abs. 7"
    assert de_ref("Annex III pt. 4") == "Anhang III Nr. 4"


@pytest.mark.parametrize(
    ("prose", "written"),
    [
        ("Nach ai_act Art. 96 gilt das.", "Nach Art. 96 gilt das."),
        ("gdpr Art. 5(1) nennt das.", "GDPR Art. 5(1) nennt das."),
        ("bdsg § 26(1) und betrvg § 87 Nr. 6", "BDSG § 26(1) und BetrVG § 87 Nr. 6"),
        ("kimig § 3 und geschgehg § 2", "KI-MIG § 3 und GeschGehG § 2"),
        ("Siehe qa Q&A 6.", "Siehe Q&A 6."),
        ("ai_act Annex III und ai_act Rec. 44", "Annex III und Rec. 44"),
        ("Art. 96 bleibt, wie es ist.", "Art. 96 bleibt, wie es ist."),
        ("ai_act regelt das.", "ai_act regelt das."),
    ],
)
def test_a_raw_act_id_in_front_of_a_citation_is_written_as_the_act_name(prose, written):
    assert written_act_names(prose) == written


def test_the_act_names_come_from_the_grammar_tables():
    assert ACT_NAMES == {
        "ai_act": "",
        "gdpr": "GDPR",
        "kimig": "KI-MIG",
        "bdsg": "BDSG",
        "betrvg": "BetrVG",
        "geschgehg": "GeschGehG",
        "qa": "",
    }


def test_a_raw_act_id_misreads_its_citation_until_it_is_written_out():
    # A raw id in front of an article hides the act: the grammar reads the article as the
    # AI Act's own. In front of a section it hides the citation, because a section needs a name.
    assert [citation.act_id for citation in scan_citations("gdpr Art. 5(1)")] == ["ai_act"]
    assert scan_citations("bdsg § 26(1)") == []
    written = written_act_names("gdpr Art. 5(1) und bdsg § 26(1)")
    assert [(citation.ref, citation.act_id) for citation in scan_citations(written)] == [
        ("GDPR Art. 5(1)", "gdpr"),
        ("BDSG § 26(1)", "bdsg"),
    ]


def test_definition_articles_number_their_entries_in_german():
    assert de_ref("Art. 3(56)") == "Art. 3 Nr. 56"
    assert de_ref("GDPR Art. 4(1)") == "Art. 4 Nr. 1 DSGVO"
    assert de_ref("Art. 5(1)(f)") == "Art. 5 Abs. 1 Buchst. f"
    assert en_ref("Art. 3(56)") == "Art. 3(56)"


def test_a_numbered_definition_is_found_in_german_prose():
    text = "Das sagt Art. 3 Nr. 56, und Art. 5 Abs. 1 Buchst. f verbietet es."
    assert [ref for _, ref in find_german_citations(text)] == ["Art. 3(56)", "Art. 5(1)(f)"]
