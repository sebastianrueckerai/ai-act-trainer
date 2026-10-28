import re

from langchain_core.tools import BaseTool, tool

from app.content.citations import (
    ACT_NAMES,
    DE_ACT_NAMES,
    CitationError,
    parse_citation,
    scan_citations,
    with_raw_citations,
)
from app.content.loader import ContentBundle
from app.corpus.excerpt import excerpt
from app.corpus.model import Library
from app.graph.deps import GraphDeps
from app.graph.state import CitationPart

PART_BUDGET = 600
PART_QUOTE_CHARS = 240
_SENTENCE_ENDS = (". ", "; ", ":")
# A model answering in prose sometimes spells the citation out, or writes the paragraph
# in parentheses instead of "Absatz"; the chip still needs to find it either way.
_SPELLED_ARTICLE = re.compile(
    r"\bArtikel (\d+[a-z]?)\b(?: Absatz (\d+[a-z]?)\b| ?\((\d+[a-z]?)\))?"
)


def _with_written_articles_shortened(text: str) -> str:
    def written(match: re.Match[str]) -> str:
        paragraph = match.group(2) or match.group(3)
        return f"Art. {match.group(1)}" + (f"({paragraph})" if paragraph else "")

    return _SPELLED_ARTICLE.sub(written, text)


# Everything a parenthesised group may hold besides its citations before it counts as nothing
# but a citation: the act names the course writes, the separators and the whitespace.
_ACT_WORD = "|".join(
    re.escape(name)
    for name in sorted(
        {name for name in ACT_NAMES.values() if name} | set(DE_ACT_NAMES.values()) | {"KI-VO"},
        key=len,
        reverse=True,
    )
)
_GROUP_FILLER = re.compile(rf"{_ACT_WORD}|\bund\b|\bsowie\b|[,;\s]", re.IGNORECASE)
_PAREN_GROUP = re.compile(r"[ \t]*\(([^()]*)\)")
# "Fundstellen: ..." as the last line or the last paragraph: the model's own sources line,
# which the app shows as parts instead (D82).
_SOURCES_TAIL = re.compile(r"\n+[ \t]*(?:Fundstellen|Quellen|Quelle)[ \t]*:[^\n]*[ \t]*\Z")
_SPACE_BEFORE_PUNCT = re.compile(r"[ \t]+([.,;:])")
_DOUBLE_SPACE = re.compile(r"[ \t]{2,}")


def _is_citation_group(inside: str) -> bool:
    """True when a parenthesised group holds citations and nothing else."""
    rest = with_raw_citations(inside)
    citations = scan_citations(rest)
    if not citations:
        return False
    for citation in citations:
        rest = rest.replace(citation.ref, " ")
    return not _GROUP_FILLER.sub("", rest).strip()


def without_inline_citations(text: str) -> str:
    """Model prose with every reference taken out of it: the grey sources line under the
    bubble is the one place a citation lives, and the tutor never rattles them off (D82)."""
    text = _SOURCES_TAIL.sub("", text)
    text = _PAREN_GROUP.sub(
        lambda match: "" if _is_citation_group(match.group(1)) else match.group(0), text
    )
    return _DOUBLE_SPACE.sub(" ", _SPACE_BEFORE_PUNCT.sub(r"\1", text)).strip()


def law_tools(deps: GraphDeps) -> list[BaseTool]:
    @tool
    def open_law(node_id: str) -> str:
        """List the children of one law node: an act, chapter, section or annex."""
        if deps.library.node(node_id) is None:
            known = ", ".join(deps.library.acts)
            return f"No law node {node_id!r}, so it has no children. Open one of: {known}."
        children = deps.library.children(node_id)
        if not children:
            return f"{node_id} is a leaf node and has no children. Read it with read_law."
        lines = [f"Children of {node_id}:"]
        for child in children:
            summary = deps.content.law.get(child.id)
            line = f"- {child.id} ({child.kind}) {child.title}"
            if summary is not None:
                line += f": {summary.summary}"
            lines.append(line)
        return "\n".join(lines)

    @tool
    def read_law(citation: str) -> str:
        """Read the law text one citation names, cut to the excerpt budget."""
        try:
            parsed = parse_citation(citation)
            passage = excerpt(deps.library, parsed, budget=deps.settings.excerpt_budget_chars)
        except CitationError as error:
            return f"Could not read {citation!r}: {error}"
        lines = [f"Ref {passage.ref} ({passage.node_id})", f"Title: {passage.title}", passage.text]
        if passage.dropped:
            lines.append(f"Dropped: {', '.join(passage.dropped)}")
        return "\n".join(lines)

    @tool
    def search_law(query: str) -> str:
        """Search every bundled act for law text matching a query, best hits first."""
        hits = deps.search.search(query, limit=deps.settings.search_top_k)
        if not hits:
            return f"No hits for {query!r} in the bundled acts."
        lines = [f"Hits for {query!r}:"]
        for hit in hits:
            summary = deps.content.law.get(hit.node_id)
            text = summary.summary if summary else hit.title
            lines.append(f"- {hit.ref} ({hit.node_id}): {text}")
        return "\n".join(lines)

    return [open_law, read_law, search_law]


def library_brief(library: Library, content: ContentBundle) -> str:
    lines = []
    for act_id, act in library.acts.items():
        summary = content.law.get(act_id)
        lines.append(f"- {act_id} ({act.short_name}): {summary.summary if summary else act.title}")
    for node_id, summary in content.law.items():
        if not node_id.startswith("ai_act:cpt_"):
            continue
        if node_id.partition(":")[2].count(".") > 1:
            continue
        lines.append(f"- {node_id}: {summary.summary}")
    return "\n".join(lines)


def _quote(text: str) -> str:
    if len(text) <= PART_QUOTE_CHARS:
        return text
    budget = text[:PART_QUOTE_CHARS]
    cut = max((budget.rfind(sep) for sep in _SENTENCE_ENDS), default=-1)
    if cut != -1:
        return budget[: cut + 1] + "…"
    space = budget.rfind(" ")
    return (budget[:space] if space != -1 else budget) + "…"


def citations_from_text(deps: GraphDeps, text: str) -> list[CitationPart]:
    parts = []
    seen: set[str] = set()
    for citation in scan_citations(with_raw_citations(_with_written_articles_shortened(text))):
        try:
            passage = excerpt(deps.library, citation, budget=PART_BUDGET)
        except CitationError:
            continue
        if passage.ref in seen:
            continue
        seen.add(passage.ref)
        parts.append(
            CitationPart(
                ref=passage.ref,
                title=passage.title,
                quote=_quote(passage.text),
                url=passage.url,
            )
        )
    return parts
