from pathlib import Path

from app.corpus.build import build_library, load_library

CORPUS_DIR = Path(__file__).resolve().parents[3] / "corpus"


def test_build_library_has_every_act():
    library = build_library(CORPUS_DIR)
    assert set(library.acts) == {
        "ai_act",
        "gdpr",
        "kimig",
        "bdsg",
        "betrvg",
        "geschgehg",
        "qa",
    }
    ai_act = library.acts["ai_act"]
    assert ai_act.lang == "de"
    assert ai_act.version == "02024R1689-20260727"
    assert ai_act.jurisdiction == "eu"
    # 13 chapters and 16 sections: 5 under Chapter III, 4 under V, 2 under VII, 5 under IX.
    assert len(ai_act.divisions) == 29
    assert len(ai_act.articles) == 119
    assert len(ai_act.annexes) == 14
    assert len(ai_act.recitals) == 180
    assert library.acts["kimig"].jurisdiction == "de"
    assert len(library.acts["kimig"].articles) == 20
    assert len(library.acts["bdsg"].articles) == 86
    assert len(library.acts["betrvg"].articles) == 145
    assert len(library.acts["geschgehg"].articles) == 23
    assert len(library.acts["qa"].articles) == 37


def test_an_act_that_bundles_no_recitals_has_none():
    library = build_library(CORPUS_DIR)
    assert library.acts["kimig"].recitals == []
    assert library.acts["qa"].recitals == []


def test_the_index_spans_every_act():
    library = build_library(CORPUS_DIR)
    index = library.index()
    assert index["ai_act:art_26.2"].kind == "paragraph"
    assert index["ai_act:rct_20"].kind == "recital"
    assert index["ai_act:anx_III.4"].kind == "paragraph"
    assert index["kimig:sec_2.1"].kind == "paragraph"
    assert index["bdsg:sec_26.1"].kind == "paragraph"
    assert index["betrvg:sec_87.1.6"].kind == "point"
    assert index["betrvg:cpt_1"].kind == "division"
    assert index["qa:item_1"].kind == "article"
    # Seven acts, one node each. The Regulation adds 29 divisions, 119 articles, 14 annexes,
    # 180 recitals, 788 paragraphs and 525 points, which is 1655. The GDPR adds 26 divisions,
    # 99 articles, 415 paragraphs and 363 points, which is 903. The Commission questions add
    # 37 items with one paragraph each. A German statute adds its divisions, its sections, its
    # paragraphs and the Nummern of those paragraphs: the KI-MIG 10, 20, 76 and 62, the BDSG
    # 25, 86, 289 and 256, the BetrVG 31, 145, 387 and 198, the GeschGehG 4, 23, 54 and 61.
    assert len(index) == 7 + 1655 + 903 + 74 + 168 + 656 + 761 + 142


def test_load_library():
    library = load_library(CORPUS_DIR)
    assert library.index()["ai_act:art_4"].title == "Artikel 4: KI-Kompetenz"


def test_the_gdpr_is_in_the_library():
    library = build_library(CORPUS_DIR)
    gdpr = library.acts["gdpr"]
    # 11 chapters and 15 sections: 5 under Chapter III, 5 under IV, 2 under VI, 3 under VII.
    assert len(gdpr.divisions) == 26
    assert len([d for d in gdpr.divisions if d.parent_id is None]) == 11
    assert len(gdpr.articles) == 99
    art_88 = library.node("gdpr:art_88")
    assert art_88.title == "Artikel 88: Datenverarbeitung im Beschäftigungskontext"
    assert library.node("gdpr:art_5") is not library.node("ai_act:art_5")


def test_the_gdpr_has_no_recitals_bundled():
    library = build_library(CORPUS_DIR)
    assert library.acts["gdpr"].recitals == []
