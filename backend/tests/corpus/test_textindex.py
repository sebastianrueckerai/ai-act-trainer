import pytest

from app.corpus.build import build_library
from app.corpus.textindex import (
    build_vocabulary,
    document_terms,
    expand_query,
    split_compound,
    stem,
    tokenize,
)
from tests.corpus.test_build import CORPUS_DIR


def test_tokenize_lowercases_and_splits_hyphens():
    assert tokenize("Hochrisiko-KI-System und Betreiber") == [
        "hochrisiko",
        "system",
        "und",
        "betreiber",
    ]


def test_tokenize_drops_short_words():
    assert tokenize("KI ist da") == ["ist"]


def test_stem_folds_plural_onto_singular():
    assert stem("Pflichten") == stem("Pflicht")


def test_split_compound_finds_both_halves_in_the_vocabulary():
    vocabulary = {stem("betreiber"), stem("pflichten")}
    assert split_compound("Betreiberpflichten", vocabulary) == [
        stem("betreiber"),
        stem("pflichten"),
    ]


def test_split_compound_accepts_a_linking_s():
    vocabulary = {stem("arbeit"), stem("vertrag")}
    assert split_compound("Arbeitsvertrag", vocabulary) == [stem("arbeit"), stem("vertrag")]


def test_split_compound_refuses_when_one_half_is_not_a_word():
    vocabulary = {stem("betreiber"), stem("pflichten")}
    assert split_compound("Verordnung", vocabulary) is None


def test_split_compound_refuses_halves_under_four_letters():
    vocabulary = {stem("kid"), stem("napping"), stem("kidnapping")}
    assert split_compound("Kidnapping", vocabulary) is None


def test_expand_query_keeps_a_word_the_vocabulary_already_has():
    vocabulary = {stem("betreiber")}
    assert expand_query("Betreiber", vocabulary) == [stem("betreiber")]


def test_expand_query_splits_a_word_the_vocabulary_lacks():
    vocabulary = {stem("betreiber"), stem("pflichten")}
    assert expand_query("Betreiberpflichten", vocabulary) == [
        stem("betreiber"),
        stem("pflichten"),
    ]


def test_expand_query_keeps_an_unknown_word_that_does_not_split():
    vocabulary = {stem("betreiber")}
    assert expand_query("Quantenphysik", vocabulary) == [stem("quantenphysik")]


@pytest.fixture(scope="module")
def vocabulary() -> set[str]:
    library = build_library(CORPUS_DIR)
    return build_vocabulary(node.text for node in library.index().values())


@pytest.mark.parametrize(
    ("query", "expected_stems"),
    [
        ("Betreiberpflichten", ["betreib", "pflicht"]),
        ("Kompetenzanforderungen", ["kompetenz", "anforder"]),
        ("Hochrisikoeinstufung", ["hochrisiko", "einstuf"]),
    ],
)
def test_real_compounds_split_into_their_parts(vocabulary, query, expected_stems):
    assert expand_query(query, vocabulary) == expected_stems


@pytest.mark.parametrize(
    "word", ["Verordnung", "Kommission", "Behörde", "Anbieter", "Arbeitsvertrag"]
)
def test_plain_words_are_not_split(vocabulary, word):
    assert expand_query(word, vocabulary) == [stem(word)]


def test_a_word_outside_the_law_is_left_alone(vocabulary):
    assert expand_query("Quantenphysik", vocabulary) == [stem("quantenphysik")]


def test_document_terms_adds_a_compound_words_parts(vocabulary):
    assert document_terms("Mitbestimmungsrechte", vocabulary) == [
        "mitbestimmungsrecht",
        "mitbestimm",
        "recht",
    ]


def test_document_terms_keeps_only_the_stem_when_nothing_splits(vocabulary):
    assert document_terms("Verordnung", vocabulary) == [stem("Verordnung")]
