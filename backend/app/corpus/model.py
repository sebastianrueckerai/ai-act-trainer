from collections.abc import Container
from functools import cached_property
from typing import Literal

from pydantic import BaseModel, ConfigDict

NodeKind = Literal[
    "act",
    "division",
    "article",
    "paragraph",
    "point",
    "annex",
    "recital",
]
Jurisdiction = Literal["eu", "de"]
ActKind = Literal["regulation", "statute", "guidance"]

REPEAT = "~"

LABELS = {
    "de": {"article": "Artikel", "annex": "Anhang", "section": "§", "recital": "Erwägungsgrund"},
    "en": {"article": "Article", "annex": "Annex", "section": "Section", "recital": "Recital"},
}


def node_id(act_id: str, local_id: str) -> str:
    """The address of one piece of one act. An act answers to its own id."""
    return f"{act_id}:{local_id}"


class Node(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    act_id: str
    kind: NodeKind
    title: str
    text: str
    parent_id: str | None


class Block(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str = ""
    points: list["Point"] = []


class Point(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    marker: str
    blocks: list[Block] = []

    @property
    def text(self) -> str:
        return next((block.text for block in self.blocks if block.text), "")

    @property
    def points(self) -> list["Point"]:
        return [point for block in self.blocks for point in block.points]

    def flat_text(self) -> str:
        return _flatten(self.blocks)


Block.model_rebuild()


def free_id(point_id: str, taken: Container[str]) -> str:
    """An id no point beside this one holds yet.

    A second list under one paragraph may restart at "(a)" or at "1.". A repeat carries a
    separator no law prints, so that a repeated "1." becomes ``1~2`` rather than ``12``, which
    is the id of the twelfth Nummer and a citation a reader could write.
    """
    candidate = point_id
    repeat = 1
    while candidate in taken:
        repeat += 1
        candidate = f"{point_id}{REPEAT}{repeat}"
    return candidate


def point_ids(blocks: list[Block]) -> set[str]:
    """The ids of the points these blocks already hold, at their own level."""
    return {point.id for block in blocks for point in block.points}


def extend_text(blocks: list[Block], text: str) -> None:
    """Add text to the block being written, or open one."""
    if blocks and blocks[-1].text:
        blocks[-1] = Block(text=f"{blocks[-1].text} {text}".strip())
    else:
        blocks.append(Block(text=text))


def append_point(blocks: list[Block], point: Point) -> None:
    """Add a point to the list being written, or open one."""
    if blocks and blocks[-1].points:
        blocks[-1] = Block(points=[*blocks[-1].points, point])
    else:
        blocks.append(Block(points=[point]))


class Paragraph(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    number: int | None
    blocks: list[Block] = []

    @property
    def text(self) -> str:
        return next((block.text for block in self.blocks if block.text), "")

    @property
    def points(self) -> list[Point]:
        return [point for block in self.blocks for point in block.points]

    def flat_text(self) -> str:
        return _flatten(self.blocks)


def _flatten(blocks: list[Block]) -> str:
    parts: list[str] = []
    for block in blocks:
        if block.points:
            parts.append(" ".join(f"{p.marker} {p.flat_text()}" for p in block.points))
        elif block.text:
            parts.append(block.text)
    return " ".join(parts).strip()


class Article(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    number: str
    title: str
    division_id: str | None = None
    paragraphs: list[Paragraph] = []


class Division(BaseModel):
    """One Chapter, Section, Teil, Abschnitt or Unterabschnitt, at whatever depth it sits.

    A law nests its divisions as deep as it likes, so depth is data rather than a shape the
    model fixes. ``parent_id`` is a local id, and it is None for a division under the act.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    number: str
    title: str
    parent_id: str | None = None


class Annex(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    number: str
    title: str
    paragraphs: list[Paragraph]


class Recital(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    number: int
    text: str


class Act(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: ActKind
    short_name: str
    title: str
    jurisdiction: Jurisdiction
    lang: str
    version: str
    source_url: str
    attribution: str
    divisions: list[Division] = []
    articles: list[Article] = []
    annexes: list[Annex] = []
    recitals: list[Recital] = []

    def index(self) -> dict[str, Node]:
        return self._index

    def children(self, local_id: str = "") -> list[Node]:
        index = self.index()
        return [index[node_id(self.id, child)] for child in self._children.get(local_id, [])]

    def _article_title(self, article: Article) -> str:
        labels = LABELS[self.lang]
        if self.kind == "statute":
            return f"{labels['section']} {article.number} {article.title}".strip()
        if self.kind == "guidance":
            return article.title
        return f"{labels['article']} {article.number}: {article.title}"

    @cached_property
    def _index(self) -> dict[str, Node]:
        nodes: dict[str, Node] = {}
        labels = LABELS[self.lang]

        def add(local_id: str, kind: NodeKind, title: str, text: str, parent: str) -> None:
            nodes[node_id(self.id, local_id)] = Node(
                id=node_id(self.id, local_id),
                act_id=self.id,
                kind=kind,
                title=title,
                text=text,
                parent_id=parent,
            )

        def add_points(points: list[Point], parent: str, title: str) -> None:
            for point in points:
                add(point.id, "point", title, point.flat_text(), parent)
                add_points(point.points, node_id(self.id, point.id), title)

        def add_paragraphs(paragraphs: list[Paragraph], parent: str, title: str) -> None:
            for paragraph in paragraphs:
                add(paragraph.id, "paragraph", title, paragraph.flat_text(), parent)
                add_points(paragraph.points, node_id(self.id, paragraph.id), title)

        nodes[self.id] = Node(
            id=self.id,
            act_id=self.id,
            kind="act",
            title=self.title,
            text=self.title,
            parent_id=None,
        )
        for division in self.divisions:
            parent = node_id(self.id, division.parent_id) if division.parent_id else self.id
            add(division.id, "division", division.title, division.title, parent)
        for article in self.articles:
            title = self._article_title(article)
            text = " ".join(p.flat_text() for p in article.paragraphs)
            parent = article.division_id
            add(
                article.id,
                "article",
                title,
                text,
                node_id(self.id, parent) if parent else self.id,
            )
            add_paragraphs(article.paragraphs, node_id(self.id, article.id), title)
        for annex in self.annexes:
            title = f"{labels['annex']} {annex.number}: {annex.title}"
            text = " ".join(p.flat_text() for p in annex.paragraphs)
            add(annex.id, "annex", title, text, self.id)
            add_paragraphs(annex.paragraphs, node_id(self.id, annex.id), title)
        for recital in self.recitals:
            label = f"{labels['recital']} {recital.number}"
            add(recital.id, "recital", label, recital.text, self.id)
        return nodes

    @cached_property
    def _children(self) -> dict[str, list[str]]:
        """Direct children per local id, in source order. The act itself is the empty key.

        An act lists its top-level divisions, then the articles under no division, then its
        annexes. A division lists its sub-divisions before its own articles, and no division in
        the library holds both. Nothing lists a recital, because a walk down 180 of them finds
        nothing. The tutor reaches a recital through the article it explains, or by search.
        """
        children: dict[str, list[str]] = {}

        def walk_points(parent_id: str, points: list[Point]) -> None:
            children[parent_id] = [point.id for point in points]
            for point in points:
                walk_points(point.id, point.points)

        def walk_paragraphs(parent_id: str, paragraphs: list[Paragraph]) -> None:
            children[parent_id] = [paragraph.id for paragraph in paragraphs]
            for paragraph in paragraphs:
                walk_points(paragraph.id, paragraph.points)

        for division in self.divisions:
            children.setdefault(division.parent_id or "", []).append(division.id)
            children.setdefault(division.id, [])
        for article in self.articles:
            children.setdefault(article.division_id or "", []).append(article.id)
            walk_paragraphs(article.id, article.paragraphs)
        for annex in self.annexes:
            children.setdefault("", []).append(annex.id)
            walk_paragraphs(annex.id, annex.paragraphs)
        return children


class Library(BaseModel):
    model_config = ConfigDict(frozen=True)

    acts: dict[str, Act]

    def act(self, act_id: str) -> Act | None:
        return self.acts.get(act_id)

    def index(self) -> dict[str, Node]:
        return self._index

    def node(self, address: str) -> Node | None:
        return self.index().get(address)

    def children(self, address: str) -> list[Node]:
        act_id, _, local_id = address.partition(":")
        act = self.act(act_id)
        return act.children(local_id) if act else []

    @cached_property
    def _index(self) -> dict[str, Node]:
        return {
            address: node for act in self.acts.values() for address, node in act.index().items()
        }
