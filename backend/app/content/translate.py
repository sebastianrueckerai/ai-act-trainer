import argparse
from datetime import date
from pathlib import Path

import yaml
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel

from app.content.loader import load_content
from app.content.models import Chapter, LastChange, Option, Question, Rubric, Step
from app.llm.models import chat_model
from app.llm.retry import with_retry
from app.settings import get_settings

REPO_ROOT = Path(__file__).resolve().parents[3]
LANG_NAMES = {"de": "German", "en": "English"}

SYSTEM = (
    "You translate training content about the EU AI Act from {source} to {target} for employees of "
    "a company. Use plain language and address the reader as you. Use the official {target} terms "
    "of Regulation (EU) 2024/1689 for legal concepts. Keep every option key, id, name and number "
    "exactly as given, and write references to articles and paragraphs of the Regulation the way "
    "{target} law texts write them, for example Art. 4(1) in English. Leave the name and the "
    "numbering of a national law untouched, so KI-MIG § 2(1) stays KI-MIG § 2(1). Use plain ASCII "
    "punctuation, the hyphen-minus and straight quotes, never a non-breaking hyphen or a "
    "typographic dash. Do not add or remove "
    "sentences. Translate every field you are given and nothing else. Return your translation by "
    "calling the function {tool}."
)

GLOSSARY = {
    ("de", "en"): {
        "KI-Verordnung": "AI Act",
        "Anbieter": "provider",
        "Betreiber": "deployer",
        "KI-System": "AI system",
        "Hochrisiko-KI-System": "high-risk AI system",
        "KI-Kompetenz": "AI literacy",
        "in eigener Verantwortung": "under its authority",
        "Inverkehrbringen": "placing on the market",
        "Inbetriebnahme": "putting into service",
        "Marktüberwachungsbehörde": "market surveillance authority",
        "Amt für künstliche Intelligenz": "AI Office",
        "Personal": "staff",
        "Aus- und Fortbildung": "education and training",
        "Personen, bei denen die KI-Systeme eingesetzt werden": (
            "persons on whom the AI systems are to be used"
        ),
        "Personen in seinem Auftrag": "persons acting on its behalf",
    }
}


class TranslatableStep(BaseModel):
    """One teaching step: its id unchanged, its text and its example translated."""

    id: str
    text: str
    example: str | None = None


class TranslatableChapter(BaseModel):
    """The translated title, intro, summary and may line of one chapter."""

    title: str
    intro: str
    summary: str
    may: str


class TranslatableQuestion(BaseModel):
    """The translated text of one question, with the same option keys in the same order."""

    question: str
    options: list[Option] = []
    rubric: Rubric | None = None
    model_answer: str
    explanation: str


def translatable_chapter(chapter: Chapter) -> TranslatableChapter:
    return TranslatableChapter(
        title=chapter.title, intro=chapter.intro, summary=chapter.summary, may=chapter.may
    )


def translatable_steps(chapter: Chapter) -> list[TranslatableStep]:
    return [TranslatableStep(id=s.id, text=s.text, example=s.example) for s in chapter.steps]


def translatable_question(question: Question) -> TranslatableQuestion:
    return TranslatableQuestion(
        question=question.question,
        options=list(question.options),
        rubric=question.rubric,
        model_answer=question.model_answer,
        explanation=question.explanation,
    )


def _change(source_locale: str, today: date) -> LastChange:
    return LastChange(
        date=today,
        by="ai",
        trigger=f"translation from {source_locale}",
        summary="machine translation, unreviewed",
    )


def merge_chapter(
    source: Chapter,
    translated: TranslatableChapter,
    translated_steps: list[TranslatableStep],
    source_locale: str,
    today: date,
) -> Chapter:
    if [s.id for s in translated_steps] != [s.id for s in source.steps]:
        raise ValueError("translated steps do not match the source steps")
    steps = [
        Step(
            id=src.id,
            text=tr.text,
            example=tr.example,
            citations=src.citations,
            question=src.question,
        )
        for src, tr in zip(source.steps, translated_steps, strict=True)
    ]
    merged = source.model_copy(
        update={
            "title": translated.title,
            "intro": translated.intro,
            "steps": steps,
            "summary": translated.summary,
            "may": translated.may,
            "last_change": _change(source_locale, today),
        }
    )
    return Chapter.model_validate(merged.model_dump())


def merge_question(
    source: Question, translated: TranslatableQuestion, source_locale: str, today: date
) -> Question:
    if [o.key for o in translated.options] != [o.key for o in source.options]:
        raise ValueError("translated option keys do not match the source option keys")
    if (translated.rubric is None) != (source.rubric is None):
        raise ValueError("translated rubric presence does not match the source")
    merged = source.model_copy(
        update={
            "question": translated.question,
            "options": translated.options,
            "rubric": translated.rubric,
            "model_answer": translated.model_answer,
            "explanation": translated.explanation,
            "last_change": _change(source_locale, today),
        }
    )
    return Question.model_validate(merged.model_dump())


def system_prompt(source_locale: str, target_locale: str, tool: str) -> str:
    prompt = SYSTEM.format(
        source=LANG_NAMES[source_locale], target=LANG_NAMES[target_locale], tool=tool
    )
    terms = GLOSSARY.get((source_locale, target_locale))
    if terms:
        pairs = ", ".join(f"{source} = {target}" for source, target in terms.items())
        prompt += f" Translate these terms exactly so: {pairs}."
    return prompt


def _messages(payload: BaseModel, source_locale: str, target_locale: str) -> list[BaseMessage]:
    system = system_prompt(source_locale, target_locale, type(payload).__name__)
    return [SystemMessage(system), HumanMessage(payload.model_dump_json(indent=2))]


def _translate_step(
    runnable: Runnable, step: TranslatableStep, source_locale: str, target_locale: str
) -> TranslatableStep:
    result = runnable.invoke(_messages(step, source_locale, target_locale))
    if result.id != step.id:
        raise ValueError(f"translated step id {result.id!r} does not match {step.id!r}")
    return result


def translate_chapter(
    model: BaseChatModel, chapter: Chapter, source_locale: str, target_locale: str, today: date
) -> Chapter:
    """Translate a chapter with one call for its frame and one call per step.

    A whole chapter in one structured call is large enough that open-weight models
    drift out of the tool-call format most of the time. Step-sized calls do not.
    """
    frame = model.with_structured_output(TranslatableChapter, method="function_calling")
    per_step = model.with_structured_output(TranslatableStep, method="function_calling")
    translated = with_retry(
        lambda: frame.invoke(_messages(translatable_chapter(chapter), source_locale, target_locale))
    )
    steps = [
        with_retry(lambda s=step: _translate_step(per_step, s, source_locale, target_locale))
        for step in translatable_steps(chapter)
    ]
    return merge_chapter(chapter, translated, steps, source_locale, today)


def translate_question(
    model: BaseChatModel, question: Question, source_locale: str, target_locale: str, today: date
) -> Question:
    structured = model.with_structured_output(TranslatableQuestion, method="function_calling")
    messages = _messages(translatable_question(question), source_locale, target_locale)
    return with_retry(
        lambda: merge_question(question, structured.invoke(messages), source_locale, today)
    )


def _dump(item: BaseModel, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            item.model_dump(mode="json"), allow_unicode=True, sort_keys=False, width=100
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Translate missing content items with the strong model"
    )
    parser.add_argument("--from", dest="source", required=True)
    parser.add_argument("--to", dest="target", required=True)
    parser.add_argument("--only", help="translate only this chapter or question id")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--content-dir", default=str(REPO_ROOT / "content"))
    args = parser.parse_args()
    content_dir = Path(args.content_dir)
    bundle = load_content(content_dir, REPO_ROOT / "personas")
    source = bundle.locales[args.source]
    target = bundle.locales.get(args.target)
    model = chat_model(get_settings(), "strong")
    today = date.today()
    written = 0
    for chapter in source.chapters.values():
        if args.only and chapter.id != args.only:
            continue
        if target and chapter.id in target.chapters and not args.overwrite:
            continue
        out = content_dir / args.target / "chapters" / f"{chapter.id}.yaml"
        _dump(translate_chapter(model, chapter, args.source, args.target, today), out)
        written += 1
        print(f"wrote {out}")
    for question in source.questions.values():
        if args.only and question.id != args.only:
            continue
        if target and question.id in target.questions and not args.overwrite:
            continue
        out = content_dir / args.target / "questions" / f"{question.id}.yaml"
        _dump(translate_question(model, question, args.source, args.target, today), out)
        written += 1
        print(f"wrote {out}")
    print(f"translated {written} items from {args.source} to {args.target}")


if __name__ == "__main__":
    main()
