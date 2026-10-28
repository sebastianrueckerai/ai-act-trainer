import pytest
from pydantic import ValidationError

from app.corpus.model import Act, Article, Block, Division, Library, Paragraph, Point


def make_library() -> Library:
    point = Point(
        id="art_5.1.a",
        label="a",
        marker="(a)",
        blocks=[Block(text="the placing on the market")],
    )
    paragraph = Paragraph(
        id="art_5.1",
        number=1,
        blocks=[Block(text="The following practices are prohibited:"), Block(points=[point])],
    )
    article = Article(
        id="art_5",
        number="5",
        title="Prohibited AI practices",
        division_id="cpt_II",
        paragraphs=[paragraph],
    )
    division = Division(
        id="cpt_II",
        number="II",
        title="PROHIBITED AI PRACTICES",
    )
    act = Act(
        id="ai_act",
        kind="regulation",
        short_name="AI Act",
        title="Regulation (EU) 2024/1689",
        jurisdiction="eu",
        lang="en",
        version="02024R1689-20260727",
        source_url="https://eur-lex.europa.eu/eli/reg/2024/1689",
        attribution="© European Union",
        divisions=[division],
        articles=[article],
    )
    return Library(acts={act.id: act})


def test_index_contains_every_node_with_parent_links():
    index = make_library().index()
    assert set(index) == {
        "ai_act",
        "ai_act:cpt_II",
        "ai_act:art_5",
        "ai_act:art_5.1",
        "ai_act:art_5.1.a",
    }
    assert index["ai_act:art_5.1.a"].parent_id == "ai_act:art_5.1"
    assert index["ai_act:art_5.1"].parent_id == "ai_act:art_5"
    assert index["ai_act:art_5"].parent_id == "ai_act:cpt_II"
    assert index["ai_act:cpt_II"].parent_id == "ai_act"
    assert index["ai_act"].parent_id is None
    assert index["ai_act:art_5"].kind == "article"
    assert index["ai_act:art_5"].title == "Article 5: Prohibited AI practices"


def test_node_text_of_a_paragraph_includes_its_points():
    library = make_library()
    node = library.node("ai_act:art_5.1")
    assert node is not None
    assert node.text == "The following practices are prohibited: (a) the placing on the market"
    assert library.node("ai_act:art_99") is None


def test_a_library_indexes_every_act_under_a_prefixed_id(library):
    assert set(library.acts) == {
        "ai_act",
        "gdpr",
        "kimig",
        "bdsg",
        "betrvg",
        "geschgehg",
        "qa",
    }
    assert library.node("ai_act:art_26.7") is not None
    assert library.node("kimig:sec_2.1") is not None
    assert library.node("qa:item_18") is not None
    assert library.node("art_26.7") is None


def test_every_node_knows_its_act(library):
    node = library.node("ai_act:art_26.7")
    assert node.act_id == "ai_act"


def test_an_act_answers_to_its_own_id(library):
    act = library.node("ai_act")
    assert act.kind == "act"
    assert act.act_id == "ai_act"
    assert act.parent_id is None
    assert act.title == library.acts["ai_act"].title
    assert library.node("kimig").title.startswith("Gesetz zur Marktüberwachung")


def test_every_act_has_one_root_and_every_other_node_has_a_parent(library):
    index = library.index()
    assert sorted(node.id for node in index.values() if node.parent_id is None) == [
        "ai_act",
        "bdsg",
        "betrvg",
        "gdpr",
        "geschgehg",
        "kimig",
        "qa",
    ]
    for node in index.values():
        assert node.parent_id is None or node.parent_id in index, node.id


def test_a_top_level_node_hangs_off_its_act(library):
    assert library.node("ai_act:cpt_I").parent_id == "ai_act"
    assert library.node("ai_act:anx_I").parent_id == "ai_act"
    assert library.node("ai_act:rct_20").parent_id == "ai_act"
    assert library.node("kimig:cpt_1").parent_id == "kimig"
    assert library.node("qa:item_18").parent_id == "qa"


def test_no_division_is_a_dead_end(library):
    for node in library.index().values():
        if node.kind == "division":
            assert library.children(node.id), f"{node.id} has no children"


def test_a_statute_division_nests_three_deep(library):
    teil = library.node("bdsg:cpt_2")
    assert teil is not None
    kapitel = library.children("bdsg:cpt_2")
    assert kapitel and all(child.kind == "division" for child in kapitel)
    abschnitte = library.children(kapitel[0].id)
    assert abschnitte and all(child.kind == "division" for child in abschnitte)
    assert library.children(abschnitte[0].id)


def test_a_division_reports_the_number_the_law_prints(library):
    numbers = {d.id: d.number for d in library.acts["bdsg"].divisions}
    assert numbers["cpt_1"] == "1"
    assert library.acts["ai_act"].divisions[0].number == "I"


def test_the_regulation_keeps_its_division_ids(library):
    assert library.node("ai_act:cpt_III") is not None
    assert library.node("ai_act:cpt_III.sct_3") is not None
    # 13 chapters and 14 annexes. No article of the Regulation stands outside a chapter.
    assert len(library.children("ai_act")) == 27
    assert len(library.children("ai_act:cpt_III")) == 5
    assert len(library.children("ai_act:cpt_III.sct_3")) == 12


def test_a_walk_from_an_act_reaches_every_node_but_a_recital(library):
    reached: set[str] = set()
    for act_id in library.acts:
        stack = [act_id]
        while stack:
            current = stack.pop()
            reached.add(current)
            stack.extend(child.id for child in library.children(current))
    unreached = [node for node in library.index().values() if node.id not in reached]
    # A recital is reached through the article it explains or by search, never by walking.
    assert {node.kind for node in unreached} == {"recital"}
    assert len(unreached) == 180


def test_every_division_parent_resolves(library):
    for act in library.acts.values():
        ids = {division.id for division in act.divisions}
        for division in act.divisions:
            assert division.parent_id is None or division.parent_id in ids


def test_children_of_an_act_without_divisions_are_its_articles(library):
    assert len(library.children("qa")) == 37
    assert library.children("qa")[0].id == "qa:item_1"


def test_a_statute_section_hangs_off_its_division(library):
    # § 2 stands in Teil 2, Abschnitt 1, and a section belongs to the innermost division.
    assert library.node("kimig:sec_2").parent_id == "kimig:cpt_2.sct_1"
    assert library.children("kimig:cpt_1")[0].id == "kimig:sec_1"


def test_a_library_record_is_frozen(library):
    article = library.acts["ai_act"].articles[0]
    with pytest.raises(ValidationError):
        article.title = "changed"


def test_node_titles_speak_the_language_of_the_act(library):
    assert library.node("ai_act:art_26.7").title.startswith("Artikel 26:")
    assert library.node("ai_act:rct_20").title == "Erwägungsgrund 20"
    assert library.node("ai_act:anx_III.4").title.startswith("Anhang III:")
    assert library.node("kimig:sec_2").title.startswith("§ 2 ")
    assert library.node("qa:item_18").title.endswith("?")
