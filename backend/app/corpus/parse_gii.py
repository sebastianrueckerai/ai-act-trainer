import re
from copy import deepcopy
from pathlib import Path

from lxml import etree

from app.corpus.model import (
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
from app.corpus.textutil import normalize, split_label

SECTION = re.compile(r"§\s*(\d+[a-z]?)")
FOOTNOTE = re.compile(r"\s*\*+\)$")
DESIGNATION = re.compile(r"(\d+[a-z]?|[IVXLCDM]+)\.?")
REPEALED = {"(weggefallen)", "(aufgehoben)"}


def parse_gii(xml_path: Path) -> tuple[list[Division], list[Article]]:
    """Read one gesetze-im-internet statute: its divisions and its sections.

    A division is a Teil, Abschnitt, Kapitel or Unterabschnitt, and they nest as deep as the
    statute prints them. A section belongs to the innermost division that opened before it.
    """
    parser = etree.XMLParser(load_dtd=False, no_network=True, resolve_entities=False)
    root = etree.parse(str(xml_path), parser).getroot()
    divisions: list[Division] = []
    by_code: dict[str, str] = {}
    counts: dict[str, int] = {}
    articles: list[Article] = []
    division_id = ""
    for norm in root.iter("norm"):
        division = norm.find("./metadaten/gliederungseinheit")
        if division is not None:
            code = _text(division.find("./gliederungskennzahl"))
            parent_id = _division_parent(code, by_code)
            division_id = _division_id(parent_id, counts)
            by_code[code] = division_id
            divisions.append(
                Division(
                    id=division_id,
                    number=_division_number(division),
                    title=_division_title(division),
                    parent_id=parent_id,
                )
            )
            continue
        article = _section(norm, division_id)
        if article is not None:
            articles.append(article)
    return divisions, articles


def _division_parent(code: str, by_code: dict[str, str]) -> str | None:
    """The division one level up, read off the gliederungskennzahl.

    The code runs three digits per level, so the parent is the division whose code is this one
    without its last three digits. A top-level division has a three-digit code and no parent.
    """
    if len(code) < 3 or len(code) % 3:
        raise ValueError(f"gliederungskennzahl {code!r} is not three digits per level")
    parent_code = code[:-3]
    if not parent_code:
        return None
    if parent_code not in by_code:
        raise ValueError(f"division {code!r} stands under no division {parent_code!r}")
    return by_code[parent_code]


def _division_id(parent_id: str | None, counts: dict[str, int]) -> str:
    """The id of the next division under one parent, numbered by position among its siblings."""
    key = parent_id or ""
    counts[key] = counts.get(key, 0) + 1
    return f"{parent_id}.sct_{counts[key]}" if parent_id else f"cpt_{counts[key]}"


def _section(norm: etree._Element, division_id: str) -> Article | None:
    """One section, or nothing for a norm that is not one.

    A statute opens with a norm that carries no enbez, and it prints its Inhaltsübersicht as
    one. Those are not sections. An enbez that names a section the parser cannot number, such
    as a range over several sections, raises rather than disappearing.
    """
    enbez = _text(norm.find("./metadaten/enbez"))
    if not enbez.startswith("§"):
        return None
    match = SECTION.fullmatch(enbez)
    if match is None:
        raise ValueError(f"{enbez!r} names no single section")
    number = match.group(1)
    title = FOOTNOTE.sub("", _text(norm.find("./metadaten/titel")))
    paragraphs = _paragraphs(norm, number)
    bodies = [paragraph.text for paragraph in paragraphs]
    if len(bodies) == 1 and bodies[0] in REPEALED:
        return None
    return Article(
        id=f"sec_{number}",
        number=number,
        title=title,
        division_id=division_id or None,
        paragraphs=paragraphs,
    )


def _paragraphs(norm: etree._Element, number: str) -> list[Paragraph]:
    """The Absätze of one section, each under the label the statute prints.

    The BetrVG amends by inserting an Absatz 2a, so a position would name the wrong Absatz
    from there on. A statute prints no two Absaetze under one id, so a list that mixes
    unlabelled and labelled Absaetze into one id raises instead of answering to both.
    """
    paragraphs: list[Paragraph] = []
    taken: set[str] = set()
    for index, element in enumerate(norm.xpath(".//textdaten/text/Content/P"), start=1):
        label = split_label(_text(element))[0]
        paragraph_id = f"sec_{number}.{label or index}"
        if paragraph_id in taken:
            raise ValueError(f"two Absaetze of section {number} share the id {paragraph_id}")
        taken.add(paragraph_id)
        paragraphs.append(
            Paragraph(
                id=paragraph_id,
                number=int(label) if label.isdigit() else None,
                blocks=_blocks(element, paragraph_id, labelled=True),
            )
        )
    return paragraphs


def _blocks(container: etree._Element, prefix: str, labelled: bool = False) -> list[Block]:
    """The blocks of one Absatz or one Nummer, in the order the statute prints them.

    A statute sets its Nummern as a definition list inside the Absatz, and it may close the
    list with a Schlusssatz. The lead-in, the list and the Schlusssatz each become a block, so
    the sentence that closes a list stays after the list it closes. ``labelled`` strips the
    Absatz marker the statute prints in front of the lead-in.
    """
    blocks: list[Block] = []
    source = _open_wrappers(container)
    holder = etree.Element("P")
    holder.text = source.text
    strip = labelled

    def flush() -> None:
        nonlocal strip
        text = _text(holder)
        holder.clear()
        if strip:
            strip = False
            text = split_label(text)[1]
        if text:
            extend_text(blocks, text)

    for child in list(source):
        if child.tag != "DL":
            holder.append(child)
            continue
        tail = child.tail
        flush()
        _add_list(blocks, child, prefix)
        holder.text = tail
    flush()
    return blocks


def _add_list(blocks: list[Block], listing: etree._Element, prefix: str) -> None:
    """Add one list, each term a point under the marker the statute prints.

    A term the label rule cannot number stays in the text instead of opening a point. The
    BetrVG prints its amtliche Hinweise this way, marked "*)" and "+)".
    """
    for term in listing.findall("DT"):
        body = term.getnext()
        if body is None or body.tag != "DD":
            continue
        marker = _text(term)
        label = split_label(marker)[0]
        if not label:
            extend_text(blocks, f"{marker} {_text(body)}".strip())
            continue
        point_id = free_id(f"{prefix}.{label}", point_ids(blocks))
        append_point(
            blocks,
            Point(id=point_id, label=label, marker=marker, blocks=_blocks(body, point_id)),
        )


def _open_wrappers(element: etree._Element) -> etree._Element:
    """A copy of one element with every ``LA`` wrapper that holds a list opened up.

    A statute nests a list inside ``DD/LA/DL`` rather than under the ``DD`` itself, so the
    walk has to see through the wrapper to reach the list.
    """
    source = deepcopy(element)
    for wrapper in source.findall("LA"):
        if wrapper.find("DL") is None:
            continue
        index = list(source).index(wrapper)
        lead = wrapper.text or ""
        if index:
            source[index - 1].tail = (source[index - 1].tail or "") + lead
        else:
            source.text = (source.text or "") + lead
        children = list(wrapper)
        for offset, child in enumerate(children):
            source.insert(index + offset, child)
        if children:
            children[-1].tail = (children[-1].tail or "") + (wrapper.tail or "")
        source.remove(wrapper)
    return source


def _division_title(division: etree._Element) -> str:
    """A division prints its label above its title, and the two read as one heading."""
    label = _text(division.find("./gliederungsbez"))
    title = _text(division.find("./gliederungstitel"))
    return f"{label} {title}".strip()


def _division_number(division: etree._Element) -> str:
    """The designation a division prints, read off its label.

    A statute writes either "Teil 1" or "Erster Teil", so the designation is the numeral where
    the label carries one and the ordinal word that opens the label otherwise.
    """
    tokens = _text(division.find("./gliederungsbez")).split()
    for token in tokens:
        match = DESIGNATION.fullmatch(token)
        if match:
            return match.group(1)
    return tokens[0] if tokens else ""


def _text(element: etree._Element | None) -> str:
    """The text of one element. A list, a table and a footnote marker are all inline here.

    The pieces are joined with a space because the statutes set a list number, a defined term
    and a table cell in their own elements and print them apart.
    """
    return "" if element is None else normalize(" ".join(element.itertext()))
