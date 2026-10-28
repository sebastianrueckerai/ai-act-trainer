from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.content.citations import de_ref
from app.content.loader import ContentBundle
from app.content.models import Chapter
from app.i18n import format_date, t
from app.settings import Settings

ATTRIBUTION = (
    "© European Union, 2024-2026, eur-lex.europa.eu, reused under Commission "
    "Decision 2011/833/EU. Only the Official Journal is authentic."
)

_chapter_cache: dict[tuple[str, str, str], bytes] = {}

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html.j2"]),
)


@dataclass(frozen=True)
class CertificateFacts:
    score: int
    total: int
    passed: bool
    passed_on: str
    course_version: str
    law_version: str


def _write_pdf(html: str, fonts_dir: Path) -> bytes:
    from weasyprint import HTML  # lazy: a host without pango still boots the app

    return HTML(string=html, base_url=str(fonts_dir)).write_pdf()


def _written_citations(chapter: Chapter) -> list[str]:
    written: dict[str, str] = {}
    for step in chapter.steps:
        for ref in step.citations:
            written.setdefault(ref, de_ref(ref))
    return list(written.values())


# A sentence end followed by a capital letter, unless what stands right before it is one of
# the abbreviations below or a bare ordinal number ("2. Dezember 2027").
_ABBREVIATIONS = ("Art.", "Abs.", "Nr.", "Buchst.", "z. B.", "u. a.", "d. h.")
_ORDINAL = re.compile(r"\d[a-z]?\.$")
_SENTENCE_END = re.compile(r"(?<=[.!?]) (?=[A-ZÄÖÜ])")


def _split_sentences(text: str) -> list[str]:
    sentences = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        before = text[: match.start()]
        if before.endswith(_ABBREVIATIONS) or _ORDINAL.search(before):
            continue
        sentences.append(text[start : match.start() + 1].strip())
        start = match.start() + 1
    sentences.append(text[start:].strip())
    return [sentence for sentence in sentences if sentence]


def _chapter_view(chapter: Chapter, locale: str) -> dict:
    return {
        "title": chapter.title,
        "stub": chapter.stub,
        "summary_sentences": _split_sentences(chapter.summary),
        "citations": _written_citations(chapter),
    }


def render_chapter_cheat(
    settings: Settings, content: ContentBundle, chapter_id: str, locale: str
) -> bytes:
    course_version = content.manifest.course_version
    key = (chapter_id, course_version, locale)
    if key not in _chapter_cache:
        chapter = content.locales[locale].chapters[chapter_id]
        heading = chapter.title
        if chapter.stub:
            heading = f"{heading} {t(locale, 'cheatsheet_stub_marker')}"
        html = _env.get_template("cheat.html.j2").render(
            title=t(locale, "cheatsheet_chapter_title", title=heading),
            chapters=[_chapter_view(chapter, locale)],
            meta_line=None,
            attribution=None,
        )
        _chapter_cache[key] = _write_pdf(html, settings.fonts_dir)
    return _chapter_cache[key]


def render_full_cheat(
    settings: Settings, content: ContentBundle, locale: str, law_version: str
) -> bytes:
    chapters = sorted(content.locales[locale].chapters.values(), key=lambda c: c.id)
    html = _env.get_template("cheat.html.j2").render(
        title=t(locale, "cheatsheet_full_title"),
        chapters=[_chapter_view(chapter, locale) for chapter in chapters],
        stub_marker=t(locale, "cheatsheet_stub_marker"),
        meta_line=t(
            locale,
            "cheatsheet_meta_line",
            course=content.manifest.course_version,
            law=law_version,
        ),
        attribution=ATTRIBUTION,
    )
    return _write_pdf(html, settings.fonts_dir)


def render_certificate(
    settings: Settings, locale: str, name: str, facts: CertificateFacts
) -> bytes:
    html = _env.get_template("certificate.html.j2").render(
        title=t(locale, "certificate_title"),
        name=name,
        body_line=t(
            locale,
            "certificate_body",
            date=format_date(locale, facts.passed_on),
            score=facts.score,
            total=facts.total,
        ),
        meta_line=t(
            locale,
            "certificate_meta_line",
            course=facts.course_version,
            law=facts.law_version,
        ),
    )
    return _write_pdf(html, settings.fonts_dir)
