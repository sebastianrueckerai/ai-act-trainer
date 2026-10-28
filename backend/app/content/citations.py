import re
from typing import NamedTuple

from pydantic import BaseModel

from app.corpus.model import Act, node_id

# Which act a written name stands for, one row per act and one table per written form. The
# empty name is the act a citation with no name in front of it means, and for an article that
# is the AI Act, because this is an AI Act course.
AI_ACT_ONLY = {"": "ai_act"}
ARTICLE_ACTS = AI_ACT_ONLY | {"GDPR": "gdpr", "DSGVO": "gdpr"}
SECTION_ACTS = {"KI-MIG": "kimig", "BDSG": "bdsg", "BetrVG": "betrvg", "GeschGehG": "geschgehg"}

# The segments below the first one, in the order a citation writes them.
SEGMENTS = ("p", "nr", "pt", "sub")


def _act_group(acts: dict[str, str]) -> str:
    """The act-name group: only the names the table carries, optional only when the
    table carries the empty name (the unnamed default act)."""
    names = [re.escape(name) for name in acts if name]
    if not names:
        return ""
    group = f"(?P<act>{'|'.join(names)})"
    return f"(?:{group} )?" if "" in acts else f"{group} "


class Form(NamedTuple):
    """One written form: how its local id opens, which acts write it, and how it is spelled."""

    prefix: str
    acts: dict[str, str]
    word: str
    pattern: re.Pattern[str]


_ART = "Art."
_SEC = "§"
_ANX = "Annex"
_RCT = "Rec."
_ITEM = "Q&A"

FORMS = (
    Form(
        "art_",
        ARTICLE_ACTS,
        _ART,
        re.compile(
            rf"{_act_group(ARTICLE_ACTS)}{re.escape(_ART)} (?P<num>\d++[a-z]?+)"
            r"(?:\((?P<p>\d+[a-z]?)\))?(?:\((?P<pt>[a-z]{1,3})\))?(?:\((?P<sub>[ivx]{1,5})\))?"
            r"(?! Abs\.| Nr\.)"
        ),
    ),
    Form(
        "sec_",
        SECTION_ACTS,
        _SEC,
        re.compile(
            rf"{_act_group(SECTION_ACTS)}{re.escape(_SEC)} (?P<num>\d+[a-z]?)"
            r"(?:\((?P<p>\d+[a-z]?)\))?(?: Nr\. (?P<nr>\d+[a-z]?))?"
        ),
    ),
    Form(
        "anx_",
        AI_ACT_ONLY,
        _ANX,
        re.compile(
            rf"{_act_group(AI_ACT_ONLY)}{re.escape(_ANX)} (?P<num>[IVX]+)"
            r"(?: pt\. (?P<p>\d+|[a-z])(?:\((?P<pt>[a-z]{1,3})\))?)?"
        ),
    ),
    Form(
        "rct_",
        AI_ACT_ONLY,
        _RCT,
        re.compile(rf"{_act_group(AI_ACT_ONLY)}{re.escape(_RCT)} (?P<num>\d+)"),
    ),
    Form(
        "item_",
        {"": "qa"},
        _ITEM,
        re.compile(rf"{_act_group({'': 'qa'})}{re.escape(_ITEM)} (?P<num>\d+)"),
    ),
)


# The name a citation writes for an act, one row per act id, first written form wins. The AI
# Act and the Commission Q&A write no name at all, because their form names them already.
ACT_NAMES: dict[str, str] = {}
for _form in FORMS:
    for _name, _act_id in _form.acts.items():
        ACT_NAMES.setdefault(_act_id, _name)

_ACT_KEY = re.compile(
    rf"\b(?P<act>{'|'.join(re.escape(act_id) for act_id in ACT_NAMES)}) +"
    rf"(?={'|'.join(re.escape(form.word) for form in FORMS)})"
)


def written_act_names(text: str) -> str:
    """Free text with every raw act id in front of a citation written as the act's name.

    A model that has read the corpus sometimes writes the manifest key it saw there, and
    "ai_act Art. 96" is neither German nor a citation the grammar reads.
    """

    def written(match: re.Match[str]) -> str:
        name = ACT_NAMES[match.group("act")]
        return f"{name} " if name else ""

    return _ACT_KEY.sub(written, text)


# What a written citation reads like on a German screen: the form's German word, the segments
# a German reader spells out, and the act's name at the end. The written grammar above stays
# English, because the curated content is written in it.
DE_FORM_WORDS = {_ANX: "Anhang", _RCT: "EG", _ITEM: "Q&A der Kommission"}
DE_ACT_NAMES = {"gdpr": "DSGVO"}
DE_SEGMENT_WORDS = {
    "art_": {"p": "Abs.", "pt": "Buchst.", "sub": "Ziff."},
    "sec_": {"p": "Abs.", "nr": "Nr."},
    "anx_": {"p": "Nr.", "pt": "Buchst."},
}
# Definition articles number their entries, so a German reader writes "Art. 3 Nr. 56".
NUMBERED_ARTICLES = {"ai_act": {"3"}, "gdpr": {"4"}}


def de_ref(ref: str) -> str:
    """One written citation as a German reader writes it, or the ref itself when it is none."""
    for form in FORMS:
        match = form.pattern.fullmatch(ref)
        if match is None:
            continue
        groups = match.groupdict()
        act_id = form.acts[groups.get("act") or ""]
        words = dict(DE_SEGMENT_WORDS.get(form.prefix, {}))
        if form.prefix == "art_" and str(groups["num"]) in NUMBERED_ARTICLES.get(act_id, ()):
            words["p"] = "Nr."
        parts = [DE_FORM_WORDS.get(form.word, form.word), str(groups["num"])]
        parts += [
            f"{words[name]} {groups[name]}"
            for name in SEGMENTS
            if name in words and groups.get(name)
        ]
        name = DE_ACT_NAMES.get(act_id, ACT_NAMES[act_id])
        return " ".join(parts + [name]) if name else " ".join(parts)
    return ref


# What an English reader is shown instead: the recital and section words spelled out, a
# section's Nummer spelled "no.", an annex's point spelled "point". An article and a Q&A item
# already read in English, and a paragraph or letter stays parenthesised rather than spelled,
# because "Art. 5(1)(f)" is how the course cites one everywhere else in English or German.
EN_FORM_WORDS = {_SEC: "Section", _RCT: "Recital"}
EN_SEGMENT_WORDS = {"sec_": {"nr": "no."}, "anx_": {"p": "point"}}


def en_ref(ref: str) -> str:
    """One written citation as an English reader writes it, or the ref itself when it is none."""
    for form in FORMS:
        match = form.pattern.fullmatch(ref)
        if match is None:
            continue
        groups = match.groupdict()
        words = EN_SEGMENT_WORDS.get(form.prefix, {})
        text = f"{EN_FORM_WORDS.get(form.word, form.word)} {groups['num']}"
        for name in SEGMENTS:
            value = groups.get(name)
            if not value:
                continue
            text += f" {words[name]} {value}" if name in words else f"({value})"
        act_id = form.acts[groups.get("act") or ""]
        name = ACT_NAMES[act_id]
        return f"{text} {name}" if name else text
    return ref


# The inverse of de_ref's own word tables: the value pattern a segment's number takes, and the
# literal word the raw grammar writes for a segment that is not purely parenthesised, so a
# citation written out in German prose can be read back into the raw ref it came from.
_NUM_PATTERN = {
    "art_": r"\d+[a-z]?",
    "sec_": r"\d+[a-z]?",
    "anx_": r"[IVX]+",
    "rct_": r"\d+",
    "item_": r"\d+",
}
_SEGMENT_VALUE = {"p": r"\d+[a-z]?", "nr": r"\d+[a-z]?", "pt": r"[a-z]{1,3}", "sub": r"[ivx]{1,5}"}
_SEGMENT_VALUE_OVERRIDE = {("anx_", "p"): r"\d+|[a-z]"}
_RAW_SEGMENT_WORDS = {"sec_": {"nr": "Nr."}, "anx_": {"p": "pt."}}


def _segment_value(prefix: str, name: str) -> str:
    return _SEGMENT_VALUE_OVERRIDE.get((prefix, name), _SEGMENT_VALUE[name])


def _de_act_names(form: Form) -> dict[str, str]:
    """German displayed name -> act id, for every act the form ever names in German.

    Built from DE_ACT_NAMES and ACT_NAMES rather than a hand-typed list, so a new row in
    SECTION_ACTS or ARTICLE_ACTS is covered here without a second edit.
    """
    return {
        DE_ACT_NAMES.get(act_id, ACT_NAMES[act_id]): act_id
        for act_id in form.acts.values()
        if DE_ACT_NAMES.get(act_id, ACT_NAMES[act_id])
    }


def _de_segment_word(prefix: str, name: str) -> str:
    word = re.escape(DE_SEGMENT_WORDS[prefix][name])
    if prefix == "art_" and name == "p":
        return rf"(?:{word}|Nr\.)"
    return word


def _de_form_pattern(form: Form) -> tuple[re.Pattern[str], dict[str, str]]:
    """The regex de_ref's own output for this form would fullmatch, and the act names it
    carries, derived from the same word tables de_ref reads rather than written twice."""
    word = re.escape(DE_FORM_WORDS.get(form.word, form.word))
    words = DE_SEGMENT_WORDS.get(form.prefix, {})
    segments = "".join(
        rf"(?: {_de_segment_word(form.prefix, name)}"
        rf" (?P<{name}>{_segment_value(form.prefix, name)}))?"
        for name in SEGMENTS
        if name in words
    )
    names = _de_act_names(form)
    if names:
        group = f"(?P<act>{'|'.join(re.escape(n) for n in sorted(names, key=len, reverse=True))})"
        optional = any(not DE_ACT_NAMES.get(a, ACT_NAMES[a]) for a in form.acts.values())
        suffix = f"(?: {group})?" if optional else f" {group}"
    else:
        suffix = ""
    pattern = re.compile(rf"{word} (?P<num>{_NUM_PATTERN[form.prefix]}){segments}{suffix}")
    return pattern, names


_DE_FORMS = [(form, *_de_form_pattern(form)) for form in FORMS]


def _raw_ref(form: Form, groups: dict[str, str | None], act_id: str) -> str:
    """The raw ref the grammar would parse back to the same node, from a German match's groups."""
    name = ACT_NAMES[act_id]
    text = f"{name} {form.word} {groups['num']}" if name else f"{form.word} {groups['num']}"
    words = _RAW_SEGMENT_WORDS.get(form.prefix, {})
    for seg in SEGMENTS:
        value = groups.get(seg)
        if not value:
            continue
        text += f" {words[seg]} {value}" if seg in words else f"({value})"
    return text


def find_german_citations(text: str) -> list[tuple[tuple[int, int], str]]:
    """Every citation de_ref would write, found inside German prose, with the raw ref it came
    from and the span it occupies: what translate_text masks before a citation reaches a model.
    """
    found: list[tuple[tuple[int, int], str]] = []
    for form, pattern, names in _DE_FORMS:
        for match in pattern.finditer(text):
            groups = match.groupdict()
            act_id = names[groups["act"]] if groups.get("act") else form.acts[""]
            found.append((match.span(), _raw_ref(form, groups, act_id)))
    found.sort(key=lambda item: item[0][0])
    return found


def with_raw_citations(text: str) -> str:
    """Free text with every citation written the German way ("Art. 4 Abs. 1") rewritten as the
    raw ref the grammar reads ("Art. 4(1)"). A citation already written raw comes back
    unchanged, so this runs in front of every scan."""
    for (start, end), ref in reversed(find_german_citations(text)):
        text = text[:start] + ref + text[end:]
    return text


class CitationError(ValueError):
    pass


class Citation(BaseModel):
    ref: str
    act_id: str
    node_id: str


def _local_id(form: Form, groups: dict[str, str | None]) -> str:
    """The id a match addresses, read segment by segment.

    A Nummer with no Absatz in front of it belongs to the first Absatz, because a section that
    numbers its Nummern without numbering its Absätze has exactly one.
    """
    parts = [form.prefix + str(groups["num"])]
    if groups.get("nr") and not groups.get("p"):
        parts.append("1")
    parts += [str(groups[name]) for name in SEGMENTS if groups.get(name)]
    return ".".join(parts)


def parse_citation(ref: str) -> Citation:
    for form in FORMS:
        match = form.pattern.fullmatch(ref)
        if match is None:
            continue
        groups = match.groupdict()
        act_id = form.acts[groups.get("act") or ""]
        return Citation(ref=ref, act_id=act_id, node_id=node_id(act_id, _local_id(form, groups)))
    raise CitationError(f"unrecognized citation: {ref!r}")


def written_ref(node_id: str) -> str:
    """The reference a citation would write for a top-level node: the inverse of parse_citation.

    Covers the nodes the grammar names at the top level, an article, a section, an annex, a
    recital or a Q&A item, addressed by act id and local id alone.
    """
    act_id, _, local_id = node_id.partition(":")
    if "." in local_id:
        raise CitationError(f"{node_id!r} is a sub-node, written_ref only covers top-level nodes")
    for form in FORMS:
        if not local_id.startswith(form.prefix):
            continue
        name = next((name for name, act in form.acts.items() if act == act_id), None)
        if name is None:
            continue
        num = local_id[len(form.prefix) :]
        return f"{name} {form.word} {num}".strip()
    raise CitationError(f"{node_id!r} has no written form in the citation grammar")


def scan_citations(text: str) -> list[Citation]:
    """Every grammar-form citation in free text, in order, deduped by node id."""
    found: list[Citation] = []
    seen: set[str] = set()
    for form in FORMS:
        for match in form.pattern.finditer(text):
            groups = match.groupdict()
            act_id = form.acts[groups.get("act") or ""]
            citation = Citation(
                ref=match.group(0),
                act_id=act_id,
                node_id=node_id(act_id, _local_id(form, groups)),
            )
            if citation.node_id not in seen:
                seen.add(citation.node_id)
                found.append(citation)
    found.sort(key=lambda c: text.find(c.ref))
    return found


def _url(act: Act, citation: Citation) -> str:
    """The act's own source, and for a regulation the anchor of the piece cited.

    A statute and a piece of guidance print one page, so they link to the page. The EUR-Lex
    page anchors its articles and annexes but not its recitals, so a recital links to the act.
    """
    if act.kind != "regulation":
        return act.source_url
    node = act.index().get(citation.node_id)
    if node is not None and node.kind == "recital":
        return act.source_url
    anchor = citation.node_id.split(":", 1)[1].split(".", 1)[0]
    return f"{act.source_url}#{anchor}"
