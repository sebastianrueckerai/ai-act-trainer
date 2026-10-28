from collections.abc import Container, Iterator
from copy import deepcopy
from pathlib import Path
from typing import Literal, NamedTuple

from lxml import etree, html

from app.corpus.model import (
    Annex,
    Article,
    Block,
    Division,
    Paragraph,
    Point,
    append_point,
    extend_text,
    free_id,
    point_ids,
)
from app.corpus.textutil import split_label, text_of

CHAPTER = 'div[starts-with(@id,"cpt_") and not(contains(@id,".sct_"))]'
ARTICLE = 'div[contains(@class,"eli-subdivision") and starts-with(@id,"art_")]'
ANNEX = 'div[starts-with(@id,"anx_") and not(contains(@id,"."))]'
CHAPTERS = f"//{CHAPTER}"
ARTICLES = f"//{ARTICLE}"
ANNEXES = f"//{ANNEX}"
SECTIONS = './div[contains(@id,".sct_")]'
GRID_LABEL = './div[contains(@class,"grid-list-column-1")]'
GRID_BODY = './div[contains(@class,"grid-list-column-2")]'
TEXT_CLASSES = {"norm", "list", "tbl-norm"}
ANNEX_SECTION = "title-gr-seq-level-1"
ANNEX_HEADINGS = {ANNEX_SECTION, "title-gr-seq-level-2"}


class _Part(NamedTuple):
    """One top-level piece of an annex body, classified by what it opens."""

    kind: Literal["item", "point", "section", "text"]
    element: etree._Element
    label: str
    text: str


def _cls(element: etree._Element) -> set[str]:
    return set((element.get("class") or "").split())


def _texts(elements: list[etree._Element]) -> str:
    return " ".join(filter(None, (text_of(element) for element in elements)))


def _first_text(container: etree._Element, xpath: str) -> str:
    found = container.xpath(xpath)
    return text_of(found[0]) if found else ""


def _label(container: etree._Element, xpath: str) -> str:
    found = container.xpath(xpath)
    return split_label(text_of(found[0]))[0] if found else ""


def _is_grid(element: etree._Element) -> bool:
    return element.tag == "div" and "grid-container" in _cls(element)


def _parse_point(grid: etree._Element, prefix: str, taken: Container[str] = ()) -> Point | None:
    """Parse one point of a list.

    An id already in ``taken`` is numbered off, because a second subparagraph of the same
    paragraph may restart its list at ``(a)``.
    """
    body = grid.xpath(GRID_BODY)
    if not body:
        return None
    label = _label(grid, GRID_LABEL)
    point_id = free_id(f"{prefix}.{label}", taken)
    return Point(
        id=point_id,
        label=label,
        marker=f"({label})",
        blocks=_body_blocks(body[0], point_id),
    )


def _body_blocks(container: etree._Element, prefix: str) -> list[Block]:
    """Blocks of a container's body, in the order the source prints them.

    The container's own text and the tail of every child belong to the body, so the text is
    gathered between the point lists rather than around them. A sentence that closes a list
    then stays after the list it closes.
    """
    blocks: list[Block] = []
    holder = etree.Element(container.tag)
    holder.text = container.text

    def flush() -> None:
        text = text_of(holder)
        if text:
            extend_text(blocks, text)
        holder.clear()

    for child in list(deepcopy(container)):
        if not _is_grid(child):
            holder.append(child)
            continue
        tail = child.tail
        flush()
        point = _parse_point(child, prefix, point_ids(blocks))
        if point is not None:
            append_point(blocks, point)
        holder.text = tail
    flush()
    return blocks


def _annex_text_blocks(container: etree._Element) -> Iterator[etree._Element]:
    """Every text-bearing paragraph of an annex, in document order, headings included.

    Annex XIV keeps its code list in table cells (``p.tbl-norm``) inside a ``div.centered``.
    """
    for node in container.iter("p"):
        if _cls(node) & (TEXT_CLASSES | ANNEX_HEADINGS):
            yield node


def _text_blocks(text: str) -> list[Block]:
    return [Block(text=text)] if text else []


def _reprefix(points: list[Point], old: str, new: str) -> list[Point]:
    return [
        Point(
            id=new + point.id[len(old) :],
            label=point.label,
            marker=point.marker,
            blocks=_reprefix_blocks(point.blocks, old, new),
        )
        for point in points
    ]


def _reprefix_blocks(blocks: list[Block], old: str, new: str) -> list[Block]:
    return [Block(text=block.text, points=_reprefix(block.points, old, new)) for block in blocks]


def _promote_numbered_points(paragraphs: list[Paragraph], prefix: str) -> list[Paragraph]:
    """Raise a numbered list under a lone lead sentence to paragraphs of its own.

    Article 3 numbers its definitions ``(1)`` to ``(68)`` below one unnumbered sentence, and
    ``Art. 3(4)`` cites the fourth of them, so each definition has to answer to ``art_3.4``.
    The lead sentence keeps the id ``art_N.0`` and loses its points.
    """
    if len(paragraphs) != 1:
        return paragraphs
    lead = paragraphs[0]
    if lead.number is not None or not lead.points:
        return paragraphs
    if not all(point.label[:1].isdigit() for point in lead.points):
        return paragraphs
    promoted = []
    for point in lead.points:
        paragraph_id = f"{prefix}.{point.label}"
        promoted.append(
            Paragraph(
                id=paragraph_id,
                number=int(point.label) if point.label.isdigit() else None,
                blocks=_reprefix_blocks(point.blocks, point.id, paragraph_id),
            )
        )
    kept: list[Block] = []
    for block in lead.blocks:
        if block.text:
            extend_text(kept, block.text)
    return [Paragraph(id=lead.id, number=lead.number, blocks=kept), *promoted]


def _parse_paragraphs(article: etree._Element, prefix: str) -> list[Paragraph]:
    """Walk an article body in document order.

    A ``div.norm`` opens a paragraph, numbered by its ``no-parag`` marker. Article-level
    ``p.norm`` and ``grid-container`` siblings are further subparagraphs and points of the
    paragraph they follow; before the first ``div.norm`` they form the lead paragraph.
    """
    paragraphs: list[Paragraph] = []

    def current() -> Paragraph:
        if not paragraphs:
            paragraphs.append(Paragraph(id=f"{prefix}.0", number=None, blocks=[]))
        return paragraphs[-1]

    for block in article:
        classes = _cls(block)
        if block.tag == "div" and "norm" in classes and "inline-element" not in classes:
            label = _label(block, './span[@class="no-parag"]')
            source = block.xpath('./div[contains(@class,"inline-element")]')[0]
            paragraph_id = f"{prefix}.{label or '0'}"
            paragraphs.append(
                Paragraph(
                    id=paragraph_id,
                    number=int(label) if label.isdigit() else None,
                    blocks=_body_blocks(source, paragraph_id),
                )
            )
        elif block.tag == "p" and classes & TEXT_CLASSES:
            text = text_of(block)
            if text:
                extend_text(current().blocks, text)
        elif _is_grid(block):
            paragraph = current()
            point = _parse_point(block, paragraph.id, point_ids(paragraph.blocks))
            if point is not None:
                append_point(paragraph.blocks, point)
    return _promote_numbered_points(paragraphs, prefix)


def _has_numbered_headings(annex: etree._Element) -> bool:
    """Whether the annex numbers its items with headings rather than with a list.

    Annexes VII, X and XIV open an item with "1. Einleitung" or "1. Schengener
    Informationssystem". Annexes I, VIII and XI head their sections "Abschnitt A" or
    "Abschnitt 1", which carry no number and open nothing.
    """
    return any(
        split_label(text_of(child))[0].isdigit()
        for child in annex
        if child.tag == "p" and ANNEX_SECTION in _cls(child)
    )


def _child_text(child: etree._Element) -> str:
    if child.tag == "p":
        return text_of(child) if _cls(child) & (TEXT_CLASSES | ANNEX_HEADINGS) else ""
    if child.tag == "div":
        return _texts(list(_annex_text_blocks(child)))
    return ""


def _annex_parts(annex: etree._Element, headed: bool) -> list[_Part]:
    """Classify every top-level child of an annex body, in document order."""
    parts: list[_Part] = []
    for child in annex:
        if _is_grid(child):
            if child.xpath(GRID_BODY):
                kind = "point" if headed else "item"
                parts.append(_Part(kind, child, _label(child, GRID_LABEL), ""))
            continue
        text = _child_text(child)
        if not text:
            continue
        label, rest = split_label(text)
        if child.tag == "p" and ANNEX_SECTION in _cls(child):
            if label.isdigit():
                parts.append(_Part("item", child, label, rest))
            else:
                parts.append(_Part("section", child, "", text))
        elif label.isdigit() and not headed:
            parts.append(_Part("item", child, label, rest))
        else:
            parts.append(_Part("text", child, "", text))
    return parts


def _annex_labels(labels: list[str]) -> list[str]:
    """Label every item of an annex, numbering by position where the labels fail.

    Annex III labels its items ``1.`` to ``8.``, but Annex II bullets them with em dashes and
    Annex VIII restarts at ``1.`` under every section, so neither yields a usable set of ids.
    """
    if all(labels) and len(set(labels)) == len(labels):
        return labels
    return [str(position) for position in range(1, len(labels) + 1)]


def _item_blocks(part: _Part, paragraph_id: str) -> list[Block]:
    if _is_grid(part.element):
        return _body_blocks(part.element.xpath(GRID_BODY)[0], paragraph_id)
    return _text_blocks(part.text)


def _parse_annex_body(annex: etree._Element, prefix: str) -> list[Paragraph]:
    """Walk an annex body in document order.

    An item is a top-level ``grid-container``, a paragraph that opens with its own number, or,
    in an annex that numbers its headings, the heading itself. Text below an item extends it,
    and a list below a numbered heading becomes that item's points. A section heading opens
    nothing, so it joins the lead paragraph instead of the item it follows, and the items keep
    running numbers across the sections.
    """
    parts = _annex_parts(annex, _has_numbered_headings(annex))
    labels = _annex_labels([part.label for part in parts if part.kind == "item"])
    paragraphs: list[Paragraph] = []
    lead = ""
    in_lead = True
    for part in parts:
        if part.kind == "item":
            label = labels[len(paragraphs)]
            paragraph_id = f"{prefix}.{label}"
            paragraphs.append(
                Paragraph(
                    id=paragraph_id,
                    number=int(label) if label.isdigit() else None,
                    blocks=_item_blocks(part, paragraph_id),
                )
            )
            in_lead = False
        elif part.kind == "point":
            if not paragraphs:
                raise ValueError(f"{prefix}: a list sits above the first numbered heading")
            paragraph = paragraphs[-1]
            point = _parse_point(part.element, paragraph.id, point_ids(paragraph.blocks))
            if point is not None:
                append_point(paragraph.blocks, point)
        else:
            in_lead = in_lead or part.kind == "section"
            if in_lead:
                lead = f"{lead} {part.text}".strip()
            else:
                extend_text(paragraphs[-1].blocks, part.text)
    if lead:
        paragraphs.insert(0, Paragraph(id=f"{prefix}.0", number=None, blocks=_text_blocks(lead)))
    return paragraphs


def _parse_divisions(div: etree._Element) -> list[Division]:
    """One chapter and the sections below it, in source order."""
    chapter_id = div.get("id")
    divisions = [
        Division(
            id=chapter_id,
            number=chapter_id.split("_", 1)[1],
            title=_first_text(div, './p[@class="title-division-2"]'),
        )
    ]
    for sdiv in div.xpath(SECTIONS):
        section_id = sdiv.get("id")
        divisions.append(
            Division(
                id=section_id,
                number=section_id.rsplit("_", 1)[1],
                title=_first_text(sdiv, './p[@class="title-division-2"]'),
                parent_id=chapter_id,
            )
        )
    return divisions


def _parse_article(div: etree._Element) -> Article:
    article_id = div.get("id")
    chapter = div.xpath(f"ancestor::{CHAPTER}[1]")
    section = div.xpath('ancestor::div[contains(@id,".sct_")][1]')
    innermost = section or chapter
    return Article(
        id=article_id,
        number=article_id.split("_", 1)[1],
        title=_first_text(div, './/p[@class="stitle-article-norm"]'),
        division_id=innermost[0].get("id") if innermost else None,
        paragraphs=_parse_paragraphs(div, article_id),
    )


def _annex_title(div: etree._Element) -> str:
    """Title of an annex.

    Annexes X and XIV carry no ``title-annex-2`` subtitle. Annex X instead runs its heading
    over two ``title-annex-1`` lines, "ANNEX X" and the subtitle, so the last one is the title.
    """
    subtitle = _first_text(div, './/p[@class="title-annex-2"]')
    if subtitle:
        return subtitle
    headings = div.xpath('.//p[@class="title-annex-1"]')
    return text_of(headings[-1]) if headings else ""


def _parse_annex(div: etree._Element) -> Annex:
    annex_id = div.get("id")
    return Annex(
        id=annex_id,
        number=annex_id.split("_", 1)[1],
        title=_annex_title(div),
        paragraphs=_parse_annex_body(div, annex_id),
    )


def parse_consolidated(path: Path) -> tuple[list[Division], list[Article], list[Annex]]:
    root = html.parse(str(path)).getroot()
    return (
        [division for div in root.xpath(CHAPTERS) for division in _parse_divisions(div)],
        [_parse_article(div) for div in root.xpath(ARTICLES)],
        [_parse_annex(div) for div in root.xpath(ANNEXES)],
    )
