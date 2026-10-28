# Research note: German compound splitting for keyword search (2026-09-16)

Spike for M3 phase 1 (D21, D24). The question: a student types "Betreiberpflichten" and needs
to find Article 26, titled "Pflichten der Betreiber von Hochrisiko-KI-Systemen". Plain word
matching does not connect the two. Does stemming plus splitting the query word against the
corpus's own vocabulary connect them, without a compound dictionary to ship and keep current.

Verified against the real German corpus on 2026-09-16: `build_library(corpus_dir)` from
`backend/app/corpus/build.py`, 4366 nodes, a vocabulary of 5807 stems. The vocabulary was
re-measured after the statutes joined the index, and one row of the table below moved:
BetrVG § 5 writes "Arbeitsvertrag" as a single word, so the corpus vocabulary already
contains it and it no longer splits. Every other row still holds.

## The rule

Implemented in `backend/app/corpus/textindex.py`.

1. `tokenize` lowercases text and keeps runs of three or more letters (German umlauts and
   sharp s included). A hyphen breaks a token, so "Hochrisiko-KI-System" yields three words.
2. `stem` runs the Snowball German stemmer on a lowercased word. It folds plural onto singular
   and other inflection, for example "Pflichten" and "Pflicht" stem the same.
3. `build_vocabulary` stems every token from a set of texts into one set. For the corpus, the
   texts are the `.text` of every node.
4. `split_compound` takes a word not already in the vocabulary. It tries every cut point from
   the fourth letter to four letters before the end, stems the head, and checks it against the
   vocabulary. If the head matches, it tries the tail with no linking letter, then with "s",
   "n", "en" or "es" stripped from the front. A cut succeeds only when both stemmed halves are
   at least four letters and both are in the vocabulary. The first successful cut wins.
5. `expand_query` tokenizes a query, stems each token, and keeps it if the vocabulary already
   has it. If not, it tries `split_compound` and takes the two-part result. If splitting also
   fails, it keeps the stem as one word.
6. `document_terms` runs the same `split_compound` step on the document side, added when the
   search index (Task 11) needed it. For every token in a document's text, it keeps the token's
   own stem, and if the token also splits, adds both part stems too. A document is written once
   and searched many times, so this only has to answer "does this token split" the same way
   `expand_query` does, then cache the answer for reuse across the rest of the build.

The linking letters model the German linking morpheme (Fugenelement) that joins two nouns,
such as the "s" in "Arbeitsvertrag" between "Arbeit" and "Vertrag".

## Why the document side needed the same split

The query side alone was not enough. A student who searches "Mitbestimmung technische
Einrichtungen" for BetrVG § 87 relies on the query word "Mitbestimmung" reaching the document.
§ 87 is titled "Mitbestimmungsrechte", one word, and it stems to `mitbestimmungsrecht`, a whole
word already in the corpus vocabulary. `expand_query` never calls `split_compound` on an
in-vocabulary word, so the query's "Mitbestimmung" (stem `mitbestimm`) and the document's stem
`mitbestimmungsrecht` never matched: two different stems, zero overlap on that term.

`document_terms` closes this by splitting the document's own word the same way a query word
splits. `document_terms("Mitbestimmungsrechte", vocabulary)` returns
`["mitbestimmungsrecht", "mitbestimm", "recht"]`: the whole-word stem, plus both halves of its
one compound cut. The document now carries `mitbestimm` as a term in its own right, so the
query's `mitbestimm` matches it directly. Measured against the real corpus, "Mitbestimmung
technische Einrichtungen" now finds `betrvg:sec_87` at rank 1 in the search index.

The split has to run unconditionally, on every token, not only on tokens whose whole-word stem
is missing from the vocabulary. `mitbestimmungsrecht` is itself a valid in-vocabulary word, so
a guard that only splits out-of-vocabulary tokens would skip this exact case and undo the fix
it exists for.

## Startup cost

`document_terms` is the slow step, since it calls `stem` and `split_compound` for every token of
every document. Building `SearchIndex` shares one cache across the whole build, keyed by token,
so each distinct token is stemmed and split once regardless of how many documents repeat it.
Measured on the real corpus (723 indexed documents) with the memoized cache: five runs of
`SearchIndex.build(library)` took 4.539s, 4.482s, 4.550s, 4.491s and 4.489s, a median of 4.5s.
This runs once at process startup, not per request.

## Queries that pass

Against the real corpus vocabulary:

| Query | `expand_query` result |
|---|---|
| Betreiberpflichten | betreib, pflicht |
| Kompetenzanforderungen | kompetenz, anforder |
| Hochrisikoeinstufung | hochrisiko, einstuf |
| Verordnung | verordn (stays whole) |
| Kommission | kommission (stays whole) |
| Behörde | behord (stays whole) |
| Anbieter | anbiet (stays whole) |
| Arbeitsvertrag | arbeitsvertrag (stays whole) |
| Quantenphysik | quantenphys (stays whole, out of vocabulary) |

"Verordnung", "Kommission", "Behörde", "Anbieter" and "Arbeitsvertrag" stay whole because
each word itself is in the corpus vocabulary, so `expand_query` never calls `split_compound`
on them. "Verordnung" also cannot split: neither "verord" nor "nung" is a word the corpus
uses. "Quantenphysik" stays whole for a different reason: it is not in the vocabulary and no
cut of it produces two words that are, so `split_compound` returns `None` and `expand_query`
falls back to the stem of the full word.

"Anbieterpflichten" and "Transparenzpflichten" also stay whole, and correctly so. Both appear
in the Regulation as single words, so they are already in the vocabulary and `expand_query`
returns them unsplit before any attempt at `split_compound`.

"Arbeitsvertrag" also stays whole, and correctly so, though for a reason outside the AI Act:
BetrVG § 5 writes it as a single word, in "wer nach Arbeitsvertrag und Stellung im
Unternehmen", so once the statutes joined the index the corpus vocabulary already contained
it, and `expand_query` returns it unsplit before any attempt at `split_compound`. The spike's
own hand-built vocabulary in "The rule" above still uses "Arbeitsvertrag" as the example of a
linking-s split, and that example still holds against a small vocabulary lacking the whole
word. The real corpus vocabulary is not that small vocabulary.

21 tests cover this: 10 against a small hand-built vocabulary, 11 against the real corpus
vocabulary. All 21 pass. The archived internal task report for 2026-09-16
carries the run output as of the spike. The count grew as later fix rounds added cases; a
fresh `pytest tests/corpus/test_textindex.py --collect-only -q` is the current count.

## Changes needed to the rule

None. The rule in the plan matched every measured case on the first implementation. No linker
was added, no minimum part length changed, no cut preference reordered.

## What still fails or is untested

- `split_compound` only splits a word into two parts. A three-part German compound, such as
  "Hochrisikokennzeichnungspflicht", stems as one unit or splits at only one of its two
  possible joins, whichever the loop reaches first. The spike did not need a three-part
  compound to answer the design question, so this is untested, not confirmed working.
- The loop returns the first cut that satisfies the check, scanning from the shortest head to
  the longest. For a word with more than one valid two-way split, this picks the shortest head,
  not necessarily the split a reader would expect. No corpus query in this spike produced more
  than one valid split, so the choice has not been exercised.
- This spike does not rank or search. It only answers whether a query word reaches the stems
  that a search index would need to match against article text. Building that index is a later
  task in M3 phase 1.

## Known limit

The search index's fixture query "Beschäftigtendatenschutz" (expecting `bdsg:sec_26`) fails,
and no amount of tuning fixes it. `expand_query` splits it to `beschaftigt` and `datenschutz`.
BDSG § 26 uses "Beschäftigte" seventeen times but never writes "Datenschutz" in any form. It
writes "Datenverarbeitung" and "personenbezogene Daten" instead. So `datenschutz` contributes
zero to § 26's score, on any `k1`, `b`, or title weight, because BM25 gives a term with zero
frequency in a document a score of exactly zero in that document. The term `beschaftigt` alone
cannot carry § 26 into the top five. Its BM25 ceiling, the score it approaches as its frequency
grows without bound, is `idf * (k1 + 1) = 2.859 * 2.5 = 7.148`. Every competing `bdsg` section
already scores at or above that on the full query at the measured configuration. This is a
synonym gap, not a tuning gap. Closing it needs a term the document does not contain, which
stemming and compound splitting cannot supply. `test_search.py` marks this one case
`xfail(strict=True)`.

## Conclusion

Stemming plus splitting against the corpus's own vocabulary connects "Betreiberpflichten" to
the stems "betreib" and "pflicht", which appear in Article 26's title. The corpus vocabulary
stays the only source of truth for what counts as a word, so a word absent from the law never
forces a split. M3 phase 1 can build the search index on this rule.
