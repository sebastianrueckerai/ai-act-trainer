import re
from collections.abc import Iterable

import snowballstemmer

WORD = re.compile(r"[A-Za-zÄÖÜäöüß]{3,}")
MIN_PART = 4
LINKERS = ("", "s", "n", "en", "es")

_stemmer = snowballstemmer.stemmer("german")


def tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in WORD.finditer(text)]


def stem(word: str) -> str:
    return _stemmer.stemWord(word.lower())


def build_vocabulary(texts: Iterable[str]) -> set[str]:
    return {stem(token) for text in texts for token in tokenize(text)}


def split_compound(word: str, vocabulary: set[str]) -> list[str] | None:
    lowered = word.lower()
    for cut in range(MIN_PART, len(lowered) - MIN_PART + 1):
        head = stem(lowered[:cut])
        if head not in vocabulary:
            continue
        for linker in LINKERS:
            rest = lowered[cut:]
            if linker and not rest.startswith(linker):
                continue
            tail = stem(rest[len(linker) :])
            if len(rest) - len(linker) >= MIN_PART and tail in vocabulary:
                return [head, tail]
    return None


def expand_query(query: str, vocabulary: set[str]) -> list[str]:
    stems: list[str] = []
    for token in tokenize(query):
        stemmed = stem(token)
        if stemmed in vocabulary:
            stems.append(stemmed)
            continue
        parts = split_compound(token, vocabulary)
        stems.extend(parts if parts else [stemmed])
    return stems


def document_terms(
    text: str, vocabulary: set[str], cache: dict[str, list[str]] | None = None
) -> list[str]:
    """Every stem tokenize(text) produces, plus, for a token whose compound splits, its two
    part stems too. The query side has always run through the spike's splitter. A document
    that only ever writes "Mitbestimmungsrechte" otherwise never matches a query for its bare
    stem "mitbestimm", so the same split now runs on the document side as well.

    Call with a shared cache across the documents of one build: stemming and splitting are
    the slow steps, and the corpus repeats the same few thousand distinct tokens many times.
    """
    if cache is None:
        cache = {}
    terms: list[str] = []
    for token in tokenize(text):
        found = cache.get(token)
        if found is None:
            stemmed = stem(token)
            parts = split_compound(token, vocabulary)
            found = [stemmed, *parts] if parts else [stemmed]
            cache[token] = found
        terms.extend(found)
    return terms
