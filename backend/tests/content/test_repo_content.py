from pathlib import Path

from app.content.citations import scan_citations, with_raw_citations
from app.content.lint import lint
from app.content.loader import load_content
from app.corpus.build import load_library

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_every_chapter_ends_on_a_cited_may_line():
    de = load_content(REPO_ROOT / "content", REPO_ROOT / "personas").locales["de"]
    opener = {}
    for chapter in de.chapters.values():
        opener[chapter.id[:2]] = chapter.may.split(":")[0]
        assert scan_citations(with_raw_citations(chapter.may)), chapter.id
    # Chapters 6, 7 and 8 grant nothing their summary says, so they say what is now known.
    assert opener == {
        "01": "Das darfst du",
        "02": "Das darfst du",
        "03": "Das darfst du",
        "04": "Das darfst du",
        "05": "Das darfst du",
        "06": "Das weißt du jetzt",
        "07": "Das weißt du jetzt",
        "08": "Das weißt du jetzt",
    }


def test_the_repo_content_lints_clean():
    bundle = load_content(REPO_ROOT / "content", REPO_ROOT / "personas")
    library = load_library(REPO_ROOT / "corpus")
    problems = lint(bundle, library)
    assert problems == [], "\n".join(f"{p.where}: {p.message}" for p in problems)
    de = bundle.locales["de"]
    assert set(de.chapters) == {
        "01-warum-es-dich-betrifft",
        "02-was-du-hineingeben-darfst",
        "03-was-dein-arbeitgeber-tun-muss",
        "04-hochrisiko-am-arbeitsplatz",
        "05-ki-gegenueber-kunden",
        "06-die-kurze-liste-der-verbote",
        "07-wenn-etwas-schiefgeht",
        "08-die-werkzeuge-die-du-nutzt",
    }
    # No chapter is a stub any more: all eight are written in shape B.
    assert [c.stub for c in de.chapters.values()] == [False] * 8
    assert len(de.questions) == 45
    by_type: dict[str, int] = {}
    for q in de.questions.values():
        by_type[q.type] = by_type.get(q.type, 0) + 1
    assert by_type == {"yes_no": 21, "multiple_choice": 13, "free_text": 11}
    # Every step of every chapter carries its own neighbouring case (D76). D125: a
    # closed question is picked and carries its why as an ask, so the attached mix has
    # no cap; the bank keeps every type per chapter (the lint checks that).
