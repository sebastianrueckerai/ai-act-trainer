import argparse
import re
import sys
from collections.abc import Container, Iterable
from pathlib import Path

from pydantic import BaseModel

from app.content.citations import (
    FORMS,
    CitationError,
    parse_citation,
    scan_citations,
    with_raw_citations,
)
from app.content.gender import find_gendered
from app.content.law_summaries import SUMMARY_KINDS, source_sha
from app.content.loader import load_content
from app.content.models import Chapter, ContentBundle, LocaleContent, PersonaManifest, Step
from app.corpus.build import load_library
from app.corpus.excerpt import excerpt
from app.corpus.model import LABELS, Library

REPO_ROOT = Path(__file__).resolve().parents[3]

# The written forms parse only English abbreviations (Art., Annex, Rec.). A German summary
# leaking a citation is more likely to spell the label out, so this checks the same labels the
# corpus renders a citation with. Kapitel joins them although the grammar writes no
# citation for it, because a chapter number in a summary goes stale the same way.
_DE_LABEL_CITATION = re.compile(
    "|".join(
        rf"{re.escape(word)} (?:\d+[a-z]?|[IVX]+)" for word in (*LABELS["de"].values(), "Kapitel")
    )
)

# Law text is printed with no-break spaces and non-breaking hyphens, and a summary that copies
# one would slip a citation past every pattern above, so the check runs on plain characters.
_PLAIN = str.maketrans({" ": " ", " ": " ", " ": " ", "‑": "-"})


# A German ordinal ("ab dem 2. Dezember 2027") carries a full stop that ends no sentence,
# so a stop after a digit never splits.
_SENTENCE_SPLIT = re.compile(r"(?<![\d])(?<=[.!?])\s+")
_WORD = re.compile(r"[^\w\s]", re.UNICODE)
# A step longer than this is a wall of text, whatever it teaches.
_MAX_STEP_WORDS = 120
# A stem that asks two things, and a must point that holds two facts (D119).
_TWO_THINGS = re.compile(r",\s*und\s+(warum|wer|wen|wem|wessen|was|wohin|von wem)\b[^?]*\?\s*$")
_TWO_FACTS = re.compile(r"\b(weil|und zwar)\b|\bund ob\b")


class Problem(BaseModel):
    where: str
    message: str


def lint_persona_images(personas: Iterable[PersonaManifest], personas_dir: Path) -> list[str]:
    missing: list[str] = []
    for persona in personas:
        for emotion in persona.emotions:
            path = personas_dir / persona.id / "images" / f"{emotion}.png"
            if not path.is_file():
                missing.append(f"{persona.id}/images/{emotion}.png")
    return missing


def _shared_chapter(chapter) -> dict:
    return {
        "duration_minutes": chapter.duration_minutes,
        "stub": chapter.stub,
        "steps": [(s.id, tuple(s.citations), s.question) for s in chapter.steps],
    }


def _shared_question(question) -> dict:
    return {
        "chapter": question.chapter,
        "type": question.type,
        "difficulty": question.difficulty,
        "correct": question.correct,
        "options": [o.key for o in question.options],
        "citations": tuple(question.citations),
    }


def lint(bundle: ContentBundle, library: Library) -> list[Problem]:
    problems: list[Problem] = []
    reference = bundle.locales[bundle.manifest.reference_locale]
    if not reference.chapters or not reference.questions:
        problems.append(
            Problem(
                where=bundle.manifest.reference_locale,
                message=(
                    "no chapters or no questions in the reference locale, "
                    "which usually means the content directory is wrong"
                ),
            )
        )
    if not bundle.personas:
        problems.append(
            Problem(
                where="personas",
                message="no personas, which usually means the personas directory is wrong",
            )
        )
    for locale, content in bundle.locales.items():
        for chapter in content.chapters.values():
            _check_gendered(problems, f"{locale}/{chapter.id}", chapter.title)
            _check_gendered(problems, f"{locale}/{chapter.id}", chapter.intro)
            _check_gendered(problems, f"{locale}/{chapter.id}", chapter.summary)
            _check_gendered(problems, f"{locale}/{chapter.id}", chapter.may)
            _check_may(problems, library, f"{locale}/{chapter.id}", chapter.may)
            for step in chapter.steps:
                for ref in step.citations:
                    _check_citation(problems, library, f"{locale}/{chapter.id}/{step.id}", ref)
                _check_gendered(problems, f"{locale}/{chapter.id}/{step.id}", step.text)
                _check_gendered(problems, f"{locale}/{chapter.id}/{step.id}", step.example)
                _check_step_question(problems, content, chapter, step)
            if not chapter.stub:
                types = {q.type for q in content.questions.values() if q.chapter == chapter.id}
                for needed in ("yes_no", "multiple_choice", "free_text"):
                    if needed not in types:
                        problems.append(
                            Problem(
                                where=f"{locale}/{chapter.id}",
                                message=f"chapter has no {needed} question",
                            )
                        )
        _check_chapter_prose(problems, content)
        for question in content.questions.values():
            if question.chapter not in content.chapters:
                problems.append(
                    Problem(
                        where=f"{locale}/{question.id}",
                        message=f"chapter {question.chapter} does not exist",
                    )
                )
            elif content.chapters[question.chapter].stub:
                problems.append(
                    Problem(
                        where=f"{locale}/{question.id}",
                        message=(
                            f"chapter {question.chapter} is a stub and teaches nothing, "
                            "so no question may sit on it"
                        ),
                    )
                )
            for ref in question.citations:
                _check_citation(problems, library, f"{locale}/{question.id}", ref)
            _check_gendered(problems, f"{locale}/{question.id}", question.question)
            _check_gendered(problems, f"{locale}/{question.id}", question.model_answer)
            _check_gendered(problems, f"{locale}/{question.id}", question.explanation)
            for option in question.options:
                _check_gendered(problems, f"{locale}/{question.id}", option.text)
            if question.type == "free_text" and _TWO_THINGS.search(question.question):
                problems.append(
                    Problem(
                        where=f"{locale}/{question.id}",
                        message="the question asks two things; the second is an ask (D119)",
                    )
                )
            if question.rubric:
                for point in question.rubric.must:
                    if point.ask:
                        _check_gendered(problems, f"{locale}/{question.id}", point.ask)
                        if point.point.lower() in point.ask.lower():
                            problems.append(
                                Problem(
                                    where=f"{locale}/{question.id}",
                                    message=f"ask repeats its point: {point.ask}",
                                )
                            )
                    if _TWO_FACTS.search(point.point):
                        problems.append(
                            Problem(
                                where=f"{locale}/{question.id}",
                                message=f"a must point holds two facts: {point.point}",
                            )
                        )
        if locale == bundle.manifest.reference_locale:
            continue
        for kind, ref_items, items in (
            ("chapter", reference.chapters, content.chapters),
            ("question", reference.questions, content.questions),
        ):
            for item_id in sorted(set(ref_items) - set(items)):
                problems.append(
                    Problem(
                        where=f"{locale}", message=f"{kind} {item_id} missing in locale {locale}"
                    )
                )
            for item_id in sorted(set(items) - set(ref_items)):
                problems.append(
                    Problem(
                        where=f"{locale}",
                        message=f"{kind} {item_id} exists only in locale {locale}",
                    )
                )
        for chapter_id in set(reference.chapters) & set(content.chapters):
            a, b = (
                _shared_chapter(reference.chapters[chapter_id]),
                _shared_chapter(content.chapters[chapter_id]),
            )
            for key in a:
                if a[key] != b[key]:
                    problems.append(
                        Problem(
                            where=f"{locale}/{chapter_id}",
                            message=(
                                f"{key} differ from {bundle.manifest.reference_locale}: "
                                f"{a[key]!r} vs {b[key]!r}"
                            ),
                        )
                    )
        for question_id in set(reference.questions) & set(content.questions):
            a, b = (
                _shared_question(reference.questions[question_id]),
                _shared_question(content.questions[question_id]),
            )
            for key in a:
                if a[key] != b[key]:
                    problems.append(
                        Problem(
                            where=f"{locale}/{question_id}",
                            message=(
                                f"{key} differ from {bundle.manifest.reference_locale}: "
                                f"{a[key]!r} vs {b[key]!r}"
                            ),
                        )
                    )
    for persona in bundle.personas.values():
        for locale in bundle.manifest.locales:
            if locale not in persona.name or locale not in persona.tagline:
                problems.append(
                    Problem(
                        where=f"persona/{persona.id}",
                        message=f"missing name or tagline for locale {locale}",
                    )
                )
                continue
            _check_gendered(problems, f"persona/{persona.id}", persona.name[locale])
            _check_gendered(problems, f"persona/{persona.id}", persona.tagline[locale])
        curated = [
            line
            for group in (persona.verdicts, persona.milestones)
            for lines in group.values()
            for line in lines
        ]
        for reaction in [*persona.reactions.values(), *curated]:
            _check_gendered(problems, f"persona/{persona.id}", reaction)
    if not bundle.law:
        problems.append(
            Problem(
                where="law",
                message="law summaries are missing entirely, run tools/summarize-law",
            )
        )
    else:
        missing = _nodes_without_summary(library, bundle.law)
        if missing:
            listed = ", ".join(missing[:10])
            rest = len(missing) - 10
            suffix = f" and {rest} more" if rest > 0 else ""
            problems.append(
                Problem(
                    where="law",
                    message=f"{len(missing)} nodes have no summary: {listed}{suffix}",
                )
            )
    for node_id, law_summary in bundle.law.items():
        where = f"law/{node_id}"
        if library.node(node_id) is None:
            problems.append(
                Problem(
                    where=where,
                    message=f"summary names {node_id}, which the library does not hold",
                )
            )
        elif law_summary.source_sha != source_sha(library, node_id):
            problems.append(
                Problem(
                    where=where,
                    message=(
                        f"source_sha for {node_id} is stale, "
                        "run tools/summarize-law --changed to rewrite it"
                    ),
                )
            )
        citation = _citation_in_text(law_summary.summary)
        if citation:
            problems.append(
                Problem(where=where, message=f"summary carries a citation: {citation!r}")
            )
        _check_gendered(problems, where, law_summary.summary)
    return problems


def _nodes_without_summary(library: Library, summarised: Container[str]) -> list[str]:
    """Every act, division, article and annex with no summary, in reading order."""
    missing: list[str] = []

    def visit(node_id: str) -> None:
        node = library.node(node_id)
        if node is not None and node.kind in SUMMARY_KINDS and node_id not in summarised:
            missing.append(node_id)
        for child in library.children(node_id):
            visit(child.id)

    for act_id in library.acts:
        visit(act_id)
    return missing


def _citation_in_text(text: str) -> str | None:
    text = text.translate(_PLAIN)
    for form in FORMS:
        match = form.pattern.search(text)
        if match:
            return match.group(0)
    match = _DE_LABEL_CITATION.search(text)
    return match.group(0) if match else None


def _split_sentences(text: str | None) -> list[str]:
    if not text:
        return []
    return [part.strip() for part in _SENTENCE_SPLIT.split(text.strip()) if part.strip()]


def _normalise(sentence: str) -> str:
    """A sentence stripped to its words: lowercased, punctuation and whitespace collapsed."""
    return " ".join(_WORD.sub(" ", sentence.lower()).split())


def _sentences(text: str | None) -> dict[str, str]:
    """Every sentence of a text, by its normalised form."""
    return {_normalise(part): part for part in _split_sentences(text)}


def _check_chapter_prose(problems: list[Problem], content: LocaleContent) -> None:
    """Each teaching point stands once, and no step grows into a wall of text.

    A sentence that stands twice anywhere in the course's prose is a point taught twice, so
    the second place is the problem: it re-explains what an earlier step already said.
    """
    seen: dict[str, str] = {}
    for chapter_id in sorted(content.chapters):
        chapter = content.chapters[chapter_id]
        prose = [(f"{content.locale}/{chapter_id}", "intro", chapter.intro)]
        for step in chapter.steps:
            where = f"{content.locale}/{chapter_id}/{step.id}"
            words = len(step.text.split())
            if words > _MAX_STEP_WORDS:
                problems.append(
                    Problem(
                        where=where,
                        message=f"step text is {words} words, the limit is {_MAX_STEP_WORDS}",
                    )
                )
            prose.append((where, "text", step.text))
            if step.example:
                prose.append((where, "example", step.example))
        for where, field, text in prose:
            for sentence in _split_sentences(text):
                first = seen.setdefault(_normalise(sentence), f"{where} {field}")
                if first != f"{where} {field}":
                    problems.append(
                        Problem(
                            where=where,
                            message=(
                                f"{field} repeats a sentence that already stands "
                                f'in {first}: "{sentence}"'
                            ),
                        )
                    )


def _check_step_question(
    problems: list[Problem], content: LocaleContent, chapter: Chapter, step: Step
) -> None:
    """A step's question must exist, sit on this chapter, and ask more than the step said."""
    if step.question is None:
        return
    where = f"{content.locale}/{chapter.id}/{step.id}"
    question = content.questions.get(step.question)
    if question is None:
        problems.append(
            Problem(where=where, message=f"step question {step.question} does not exist")
        )
        return
    if question.chapter != chapter.id:
        problems.append(
            Problem(
                where=where, message=f"step question {step.question} belongs to another chapter"
            )
        )
    taught = _sentences(step.text) | _sentences(step.example)
    for normalised in _sentences(question.question):
        if normalised in taught:
            problems.append(
                Problem(
                    where=where, message=f'step question repeats the step: "{taught[normalised]}"'
                )
            )
            return


def _check_citation(problems: list[Problem], library: Library, where: str, ref: str) -> None:
    try:
        excerpt(library, parse_citation(ref))
    except CitationError as exc:
        problems.append(Problem(where=where, message=str(exc)))


def _check_may(problems: list[Problem], library: Library, where: str, may: str) -> None:
    """The may line makes a legal claim, so it cites, and every citation resolves."""
    citations = scan_citations(with_raw_citations(may))
    if not citations:
        problems.append(Problem(where=where, message="the may line cites nothing"))
    for citation in citations:
        _check_citation(problems, library, where, citation.ref)


def _check_gendered(problems: list[Problem], where: str, text: str | None) -> None:
    if not text:
        return
    forms = find_gendered(text)
    if forms:
        problems.append(Problem(where=where, message=f"uses gendered German: {', '.join(forms)}"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Lint the course content against the library")
    parser.add_argument("--content-dir", default=str(REPO_ROOT / "content"))
    parser.add_argument("--personas-dir", default=str(REPO_ROOT / "personas"))
    parser.add_argument("--corpus-dir", default=str(REPO_ROOT / "corpus"))
    parser.add_argument("--overlay-dir")
    args = parser.parse_args()
    overlay = Path(args.overlay_dir) if args.overlay_dir else None
    bundle = load_content(Path(args.content_dir), Path(args.personas_dir), overlay)
    library = load_library(Path(args.corpus_dir))
    problems = lint(bundle, library)
    for problem in problems:
        print(f"{problem.where}: {problem.message}")
    if problems:
        sys.exit(1)
    chapters = sum(len(c.chapters) for c in bundle.locales.values())
    questions = sum(len(c.questions) for c in bundle.locales.values())
    print(
        f"content ok: {chapters} chapters, {questions} questions, {len(bundle.personas)} "
        f"personas, {len(bundle.law)} law summaries"
    )


if __name__ == "__main__":
    main()
