import re
import zlib
from pathlib import Path

import pytest

from app.content.loader import load_content
from app.settings import REPO_ROOT, Settings

try:
    import weasyprint  # noqa: F401
except Exception:  # pango/fontconfig missing on this host
    pytest.skip("weasyprint unavailable", allow_module_level=True)

from app.files import pdf as pdf_module
from app.files.pdf import (
    ATTRIBUTION,
    CertificateFacts,
    _split_sentences,
    _written_citations,
    render_certificate,
    render_chapter_cheat,
    render_full_cheat,
)

CONTENT = load_content(REPO_ROOT / "content", REPO_ROOT / "personas")


def _pdf_objects(pdf: bytes) -> bytes:
    """PDF 1.7 keeps object dictionaries in compressed streams; inflate them all."""
    parts = [pdf]
    for raw in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        try:
            parts.append(zlib.decompress(raw))
        except zlib.error:
            continue
    return b"".join(parts)


def test_chapter_cheat_renders_a_pdf_with_embedded_fonts(settings: Settings) -> None:
    pdf = render_chapter_cheat(settings, CONTENT, "01-warum-es-dich-betrifft", "de")

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 4000
    objects = _pdf_objects(pdf)
    assert b"/FontFile2" in objects
    assert b"Tiny5" in objects


def test_chapter_cheat_is_cached_per_chapter_and_version(settings: Settings) -> None:
    pdf_module._chapter_cache.clear()
    bumped = CONTENT.model_copy(
        update={"manifest": CONTENT.manifest.model_copy(update={"course_version": "99.0.0"})}
    )

    first = render_chapter_cheat(settings, CONTENT, "01-warum-es-dich-betrifft", "de")
    again = render_chapter_cheat(settings, CONTENT, "01-warum-es-dich-betrifft", "de")
    other_chapter = render_chapter_cheat(settings, CONTENT, "02-was-du-hineingeben-darfst", "de")
    other_version = render_chapter_cheat(settings, bumped, "01-warum-es-dich-betrifft", "de")

    assert first is again
    assert other_chapter is not first
    assert other_version is not first
    assert len(pdf_module._chapter_cache) == 3


def test_full_cheat_renders_a_pdf(settings: Settings) -> None:
    pdf = render_full_cheat(settings, CONTENT, "de", "02024R1689-20260727")

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 10000


def test_full_cheat_carries_every_chapter_and_the_attribution(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[str] = []

    def capture(html: str, fonts_dir: Path) -> bytes:
        captured.append(html)
        return b"%PDF-"

    monkeypatch.setattr(pdf_module, "_write_pdf", capture)
    render_full_cheat(settings, CONTENT, "de", "02024R1689-20260727")

    html = captured[0]
    for chapter in CONTENT.locales["de"].chapters.values():
        assert chapter.title in html
    assert ATTRIBUTION in html
    assert "Dauer:" not in html


def test_certificate_renders_with_the_name(settings: Settings) -> None:
    facts = CertificateFacts(
        score=9,
        total=10,
        passed=True,
        passed_on="2026-09-19",
        course_version="v0.1",
        law_version="02024R1689-20260727",
    )

    pdf = render_certificate(settings, "de", "Max Mustermann", facts)

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 3000


def test_split_sentences_on_chapter_ones_summary() -> None:
    chapter = CONTENT.locales["de"].chapters["01-warum-es-dich-betrifft"]

    sentences = _split_sentences(chapter.summary)

    assert len(sentences) == 8
    assert sentences[0] == (
        "Dein Unternehmen setzt KI-Systeme ein und ist damit ihr Betreiber, und du bist die "
        "Person, die sie bedient (Art. 3 Nr. 1, Art. 3 Nr. 4)."
    )
    assert sentences[6].startswith("Verboten ist das Ableiten von Emotionen")
    assert sentences[7].startswith("Ein Zertifikat verlangt die Verordnung nicht")


def test_split_sentences_keeps_an_ordinal_date_whole() -> None:
    chapter = CONTENT.locales["de"].chapters["04-hochrisiko-am-arbeitsplatz"]

    dated = [line for line in _split_sentences(chapter.summary) if "2027" in line]

    assert dated == [
        "Die Pflichten für die Systeme aus Anhang III gelten ab dem 2. Dezember 2027 (Art. 113)."
    ]


def test_written_citations_render_in_the_german_reading_style() -> None:
    chapter = CONTENT.locales["de"].chapters["01-warum-es-dich-betrifft"]

    written = _written_citations(chapter)

    assert written[0] == "Art. 3 Nr. 1"
    assert "Art. 5 Abs. 1 Buchst. f" in written
    assert "EG 44" in written
    assert "Q&A der Kommission 14" in written
    # Art. 4(1) is cited by both s2 and s3; it shows once.
    assert written.count("Art. 4 Abs. 1") == 1


def test_a_german_acts_paragraph_sign_renders_in_the_reading_style() -> None:
    chapter = CONTENT.locales["de"].chapters["07-wenn-etwas-schiefgeht"]

    written = _written_citations(chapter)

    assert "§ 2 Abs. 1 KI-MIG" in written
    assert "§ 8 KI-MIG" in written


def test_full_cheat_renders_the_summary_as_a_list(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[str] = []

    def capture(html: str, fonts_dir: Path) -> bytes:
        captured.append(html)
        return b"%PDF-"

    monkeypatch.setattr(pdf_module, "_write_pdf", capture)
    render_full_cheat(settings, CONTENT, "de", "02024R1689-20260727")

    html = captured[0]
    assert '<ul class="summary">' in html
    assert html.count("<li>") >= 8
    assert "Art. 5 Abs. 1 Buchst. f" in html
