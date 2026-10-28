from pathlib import Path

import pytest

from app.corpus.manifest import ActSource, load_corpus_manifest
from app.corpus.parse_formex import parse_recitals
from app.corpus.parse_gii import parse_gii
from app.corpus.parse_qa import parse_qa

CORPUS_DIR = Path(__file__).resolve().parents[3] / "corpus"
RAW = CORPUS_DIR / "raw"

# Recital 8 glues the text before its footnote directly onto the footnote body with no
# separator. This is the word pair that results if the footnote is not stripped.
GLUED_RECITAL_8 = "einzunehmenEuropäischer"


def source(act_id: str) -> ActSource:
    return next(act for act in load_corpus_manifest(CORPUS_DIR).acts if act.id == act_id)


def test_recitals_count_and_numbering():
    recitals = parse_recitals(RAW / "32024R1689" / "formex-de.zip")
    assert len(recitals) == 180
    assert recitals[0].id == "rct_1" and recitals[0].number == 1
    assert recitals[-1].id == "rct_180"
    assert not recitals[19].text.startswith("(20)")
    assert len(recitals[19].text) > 100


def test_recitals_carry_no_footnote_text():
    recitals = parse_recitals(RAW / "32024R1689" / "formex-de.zip")
    eight = recitals[7].text
    assert "EUCO 13/20" not in eight
    assert GLUED_RECITAL_8 not in eight
    for recital in recitals:
        assert "EUCO" not in recital.text and " p. " not in recital.text, recital.id


def test_kimig_sections():
    divisions, articles = parse_gii(RAW / "kimig" / "BJNR0DF0B0026.xml")
    assert len(articles) == 20
    two = next(article for article in articles if article.id == "sec_2")
    assert two.number == "2"
    assert two.paragraphs[0].id == "sec_2.1"
    assert "Bundesnetzagentur" in two.paragraphs[0].text
    assert divisions[0].id == "cpt_1"
    assert divisions[0].title == "Teil 1 Allgemeine Vorschriften"
    assert [a.id for a in articles if a.division_id == "cpt_1"] == ["sec_1"]
    # § 2 stands in Teil 2, Abschnitt 1, and a section belongs to the innermost division.
    assert divisions[2].id == "cpt_2.sct_1"
    assert divisions[2].title == "Abschnitt 1 Zuständige Stellen"
    assert divisions[2].parent_id == "cpt_2"
    assert two.division_id == "cpt_2.sct_1"


def test_the_kimig_keeps_its_node_ids(library):
    act = library.acts["kimig"]
    assert act.kind == "statute"
    assert act.attribution.startswith("§ 5 UrhG")
    assert library.node("kimig:sec_2").title.startswith("§ 2 ")
    assert "Bundesnetzagentur" in library.node("kimig:sec_2.1").text


def test_the_bdsg_carries_the_employee_data_section(library):
    node = library.node("bdsg:sec_26")
    assert node is not None
    assert "Beschäftigungsverhältnis" in node.title
    assert node.title == "§ 26 Datenverarbeitung für Zwecke des Beschäftigungsverhältnisses"


def test_the_betrvg_carries_the_co_determination_section(library):
    node = library.node("betrvg:sec_87")
    assert "Mitbestimmungsrechte" in node.title
    # § 87 Absatz 1 Nummer 6, the works council's say over monitoring by technical means.
    assert (
        "Einführung und Anwendung von technischen Einrichtungen, die dazu bestimmt sind, "
        "das Verhalten oder die Leistung der Arbeitnehmer zu überwachen"
        in library.node("betrvg:sec_87.1").text
    )


def test_the_geschgehg_defines_a_trade_secret(library):
    assert library.node("geschgehg:sec_2").title == "§ 2 Begriffsbestimmungen"
    assert "Geschäftsgeheimnis eine Information" in library.node("geschgehg:sec_2.1").text


def test_a_statute_keeps_its_divisions(library):
    divisions = library.children("bdsg")
    assert divisions != []
    assert divisions[0].kind == "division"
    # The BDSG prints four Teile, and the Kapitel stand below them.
    assert [division.title for division in divisions] == [
        "Teil 1 Gemeinsame Bestimmungen",
        "Teil 2 Durchführungsbestimmungen für Verarbeitungen zu Zwecken gemäß Artikel 2 der "
        "Verordnung (EU) 2016/679",
        "Teil 3 Bestimmungen für Verarbeitungen zu Zwecken gemäß Artikel 1 Absatz 1 der "
        "Richtlinie (EU) 2016/680",
        "Teil 4 Besondere Bestimmungen für Verarbeitungen im Rahmen von nicht in die "
        "Anwendungsbereiche der Verordnung (EU) 2016/679 und der Richtlinie (EU) 2016/680 "
        "fallenden Tätigkeiten",
    ]
    kapitel = library.children("bdsg:cpt_1")[0]
    assert kapitel.title == "Kapitel 1 Anwendungsbereich und Begriffsbestimmungen"
    assert [node.id for node in library.children(kapitel.id)] == ["bdsg:sec_1", "bdsg:sec_2"]
    # §§ 85 and 86 stand directly under Teil 4, which opens no Kapitel.
    assert [node.id for node in library.children("bdsg:cpt_4")] == ["bdsg:sec_85", "bdsg:sec_86"]
    betrvg = library.node("betrvg:sec_87")
    assert library.node(betrvg.parent_id).title == "Dritter Abschnitt Soziale Angelegenheiten"


def test_a_statute_division_is_numbered_as_the_law_prints_it(library):
    # The BDSG writes "Teil 1" and "Kapitel 1", the BetrVG writes "Erster Teil".
    bdsg = {division.id: division.number for division in library.acts["bdsg"].divisions}
    assert bdsg["cpt_1"] == "1"
    assert bdsg["cpt_2.sct_1"] == "1"
    assert bdsg["cpt_2.sct_1.sct_2"] == "2"
    betrvg = {division.id: division.number for division in library.acts["betrvg"].divisions}
    assert betrvg["cpt_1"] == "Erster"
    assert betrvg["cpt_4.sct_5.sct_3"] == "Dritter"


def test_a_gliederungskennzahl_of_no_whole_levels_raises(tmp_path: Path):
    statute = tmp_path / "statute.xml"
    statute.write_text(
        "<dokumente><norm><metadaten><gliederungseinheit>"
        "<gliederungskennzahl>0100</gliederungskennzahl>"
        "<gliederungsbez>Teil 1</gliederungsbez>"
        "</gliederungseinheit></metadaten></norm></dokumente>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="three digits per level"):
        parse_gii(statute)


def test_a_division_that_stands_under_no_division_raises(tmp_path: Path):
    statute = tmp_path / "statute.xml"
    statute.write_text(
        "<dokumente><norm><metadaten><gliederungseinheit>"
        "<gliederungskennzahl>010020</gliederungskennzahl>"
        "<gliederungsbez>Kapitel 2</gliederungsbez>"
        "</gliederungseinheit></metadaten></norm></dokumente>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="stands under no division"):
        parse_gii(statute)


def test_a_repealed_section_is_not_in_the_library(library):
    for act_id in ("bdsg", "betrvg", "geschgehg"):
        for article in library.acts[act_id].articles:
            assert article.title.strip() not in {"(weggefallen)", "(aufgehoben)"}
    # The BetrVG prints §§ 6, 10 and 12 as "(weggefallen)" and nothing else.
    for local_id in ("sec_6", "sec_10", "sec_12"):
        assert library.node(f"betrvg:{local_id}") is None
    assert library.node("betrvg:sec_5") is not None
    assert library.node("betrvg:sec_7") is not None


def test_a_betrvg_absatz_answers_to_the_label_the_law_prints(library):
    # The BetrVG inserts a lettered Absatz by amendment, and § 95 Absatz 2a is one of the few
    # German provisions that name AI. A position would name every later Absatz wrongly.
    assert library.node("betrvg:sec_95.2a").text == (
        "Die Absätze 1 und 2 finden auch dann Anwendung, wenn bei der Aufstellung der "
        "Richtlinien nach diesen Absätzen Künstliche Intelligenz zum Einsatz kommt."
    )
    assert library.node("betrvg:sec_95.3").text.startswith(
        "Versetzung im Sinne dieses Gesetzes ist die Zuweisung eines anderen Arbeitsbereichs"
    )
    assert library.node("betrvg:sec_95.4") is None
    assert library.node("betrvg:sec_96.1a").text.startswith(
        "Kommt im Rahmen der Beratung nach Absatz 1 eine Einigung"
    )
    assert library.node("betrvg:sec_96.2").text.startswith(
        "Arbeitgeber und Betriebsrat haben darauf zu achten"
    )
    assert library.node("betrvg:sec_103.2a").text == (
        "Absatz 2 gilt entsprechend, wenn im Betrieb kein Betriebsrat besteht."
    )
    assert library.node("betrvg:sec_103.3").text.startswith(
        "Die Versetzung der in Absatz 1 genannten Personen"
    )


def test_a_section_title_drops_its_footnote_marker(library):
    assert library.node("betrvg:sec_9").title == "§ 9 Zahl der Betriebsratsmitglieder"
    assert library.node("betrvg:sec_21a").title == "§ 21a Übergangsmandat"


def test_an_enbez_that_names_no_single_section_raises(tmp_path: Path):
    statute = tmp_path / "statute.xml"
    statute.write_text(
        "<dokumente><norm><metadaten><enbez>§§ 1 bis 3</enbez></metadaten><textdaten>"
        "<text><Content><P>(weggefallen)</P></Content></text></textdaten></norm></dokumente>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="names no single section"):
        parse_gii(statute)


def test_two_absaetze_that_share_an_id_raise(tmp_path: Path):
    statute = tmp_path / "statute.xml"
    statute.write_text(
        "<dokumente><norm><metadaten><enbez>§ 1</enbez><titel>Begriffe</titel></metadaten>"
        "<textdaten><text><Content><P>Eine Einleitung.</P>"
        "<P>(1) Erster Absatz.</P></Content></text></textdaten></norm></dokumente>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="share the id sec_1.1"):
        parse_gii(statute)


def test_a_numbered_list_keeps_the_space_after_its_number(library):
    text = library.node("bdsg:sec_26.8").text
    assert "sind: 1. Arbeitnehmerinnen und Arbeitnehmer" in text
    assert "2. zu ihrer Berufsbildung Beschäftigte" in text


def test_a_nummer_of_an_absatz_is_its_own_node(library):
    # § 87 Absatz 1 Nummer 6 BetrVG, the works council's say over monitoring by technical means.
    assert library.node("betrvg:sec_87.1.6").text == (
        "Einführung und Anwendung von technischen Einrichtungen, die dazu bestimmt sind, das "
        "Verhalten oder die Leistung der Arbeitnehmer zu überwachen;"
    )
    absatz = library.node("betrvg:sec_87.1")
    assert absatz.text.startswith(
        "Der Betriebsrat hat, soweit eine gesetzliche oder tarifliche Regelung nicht besteht, "
        "in folgenden Angelegenheiten mitzubestimmen:"
    )
    assert "6. Einführung und Anwendung von technischen Einrichtungen" in absatz.text
    assert library.node("betrvg:sec_87.1.14") is not None
    assert library.node("betrvg:sec_87.1.15") is None


def test_a_sentence_below_a_list_stays_below_it(library):
    # § 2 Absatz 3 BDSG closes its two Nummern with a Schlusssatz.
    absatz = library.node("bdsg:sec_2.3")
    assert absatz.text.endswith("Andernfalls gelten sie als öffentliche Stellen der Länder.")
    assert library.node("bdsg:sec_2.3.2").text == (
        "dem Bund die absolute Mehrheit der Anteile gehört oder die absolute Mehrheit der "
        "Stimmen zusteht."
    )


def test_a_nested_list_carries_its_letters(library):
    # § 2 Nummer 1 GeschGehG defines a trade secret in three lettered conditions.
    nummer = library.node("geschgehg:sec_2.1.1")
    assert nummer.text.startswith("Geschäftsgeheimnis eine Information a) die weder insgesamt")
    assert library.node("geschgehg:sec_2.1.1.a").text.startswith(
        "die weder insgesamt noch in der genauen Anordnung"
    )
    assert library.node("geschgehg:sec_2.1.1.c").text == (
        "bei der ein berechtigtes Interesse an der Geheimhaltung besteht;"
    )


def test_a_second_list_in_one_absatz_keeps_the_first(library):
    # § 4 Absatz 1 BDSG prints two lists, and both of them open at "1.". A repeat carries a
    # separator no law prints, so no repeat can read as a Nummer the statute does not print.
    assert library.node("bdsg:sec_4.1.1").text == "zur Aufgabenerfüllung öffentlicher Stellen,"
    assert library.node("bdsg:sec_4.1.1~2").text.startswith(
        "öffentlich zugänglichen großflächigen Anlagen"
    )
    assert library.node("bdsg:sec_4.1.2~2").text.startswith(
        "Fahrzeugen und öffentlich zugänglichen"
    )
    assert library.node("bdsg:sec_4.1.12") is None
    assert library.node("bdsg:sec_4.1.22") is None


def test_an_absatz_that_prints_nothing_but_its_marker_keeps_no_marker(tmp_path: Path):
    statute = tmp_path / "statute.xml"
    statute.write_text(
        "<dokumente><norm><metadaten><enbez>§ 1</enbez><titel>Begriffe</titel></metadaten>"
        "<textdaten><text><Content><P>(1)<DL><DT>1.</DT><DD><LA>erste Nummer;</LA></DD>"
        "<DT>2.</DT><DD><LA>zweite Nummer.</LA></DD></DL></P></Content></text></textdaten>"
        "</norm></dokumente>",
        encoding="utf-8",
    )
    _, articles = parse_gii(statute)
    paragraph = articles[0].paragraphs[0]
    assert paragraph.id == "sec_1.1"
    assert paragraph.text == ""
    assert paragraph.flat_text() == "1. erste Nummer; 2. zweite Nummer."


def test_a_list_term_the_parser_cannot_number_opens_no_node(library):
    # The BetrVG prints its amtliche Hinweise as list terms marked "*)" and "+)".
    section = library.node("betrvg:sec_9")
    assert section.title == "§ 9 Zahl der Betriebsratsmitglieder"
    assert "Gemäß Artikel 14 Satz 2 des Gesetzes zur Reform des Betriebsverfassungsgesetzes" in (
        section.text
    )
    assert [node.id for node in library.children("betrvg:sec_9.1")] == []


def test_qa_items():
    act = parse_qa(RAW / "qa" / "de.html", source("qa"))
    assert act.id == "qa"
    assert act.kind == "guidance"
    assert len(act.articles) == 37
    assert act.articles[0].id == "item_1"
    assert act.articles[0].title.endswith("?")
    assert act.articles[0].paragraphs[0].id == "item_1.1"
    assert len(act.articles[0].paragraphs[0].text) > 50
    assert "CC BY 4.0" in act.attribution
