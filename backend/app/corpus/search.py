import math

from pydantic import BaseModel

from app.content.citations import written_ref
from app.corpus.model import Library, Node
from app.corpus.textindex import build_vocabulary, document_terms, expand_query

K1 = 1.5
# Lower than the usual 0.75: articles run longer than recitals, and a length penalty this
# strong buried articles under the recitals that restate their substance in a few sentences.
B = 0.3
INDEXED_KINDS = ("article", "annex", "recital")


class Hit(BaseModel):
    node_id: str
    act_id: str
    ref: str
    title: str
    score: float


class SearchIndex:
    """BM25 over one document per article, statute section, annex and recital in the library.

    An article is one document, so a hit names a whole article, not a paragraph inside it.
    """

    def __init__(
        self,
        vocabulary: set[str],
        nodes: dict[str, Node],
        postings: dict[str, dict[str, int]],
        doc_lengths: dict[str, int],
    ) -> None:
        self._vocabulary = vocabulary
        self._nodes = nodes
        self._postings = postings
        self._doc_lengths = doc_lengths
        self._doc_count = len(doc_lengths)
        self._avg_length = sum(doc_lengths.values()) / self._doc_count if doc_lengths else 0.0

    @classmethod
    def build(cls, library: Library) -> "SearchIndex":
        nodes = {node.id: node for node in library.index().values() if node.kind in INDEXED_KINDS}
        texts = {
            node_id: f"{node.title} {node.title} {node.text}" for node_id, node in nodes.items()
        }
        vocabulary = build_vocabulary(texts.values())
        cache: dict[str, list[str]] = {}
        postings: dict[str, dict[str, int]] = {}
        doc_lengths: dict[str, int] = {}
        for node_id, text in texts.items():
            terms = document_terms(text, vocabulary, cache)
            doc_lengths[node_id] = len(terms)
            counts: dict[str, int] = {}
            for term in terms:
                counts[term] = counts.get(term, 0) + 1
            for term, count in counts.items():
                postings.setdefault(term, {})[node_id] = count
        return cls(vocabulary, nodes, postings, doc_lengths)

    def search(self, query: str, limit: int = 5) -> list[Hit]:
        scores: dict[str, float] = {}
        for term in expand_query(query, self._vocabulary):
            matches = self._postings.get(term)
            if not matches:
                continue
            idf = math.log(1 + (self._doc_count - len(matches) + 0.5) / (len(matches) + 0.5))
            for node_id, freq in matches.items():
                norm = 1 - B + B * self._doc_lengths[node_id] / self._avg_length
                weight = idf * freq * (K1 + 1) / (freq + K1 * norm)
                scores[node_id] = scores.get(node_id, 0.0) + weight
        ranked = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)[:limit]
        return [self._hit(node_id, score) for node_id, score in ranked]

    def _hit(self, node_id: str, score: float) -> Hit:
        node = self._nodes[node_id]
        return Hit(
            node_id=node_id,
            act_id=node.act_id,
            ref=written_ref(node_id),
            title=node.title,
            score=score,
        )
