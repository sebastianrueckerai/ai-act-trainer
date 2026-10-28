import pytest

from app.content.citations import parse_citation
from app.corpus.search import SearchIndex


@pytest.fixture(scope="module")
def index(library) -> SearchIndex:
    return SearchIndex.build(library)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Betreiberpflichten", "ai_act:art_26"),
        ("KI-Kompetenz", "ai_act:art_4"),
        ("verbotene Praktiken", "ai_act:art_5"),
        pytest.param(
            "Beschäftigtendatenschutz",
            "bdsg:sec_26",
            marks=pytest.mark.xfail(
                strict=True,
                reason="BDSG § 26 never writes Datenschutz, it writes Datenverarbeitung, "
                "so the query's second half scores zero against it.",
            ),
        ),
        ("Mitbestimmung technische Einrichtungen", "betrvg:sec_87"),
        ("Geschäftsgeheimnis Definition", "geschgehg:sec_2"),
    ],
)
def test_a_query_finds_the_right_article_in_the_top_five(index, query, expected):
    hits = index.search(query, limit=5)
    assert expected in [hit.node_id for hit in hits]


def test_a_query_outside_the_library_returns_nothing(index):
    hits = index.search("Quantenphysik Zinsberechnung", limit=5)
    assert hits == []


def test_a_hit_carries_a_citable_reference(index):
    hits = index.search("Betreiberpflichten", limit=1)
    assert hits[0].ref == "Art. 26"
    assert parse_citation(hits[0].ref).node_id == "ai_act:art_26"


def test_paragraphs_are_not_indexed_separately(index):
    hits = index.search("Betreiberpflichten", limit=20)
    assert all("." not in hit.node_id.split(":", 1)[1] for hit in hits)
