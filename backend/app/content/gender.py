"""Deterministic enforcement of the generic masculine in German text.

The product never genders: no star, colon, underscore, middle dot, slash or Binnen-I form,
no paired form ("Nutzerinnen und Nutzer"), no participle substitute ("Mitarbeitende"). A
prompt rule alone does not hold, so this rewrites model output and lints curated content.
"""

import re

_STEM = r"[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]*"
_SEP = r"(?:\*|:|_|·|/-|/)"

_PLURAL_SEP = re.compile(rf"\b({_STEM}){_SEP}innen\b")
_SINGULAR_SEP = re.compile(rf"\b({_STEM}){_SEP}in\b")
_PLURAL_BINNEN = re.compile(r"\b([A-ZÄÖÜ][a-zäöüß]*)Innen\b")
_SINGULAR_BINNEN = re.compile(r"\b([A-ZÄÖÜ][a-zäöüß]*)In\b")

_PARTICIPLE = re.compile(r"\b(Mitarbeitend|Nutzend|Teilnehmend|Studierend)(en|er|es|em|e)\b")

_PAIR = re.compile(r"\b([A-ZÄÖÜ][a-zäöüß]+)\s+(?:und|oder|bzw\.)\s+([A-ZÄÖÜ][a-zäöüß]+)\b")

_TRAILING_WORD = re.compile(r"(\w+)(\s*)$")

_PRONOUN_FORMS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b([Jj]ede)(?:\*r|:r|_r)\b"), "jeder"),
    (re.compile(r"\b([Ee]in)(?:\*e|:e)\b"), "ein"),
    (re.compile(r"\b([Ee]ine)(?:\*n|:n)\b"), "einen"),
    (re.compile(r"\b([Dd]er)(?:\*die|/die)\b"), "der"),
    (re.compile(r"\b([Dd]ie)(?:\*der|/der)\b"), "der"),
    (re.compile(r"\b([Ee]r)(?:\*sie|/sie)\b"), "er"),
    (re.compile(r"\b([Ss]ie)(?:\*er|/er)\b"), "er"),
]

PLURAL_EXCEPTIONS = {
    "Ärzt": "Ärzte",
    "Anwält": "Anwälte",
    "Köch": "Köche",
    "Bäuer": "Bauern",
    "Chef": "Chefs",
    "Ingenieur": "Ingenieure",
    "Beamt": "Beamte",
    "Freund": "Freunde",
}
SINGULAR_EXCEPTIONS = {
    "Ärzt": "Arzt",
    "Anwält": "Anwalt",
    "Köch": "Koch",
    "Bäuer": "Bauer",
    "Chef": "Chef",
    "Ingenieur": "Ingenieur",
    "Beamt": "Beamter",
    "Freund": "Freund",
}
PARTICIPLE_MAP = {
    "Mitarbeitende": "Mitarbeiter",
    "Mitarbeitenden": "Mitarbeiter",
    "Nutzende": "Nutzer",
    "Teilnehmende": "Teilnehmer",
    "Studierende": "Studenten",
}
ARTICLE_MAP = {
    "eine": "ein",
    "einer": "einem",
    "die": "der",
    "jede": "jeder",
    "jeder": "jedem",
    "keine": "kein",
    "keiner": "keinem",
    "meine": "mein",
    "deine": "dein",
    "unsere": "unser",
    "ihre": "ihr",
    "seine": "sein",
}


def _plural_form(stem: str) -> str:
    if stem in PLURAL_EXCEPTIONS:
        return PLURAL_EXCEPTIONS[stem]
    return stem if stem.endswith("er") else stem + "en"


def _singular_form(stem: str) -> str:
    if stem in SINGULAR_EXCEPTIONS:
        return SINGULAR_EXCEPTIONS[stem]
    return stem if stem.endswith("er") else stem + "e"


def _cap_like(sample: str, replacement: str) -> str:
    if sample[:1].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def _fem_stem(word: str) -> str | None:
    if word.endswith("innen"):
        stem = word[:-5]
    elif word.endswith("in"):
        stem = word[:-2]
    else:
        return None
    return stem if len(stem) >= 3 else None


def _pair_masculine(word1: str, word2: str) -> str | None:
    for fem, other in ((word1, word2), (word2, word1)):
        stem = _fem_stem(fem)
        if stem is not None and other in {stem, stem + "e", stem + "en", stem + "n"}:
            return other
    return None


def _fix_determiner(segment: str) -> str:
    match = _TRAILING_WORD.search(segment)
    if not match:
        return segment
    replacement = ARTICLE_MAP.get(match.group(1).lower())
    if replacement is None:
        return segment
    replacement = _cap_like(match.group(1), replacement)
    return segment[: match.start(1)] + replacement + match.group(2)


def _all_matches(text: str) -> list[tuple[int, int, str, str]]:
    found: list[tuple[int, int, str, str]] = []

    for m in _PLURAL_SEP.finditer(text):
        found.append((m.start(), m.end(), "plural", _plural_form(m.group(1))))
    for m in _PLURAL_BINNEN.finditer(text):
        found.append((m.start(), m.end(), "plural", _plural_form(m.group(1))))
    for m in _SINGULAR_SEP.finditer(text):
        found.append((m.start(), m.end(), "singular", _singular_form(m.group(1))))
    for m in _SINGULAR_BINNEN.finditer(text):
        found.append((m.start(), m.end(), "singular", _singular_form(m.group(1))))
    for pattern, base in _PRONOUN_FORMS:
        for m in pattern.finditer(text):
            found.append((m.start(), m.end(), "pronoun", _cap_like(m.group(0), base)))
    for m in _PARTICIPLE.finditer(text):
        found.append((m.start(), m.end(), "participle", PARTICIPLE_MAP.get(m.group(0), m.group(0))))
    for m in _PAIR.finditer(text):
        masculine = _pair_masculine(m.group(1), m.group(2))
        if masculine is not None:
            found.append((m.start(), m.end(), "pair", masculine))

    found.sort(key=lambda item: item[0])

    resolved: list[tuple[int, int, str, str]] = []
    last_end = -1
    for start, end, kind, replacement in found:
        if start >= last_end:
            resolved.append((start, end, kind, replacement))
            last_end = end
    return resolved


def find_gendered(text: str) -> list[str]:
    """Every offending form in the text, verbatim, in order."""
    return [text[start:end] for start, end, _, _ in _all_matches(text)]


def degender(text: str) -> str:
    """Rewrite gendered forms to the generic masculine. Idempotent; unmatched text is unchanged."""
    matches = _all_matches(text)
    if not matches:
        return text
    parts: list[str] = []
    last_end = 0
    for start, end, kind, replacement in matches:
        segment = text[last_end:start]
        if kind == "singular":
            segment = _fix_determiner(segment)
        parts.append(segment)
        parts.append(replacement)
        last_end = end
    parts.append(text[last_end:])
    return "".join(parts)
