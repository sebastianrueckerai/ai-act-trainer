from pydantic import BaseModel

from app.content.citations import Citation, CitationError, _url
from app.corpus.model import Library, Node

DEFAULT_BUDGET = 1200


class Excerpt(BaseModel):
    ref: str
    node_id: str
    title: str
    text: str
    url: str
    dropped: list[str] = []


def excerpt(library: Library, citation: Citation, budget: int = DEFAULT_BUDGET) -> Excerpt:
    act = library.act(citation.act_id)
    node = library.node(citation.node_id)
    if act is None or node is None:
        raise CitationError(
            f"{citation.ref!r} resolves to {citation.node_id}, which is not in the library"
        )
    parts = _parts(library, citation, node)
    kept: list[str] = []
    dropped: list[str] = []
    used = 0
    for index, (ref, text) in enumerate(parts):
        growth = len(text) if not kept else len(text) + 2
        if kept and used + growth > budget:
            dropped = [ref for ref, _ in parts[index:]]
            break
        kept.append(text)
        used += growth
    return Excerpt(
        ref=citation.ref,
        node_id=citation.node_id,
        title=node.title,
        text="\n\n".join(kept),
        url=_url(act, citation),
        dropped=dropped,
    )


def _parts(library: Library, citation: Citation, node: Node) -> list[tuple[str, str]]:
    """The pieces a citation names, in source order, each with its own written reference.

    An article, an annex or a statute section is cut paragraph by paragraph. Anything smaller
    is one piece: its own node holds nothing that should be split.
    """
    if node.kind not in ("article", "annex"):
        return [(citation.ref, node.text)]
    parts: list[tuple[str, str]] = []
    for child in library.children(citation.node_id):
        segment = child.id.rsplit(".", 1)[-1]
        if node.kind == "annex":
            ref = f"{citation.ref} pt. {segment}"
        else:
            ref = f"{citation.ref}({segment})"
        parts.append((ref, child.text))
    return parts
