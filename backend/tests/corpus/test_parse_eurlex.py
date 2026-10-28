from pathlib import Path

from lxml import html

from app.corpus.build import build_library
from app.corpus.parse_eurlex import ANNEXES, ARTICLES, parse_consolidated
from app.corpus.textutil import normalize

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[3]
CORPUS_DIR = REPO_ROOT / "corpus"
RAW = CORPUS_DIR / "raw" / "02024R1689-20260727"
MARKERS = './/*[contains(@class,"modref") or contains(@class,"superscript")]'
MIN_BLOCK = 25


def test_fixture_article_5_structure():
    divisions, articles, annexes = parse_consolidated(FIXTURES / "article_5_snippet.xhtml")
    assert [d.id for d in divisions] == ["cpt_II"]
    assert divisions[0].number == "II"
    assert divisions[0].parent_id is None
    (article,) = articles
    assert article.id == "art_5"
    assert article.number == "5"
    assert article.title == "Prohibited AI practices"
    assert article.division_id == "cpt_II"
    assert [p.number for p in article.paragraphs] == [1, 2]
    first = article.paragraphs[0]
    assert first.id == "art_5.1"
    assert first.text.startswith("The following AI practices shall be prohibited")
    assert [p.label for p in first.points] == ["a", "b", "ba"]
    assert first.points[0].id == "art_5.1.a"
    assert first.points[0].text.startswith("the placing on the market")
    assert annexes == []


def test_full_file_counts():
    divisions, articles, annexes = parse_consolidated(RAW / "de.xhtml")
    assert len([d for d in divisions if d.parent_id is None]) == 13
    assert len(articles) >= 113
    assert len(annexes) == 14
    ids = [a.id for a in articles]
    assert ids[0] == "art_1"
    assert "art_4" in ids and "art_26" in ids and "art_113" in ids
    assert len(ids) == len(set(ids))
    for article in articles:
        assert article.paragraphs, article.id
        assert article.division_id.startswith("cpt_")


def test_article_4_after_omnibus():
    _, articles, _ = parse_consolidated(RAW / "de.xhtml")
    article = next(a for a in articles if a.id == "art_4")
    assert article.title == "KI-Kompetenz"
    assert article.paragraphs[0].id == "art_4.1"
    assert article.paragraphs[0].text.startswith(
        "Die Anbieter und Betreiber von KI-Systemen ergreifen Maßnahmen, um die "
        "Entwicklung der KI-Kompetenz ihres Personals und "
    )


def test_annex_iii_point_4_is_employment():
    _, _, annexes = parse_consolidated(RAW / "de.xhtml")
    annex = next(a for a in annexes if a.id == "anx_III")
    assert annex.number == "III"
    point_4 = next(p for p in annex.paragraphs if p.number == 4)
    assert point_4.id == "anx_III.4"
    assert "Beschäftigung" in point_4.text
    assert point_4.points and point_4.points[0].id == "anx_III.4.a"


def test_article_3_definitions_are_numbered_paragraphs():
    _, articles, _ = parse_consolidated(RAW / "de.xhtml")
    article = next(a for a in articles if a.id == "art_3")
    assert article.paragraphs[0].id == "art_3.0" and article.paragraphs[0].points == []
    four = next(p for p in article.paragraphs if p.id == "art_3.4")
    assert four.number == 4
    assert "betreiber" in four.text.lower()
    assert not any(p.id.startswith("art_3.0.") for p in article.paragraphs)


def test_article_3_lead_sentence_stays_unnumbered():
    _, articles, _ = parse_consolidated(RAW / "de.xhtml")
    article = next(a for a in articles if a.id == "art_3")
    lead = article.paragraphs[0]
    assert lead.number is None
    assert lead.text.startswith("Für die Zwecke dieser Verordnung bezeichnet der Ausdruck")
    assert article.paragraphs[1].id == "art_3.1"
    assert article.paragraphs[1].text.startswith("„KI-System“ ein maschinengestütztes System")


def test_article_5_keeps_subparagraphs_that_follow_the_points():
    _, articles, _ = parse_consolidated(RAW / "de.xhtml")
    article = next(a for a in articles if a.id == "art_5")
    second = next(p for p in article.paragraphs if p.id == "art_5.2")
    systems = "biometrischer Echtzeit-Fernidentifizierungssysteme in öffentlich zugänglichen Räumen"
    assert second.text.startswith(f"Die Verwendung {systems}")
    assert second.flat_text().count(systems) >= 2


def test_annex_xiv_includes_the_code_tables():
    _, _, annexes = parse_consolidated(RAW / "de.xhtml")
    annex = next(a for a in annexes if a.id == "anx_XIV")
    words = sum(len(p.flat_text().split()) for p in annex.paragraphs)
    assert words > 400
    assert "AIP 0102" in " ".join(p.flat_text() for p in annex.paragraphs)


def test_annex_vi_items_are_numbered_paragraphs():
    _, _, annexes = parse_consolidated(RAW / "de.xhtml")
    annex_vi = next(a for a in annexes if a.id == "anx_VI")
    second = next(p for p in annex_vi.paragraphs if p.id == "anx_VI.2")
    assert second.number == 2
    assert second.text
    annex_i = next(a for a in annexes if a.id == "anx_I")
    assert len(annex_i.paragraphs) > 1


def test_section_titles_are_present():
    divisions, _, _ = parse_consolidated(RAW / "de.xhtml")
    # 5 sections under Chapter III, 4 under V, 2 under VII and 5 under IX.
    sections = [d for d in divisions if d.parent_id is not None]
    assert len(sections) == 16
    assert all(section.title for section in sections), [s.id for s in sections if not s.title]
    first = next(s for s in sections if s.id == "cpt_III.sct_1")
    assert first.number == "1"
    assert first.parent_id == "cpt_III"
    assert first.title == "Einstufung von KI-Systemen als Hochrisiko-KI-Systeme"


def test_an_article_inside_a_section_names_the_section():
    divisions, articles, _ = parse_consolidated(RAW / "de.xhtml")
    with_sections = {d.parent_id for d in divisions if d.parent_id is not None}
    assert with_sections == {"cpt_III", "cpt_V", "cpt_VII", "cpt_IX"}
    # No article names one of those four, because every article of theirs sits in a section.
    for article in articles:
        assert article.division_id not in with_sections, article.id
    assert next(a for a in articles if a.id == "art_16").division_id == "cpt_III.sct_3"
    assert next(a for a in articles if a.id == "art_5").division_id == "cpt_II"
    # Chapter II holds Article 5 and nothing else, so a stray article there would show up.
    library = build_library(CORPUS_DIR)
    assert [node.id for node in library.children("ai_act:cpt_II")] == ["ai_act:art_5"]


def test_every_annex_has_a_title():
    _, _, annexes = parse_consolidated(RAW / "de.xhtml")
    assert all(a.title for a in annexes)
    assert next(a for a in annexes if a.id == "anx_XIV").title == "ANHANG XIV"
    assert next(a for a in annexes if a.id == "anx_X").title.startswith(
        "Rechtsvorschriften der Union"
    )
    assert next(a for a in annexes if a.id == "anx_III").title.startswith("Hochrisiko-KI-Systeme")


def test_annex_ii_bullets_are_numbered_by_position():
    _, _, annexes = parse_consolidated(RAW / "de.xhtml")
    annex = next(a for a in annexes if a.id == "anx_II")
    assert [p.id for p in annex.paragraphs[:3]] == ["anx_II.0", "anx_II.1", "anx_II.2"]
    assert annex.paragraphs[0].number is None
    assert annex.paragraphs[1].number == 1


def test_article_5_paragraph_1_reads_its_exception_after_the_list():
    act = build_library(CORPUS_DIR).acts["ai_act"]
    paragraph = next(
        p for a in act.articles if a.id == "art_5" for p in a.paragraphs if p.id == "art_5.1"
    )
    assert paragraph.text.rstrip().endswith(":")
    assert "unbeschadet des Artikels 9" not in paragraph.text
    flat = paragraph.flat_text()
    assert flat.index("(a)") < flat.index("unbeschadet des Artikels 9")


def test_article_43_paragraph_1_keeps_its_middle_text_between_the_two_lists():
    act = build_library(CORPUS_DIR).acts["ai_act"]
    paragraph = next(
        p for a in act.articles if a.id == "art_43" for p in a.paragraphs if p.id == "art_43.1"
    )
    kinds = ["points" if block.points else "text" for block in paragraph.blocks]
    assert kinds == ["text", "points", "text", "points", "text"]
    flat = paragraph.flat_text()
    first_list = flat.index("(a)")
    middle = flat.index("befolgt der Anbieter das Konformitätsbewertungsverfahren")
    assert first_list < middle < flat.rindex("(a)")


def test_a_paragraph_without_a_trailing_block_has_one_block():
    act = build_library(CORPUS_DIR).acts["ai_act"]
    paragraph = next(p for a in act.articles if a.id == "art_4" for p in a.paragraphs)
    assert [bool(block.points) for block in paragraph.blocks] == [False]
    assert paragraph.flat_text() == paragraph.text


def test_article_22_paragraph_3_reads_its_closing_sentence_after_the_list():
    act = build_library(CORPUS_DIR).acts["ai_act"]
    paragraph = next(
        p for a in act.articles if a.id == "art_22" for p in a.paragraphs if p.id == "art_22.3"
    )
    closing = "Mit dem Auftrag wird der Bevollmächtigte ermächtigt"
    assert paragraph.text.rstrip().endswith(
        "ermächtigt der Auftrag den Bevollmächtigten zumindest zur Wahrnehmung folgender Aufgaben:"
    )
    assert closing not in paragraph.text
    flat = paragraph.flat_text()
    assert flat.index("(a)") < flat.index(closing)


def test_annex_xi_point_2_reads_its_closing_sentence_after_the_list():
    act = build_library(CORPUS_DIR).acts["ai_act"]
    paragraph = next(
        p for a in act.annexes if a.id == "anx_XI" for p in a.paragraphs if p.id == "anx_XI.2"
    )
    closing = "Wenn der Energieverbrauch des Modells nicht bekannt ist"
    assert paragraph.text.rstrip().endswith(
        "Informationen zum Entwicklungsverfahren, einschließlich der folgenden Elemente:"
    )
    assert closing not in paragraph.text
    flat = paragraph.flat_text()
    assert flat.index("(e)") < flat.index(closing)


def test_points_is_every_point_across_every_group_in_source_order():
    act = build_library(CORPUS_DIR).acts["ai_act"]
    paragraph = next(
        p for a in act.articles if a.id == "art_43" for p in a.paragraphs if p.id == "art_43.1"
    )
    assert [point.label for point in paragraph.points] == ["a", "b", "a", "b", "c", "d"]


def _flatten(nodes: list) -> list:
    """Every paragraph and point of an article or annex, in document order."""
    flat = []
    for node in nodes:
        flat.append(node)
        flat.extend(_flatten(node.points))
    return flat


def _all_nodes(articles: list, annexes: list) -> list:
    return [node for parent in [*articles, *annexes] for node in _flatten(parent.paragraphs)]


def test_node_ids_are_unique():
    _, articles, annexes = parse_consolidated(RAW / "de.xhtml")
    ids = [node.id for node in _all_nodes(articles, annexes)]
    assert len(ids) == len(set(ids))
    assert {"art_26.2", "art_5.1.a", "art_3.4", "anx_III.4", "anx_III.4.a"} <= set(ids)


def _source_texts(container) -> list[str]:
    """Every text node of the container, minus the markers and footnote refs text_of drops."""
    dropped = {node for marker in container.xpath(MARKERS) for node in marker.iter()}
    found = []
    for node in container.iter():
        if node in dropped:
            continue
        for raw in (node.text, node.tail):
            text = normalize(raw) if raw else ""
            if len(text) >= MIN_BLOCK:
                found.append(text)
    return found


def test_no_source_text_block_is_dropped():
    """Every text node of an article or annex reaches the parsed act."""
    path = RAW / "de.xhtml"
    _, articles, annexes = parse_consolidated(path)
    parsed = " || ".join(
        [node.flat_text() for node in _all_nodes(articles, annexes)]
        + [parent.title for parent in [*articles, *annexes]]
    )
    root = html.parse(str(path)).getroot()
    containers = root.xpath(ARTICLES) + root.xpath(ANNEXES)
    dropped = [
        text
        for container in containers
        for text in _source_texts(container)
        if text[:MIN_BLOCK] not in parsed
    ]
    assert [text[:80] for text in dropped] == []


def test_annex_vii_numbered_headings_open_its_items():
    _, _, annexes = parse_consolidated(RAW / "de.xhtml")
    annex = next(a for a in annexes if a.id == "anx_VII")
    assert [p.id for p in annex.paragraphs] == [f"anx_VII.{n}" for n in range(1, 6)]
    assert [p.number for p in annex.paragraphs] == [1, 2, 3, 4, 5]
    assert annex.paragraphs[0].flat_text() == (
        "Einleitung Die Konformität auf der Grundlage einer Bewertung des "
        "Qualitätsmanagementsystems und einer Bewertung der technischen Dokumentation "
        "entspricht dem Konformitätsbewertungsverfahren gemäß den Nummern 2 bis 5."
    )


def test_annex_vii_letter_lists_are_points_of_the_item_above_them():
    _, _, annexes = parse_consolidated(RAW / "de.xhtml")
    annex = next(a for a in annexes if a.id == "anx_VII")
    third = next(p for p in annex.paragraphs if p.id == "anx_VII.3")
    assert [point.label for point in third.points] == ["a", "b", "c", "d", "e", "f"]
    assert third.points[0].id == "anx_VII.3.a"
    fourth = next(p for p in annex.paragraphs if p.id == "anx_VII.4")
    assert [point.label for point in fourth.points] == ["a", "b", "c"]
    assert fourth.flat_text().startswith(
        "Kontrolle der technischen Dokumentation 4.1. Zusätzlich zu dem unter Nummer 3"
    )
    assert "5.1." not in fourth.flat_text()
    fifth = next(p for p in annex.paragraphs if p.id == "anx_VII.5")
    assert fifth.flat_text().startswith(
        "Überwachung des genehmigten Qualitätsmanagementsystems 5.1. Mit der unter Nummer 3"
    )


def test_annex_x_numbered_headings_open_its_items():
    _, _, annexes = parse_consolidated(RAW / "de.xhtml")
    annex = next(a for a in annexes if a.id == "anx_X")
    assert [p.id for p in annex.paragraphs] == [f"anx_X.{n}" for n in range(1, 8)]
    first = annex.paragraphs[0]
    assert first.text == "Schengener Informationssystem"
    assert [point.label for point in first.points] == ["a", "b", "c"]
    assert first.points[0].id == "anx_X.1.a"
    assert "Visa-Informationssystem" not in first.flat_text()
    third = next(p for p in annex.paragraphs if p.id == "anx_X.3")
    assert third.flat_text().startswith("Eurodac Verordnung (EU) 2024/1358")
    seventh = next(p for p in annex.paragraphs if p.id == "anx_X.7")
    assert [point.label for point in seventh.points] == ["a", "b"]


def test_annex_i_section_b_heading_leaves_item_12_alone():
    _, _, annexes = parse_consolidated(RAW / "de.xhtml")
    annex = next(a for a in annexes if a.id == "anx_I")
    twelfth = next(p for p in annex.paragraphs if p.id == "anx_I.12")
    assert twelfth.flat_text().endswith("(ABl. L 117 vom 5.5.2017, S. 176)")
    assert "Abschnitt B" not in twelfth.flat_text()
    lead = annex.paragraphs[0]
    assert lead.id == "anx_I.0"
    assert "Abschnitt A — Liste der Harmonisierungsrechtsvorschriften" in lead.text
    assert "Abschnitt B — Liste anderer Harmonisierungsrechtsvorschriften" in lead.text


def test_annex_viii_section_headings_leave_the_items_alone():
    _, _, annexes = parse_consolidated(RAW / "de.xhtml")
    annex = next(a for a in annexes if a.id == "anx_VIII")
    thirteenth = next(p for p in annex.paragraphs if p.id == "anx_VIII.13")
    assert thirteenth.flat_text() == "Eine URL-Adresse für zusätzliche Informationen (fakultativ)."
    twentieth = next(p for p in annex.paragraphs if p.id == "anx_VIII.20")
    assert twentieth.flat_text() == (
        "der Status des KI-Systems (in Verkehr/in Betrieb; nicht mehr in Verkehr/in Betrieb, "
        "zurückgerufen)."
    )
    lead = annex.paragraphs[0]
    assert [lead.text.count(f"Abschnitt {letter} —") for letter in "ABC"] == [1, 1, 1]
    assert "Für KI-Systeme, die gemäß Artikel 49 Absatz 2 zu registrieren sind" in lead.text


def test_annex_xi_section_2_items_are_items_of_the_annex():
    _, _, annexes = parse_consolidated(RAW / "de.xhtml")
    annex = next(a for a in annexes if a.id == "anx_XI")
    assert [p.id for p in annex.paragraphs] == [f"anx_XI.{n}" for n in range(0, 6)]
    second = next(p for p in annex.paragraphs if p.id == "anx_XI.2")
    assert "Abschnitt 2" not in second.flat_text()
    third = next(p for p in annex.paragraphs if p.id == "anx_XI.3")
    assert third.flat_text().startswith(
        "Eine ausführliche Beschreibung der Prüfstrategien, einschließlich der Prüfungsergebnisse"
    )
    assert annex.paragraphs[0].text.count("Abschnitt") == 2


def test_annex_section_headings_have_no_id_of_their_own():
    act = build_library(CORPUS_DIR).acts["ai_act"]
    index = act.index()
    assert "ai_act:anx_I.A" not in index
    assert "ai_act:anx_VIII.B" not in index
    assert "ai_act:anx_VIII.C" not in index
    assert "Abschnitt A —" in index["ai_act:anx_I.0"].text
    assert index["ai_act:anx_XI.1"].text.startswith("Eine allgemeine Beschreibung des KI-Modells")
