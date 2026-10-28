import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

from app.content import translate
from app.content.models import Chapter, LastChange, MustPoint, Option, Question, Rubric, Step
from app.content.translate import (
    TranslatableChapter,
    TranslatableQuestion,
    TranslatableStep,
    merge_chapter,
    merge_question,
    system_prompt,
    translatable_chapter,
    translatable_question,
    translatable_steps,
    translate_chapter,
    translate_question,
)
from app.settings import Settings
from tests.test_llm_retry import tool_use_failed


def make_question() -> Question:
    return Question(
        id="q-01-03",
        chapter="01-x",
        type="multiple_choice",
        difficulty=2,
        question="Seit wann gilt Artikel 4?",
        options=[
            Option(key=k, text=t)
            for k, t in (("A", "1. August 2024"), ("B", "2. Februar 2025"), ("C", "2. August 2026"))
        ],
        correct="B",
        model_answer="Seit dem 2. Februar 2025.",
        explanation="Artikel 113 nennt das Datum.",
        citations=["Art. 113"],
        last_change=LastChange(date=date(2026, 9, 15), by="human", trigger="initial", summary="x"),
    )


def make_free_text_question() -> Question:
    return Question(
        id="q-01-05",
        chapter="01-x",
        type="free_text",
        difficulty=2,
        question="Worin unterscheiden sich Anbieter und Betreiber?",
        rubric=Rubric(
            must=[MustPoint(point="nennt den Anbieter", ask="Wer stellt es bereit?")],
            should=["nennt ein Beispiel"],
        ),
        model_answer="Der Anbieter entwickelt, der Betreiber verwendet.",
        explanation="Art. 3 Nr. 3 und Nr. 4 trennen die Rollen.",
        citations=["Art. 3(3)", "Art. 3(4)"],
        last_change=LastChange(date=date(2026, 9, 15), by="human", trigger="initial", summary="x"),
    )


def make_chapter() -> Chapter:
    return Chapter(
        id="01-x",
        title="Warum die KI-Verordnung dich betrifft",
        intro="Dieses Kapitel zeigt dir, was die KI-Verordnung ist.",
        duration_minutes=8,
        steps=[
            Step(
                id="s1",
                text="Die KI-Verordnung ist das KI-Gesetz der EU.",
                example="Du schreibst Kundenmails mit einem Chatassistenten.",
                citations=["Art. 1", "Art. 113"],
                question="q-01-01",
            ),
            Step(id="s2", text="Betreiber verwenden ein KI-System.", citations=["Art. 3(4)"]),
        ],
        summary="Die KI-Verordnung schützt Grundrechte.",
        may="Das darfst du: Kundenmails mit KI schreiben (Art. 50).",
        last_change=LastChange(date=date(2026, 9, 15), by="human", trigger="initial", summary="x"),
    )


def test_translatable_question_carries_only_text_fields():
    payload = translatable_question(make_question())
    assert payload.question == "Seit wann gilt Artikel 4?"
    assert [o.key for o in payload.options] == ["A", "B", "C"]
    assert payload.rubric is None
    assert not hasattr(payload, "citations")


def test_translatable_question_carries_the_rubric_of_a_free_text_question():
    payload = translatable_question(make_free_text_question())
    assert payload.options == []
    assert payload.rubric is not None
    assert payload.rubric.must_texts == ["nennt den Anbieter"]


def test_merge_question_keeps_shared_fields_and_marks_ai_change():
    source = make_question()
    translated = TranslatableQuestion(
        question="Since when does Article 4 apply?",
        options=[
            Option(key="A", text="1 August 2024"),
            Option(key="B", text="2 February 2025"),
            Option(key="C", text="2 August 2026"),
        ],
        rubric=None,
        model_answer="Since 2 February 2025.",
        explanation="Article 113 names the date.",
    )
    merged = merge_question(source, translated, "de", date(2026, 9, 16))
    assert merged.id == source.id and merged.correct == "B" and merged.citations == ["Art. 113"]
    assert merged.chapter == "01-x" and merged.type == "multiple_choice" and merged.difficulty == 2
    assert merged.question == "Since when does Article 4 apply?"
    assert merged.options[1].text == "2 February 2025"
    assert merged.last_change.by == "ai"
    assert merged.last_change.trigger == "translation from de"
    assert merged.last_change.date == date(2026, 9, 16)
    assert merged.last_change.summary == "machine translation, unreviewed"


def test_merge_question_rejects_changed_option_keys():
    source = make_question()
    translated = TranslatableQuestion(
        question="x",
        options=[Option(key="A", text="a"), Option(key="B", text="b"), Option(key="D", text="d")],
        rubric=None,
        model_answer="m",
        explanation="e",
    )
    with pytest.raises(ValueError, match="option keys"):
        merge_question(source, translated, "de", date(2026, 9, 16))


def test_merge_question_rejects_a_dropped_rubric():
    source = make_free_text_question()
    translated = TranslatableQuestion(
        question="x", options=[], rubric=None, model_answer="m", explanation="e"
    )
    with pytest.raises(ValueError, match="rubric"):
        merge_question(source, translated, "de", date(2026, 9, 16))


def test_merge_question_revalidates_the_merged_item():
    source = make_free_text_question()
    translated = TranslatableQuestion.model_construct(
        question="How do provider and deployer differ?",
        options=[],
        rubric=Rubric.model_construct(must=[], should=[]),
        model_answer="m",
        explanation="e",
    )
    with pytest.raises(ValueError, match="must"):
        merge_question(source, translated, "de", date(2026, 9, 16))


def translated_chapter() -> TranslatableChapter:
    return TranslatableChapter(
        title="Why the AI Act concerns you",
        intro="This chapter shows you what the AI Act is.",
        summary="The AI Act protects fundamental rights.",
        may="You may: write customer mails with AI (Art. 50).",
    )


def translated_steps() -> list[TranslatableStep]:
    return [
        TranslatableStep(
            id="s1",
            text="The AI Act is the AI law of the EU.",
            example="You write customer mails with a chat assistant.",
        ),
        TranslatableStep(id="s2", text="Deployers use an AI system.", example=None),
    ]


def test_translatable_chapter_carries_only_the_frame_text():
    payload = translatable_chapter(make_chapter())
    assert payload.title == "Warum die KI-Verordnung dich betrifft"
    assert payload.summary == "Die KI-Verordnung schützt Grundrechte."
    assert payload.may == "Das darfst du: Kundenmails mit KI schreiben (Art. 50)."
    assert not hasattr(payload, "steps")
    assert not hasattr(payload, "duration_minutes")


def test_translatable_steps_carry_only_text_fields():
    steps = translatable_steps(make_chapter())
    assert [s.id for s in steps] == ["s1", "s2"]
    assert steps[0].example == "Du schreibst Kundenmails mit einem Chatassistenten."
    assert steps[1].example is None
    assert not hasattr(steps[0], "citations")
    assert not hasattr(steps[0], "question")


def test_merge_chapter_keeps_shared_fields_and_marks_ai_change():
    source = make_chapter()
    merged = merge_chapter(
        source, translated_chapter(), translated_steps(), "de", date(2026, 9, 16)
    )
    assert merged.id == "01-x" and merged.duration_minutes == 8
    assert [s.question for s in merged.steps] == ["q-01-01", None]
    assert [s.id for s in merged.steps] == ["s1", "s2"]
    assert [s.citations for s in merged.steps] == [["Art. 1", "Art. 113"], ["Art. 3(4)"]]
    assert merged.title == "Why the AI Act concerns you"
    assert merged.intro == "This chapter shows you what the AI Act is."
    assert merged.steps[0].example == "You write customer mails with a chat assistant."
    assert merged.steps[1].example is None
    assert merged.summary == "The AI Act protects fundamental rights."
    assert merged.may == "You may: write customer mails with AI (Art. 50)."
    assert merged.last_change.by == "ai"
    assert merged.last_change.trigger == "translation from de"
    assert merged.last_change.date == date(2026, 9, 16)


def test_merge_chapter_rejects_a_changed_step_count():
    source = make_chapter()
    steps = [TranslatableStep(id="s1", text="one step only")]
    with pytest.raises(ValueError, match="steps"):
        merge_chapter(source, translated_chapter(), steps, "de", date(2026, 9, 16))


def test_merge_chapter_rejects_renamed_steps():
    source = make_chapter()
    steps = [TranslatableStep(id="s1", text="a"), TranslatableStep(id="step-2", text="b")]
    with pytest.raises(ValueError, match="steps"):
        merge_chapter(source, translated_chapter(), steps, "de", date(2026, 9, 16))


def test_system_prompt_names_the_languages_and_the_tool():
    prompt = system_prompt("de", "en", "TranslatableQuestion")
    assert "from German to English" in prompt
    assert "TranslatableQuestion" in prompt


def test_system_prompt_carries_the_official_terms_of_the_pair():
    prompt = system_prompt("de", "en", "TranslatableQuestion")
    assert "Betreiber = deployer" in prompt
    assert "KI-Kompetenz = AI literacy" in prompt
    assert "KI-Verordnung = AI Act" in prompt


def test_system_prompt_without_a_glossary_for_the_pair():
    prompt = system_prompt("en", "de", "TranslatableQuestion")
    assert "from English to German" in prompt
    assert "=" not in prompt


@dataclass
class StubModel:
    """A chat model that answers every structured call from a canned payload.

    It records the keyword arguments `with_structured_output` was called with, so a test can
    prove the method stays pinned, and it answers with text that would corrupt ids, citations
    and option keys if the merge ever stopped protecting them.
    """

    payloads: dict[type[BaseModel], Any] = field(default_factory=dict)
    kwargs: list[dict[str, Any]] = field(default_factory=list)
    calls: list[type[BaseModel]] = field(default_factory=list)

    def with_structured_output(self, schema: type[BaseModel], **kwargs: Any) -> Runnable:
        self.kwargs.append(kwargs)

        def answer(_messages: list[BaseMessage]) -> Any:
            self.calls.append(schema)
            payload = self.payloads[schema]
            return payload(len(self.calls)) if callable(payload) else payload

        return RunnableLambda(answer)


def english_question(**overrides: Any) -> TranslatableQuestion:
    fields: dict[str, Any] = {
        "question": "Since when does Article 4 apply?",
        "options": [
            Option(key=k, text=t)
            for k, t in (("A", "1 August 2024"), ("B", "2 February 2025"), ("C", "2 August 2026"))
        ],
        "rubric": None,
        "model_answer": "Since 2 February 2025.",
        "explanation": "Article 113 names the date.",
    }
    return TranslatableQuestion(**{**fields, **overrides})


def english_chapter(**overrides: Any) -> TranslatableChapter:
    fields: dict[str, Any] = {
        "title": "Why the AI Act concerns you",
        "intro": "This chapter shows you what the AI Act is.",
        "summary": "The AI Act protects fundamental rights.",
        "may": "You may: write customer mails with AI (Art. 50).",
    }
    return TranslatableChapter(**{**fields, **overrides})


def test_translate_question_pins_the_structured_output_method():
    model = StubModel(payloads={TranslatableQuestion: english_question()})
    translate_question(model, make_question(), "de", "en", date(2026, 9, 16))
    assert model.kwargs == [{"method": "function_calling"}]


def test_translate_question_keeps_every_field_the_model_never_saw():
    source = make_question()
    model = StubModel(payloads={TranslatableQuestion: english_question()})
    result = translate_question(model, source, "de", "en", date(2026, 9, 16))

    assert result.id == "q-01-03"
    assert result.chapter == "01-x"
    assert result.type == "multiple_choice"
    assert result.difficulty == 2
    assert result.correct == "B"
    assert result.citations == ["Art. 113"]
    assert [o.key for o in result.options] == ["A", "B", "C"]

    assert result.question == "Since when does Article 4 apply?"
    assert result.options[1].text == "2 February 2025"
    assert result.explanation == "Article 113 names the date."
    assert result.last_change.by == "ai"
    assert result.last_change.trigger == "translation from de"
    assert result.last_change.date == date(2026, 9, 16)


def test_translate_question_refuses_option_keys_the_model_renamed():
    renamed = english_question(options=[Option(key=k, text=k) for k in ("A", "B", "D")])
    model = StubModel(payloads={TranslatableQuestion: renamed})
    with pytest.raises(ValueError, match="option keys"):
        translate_question(model, make_question(), "de", "en", date(2026, 9, 16))
    assert len(model.calls) == 3


def test_translate_chapter_calls_once_for_the_frame_and_once_per_step():
    source = make_chapter()
    model = StubModel(
        payloads={
            TranslatableChapter: english_chapter(),
            TranslatableStep: lambda n: TranslatableStep(
                id=f"s{n - 1}", text=f"English step {n - 1}", example="An example."
            ),
        }
    )
    result = translate_chapter(model, source, "de", "en", date(2026, 9, 16))

    assert model.calls == [TranslatableChapter, TranslatableStep, TranslatableStep]
    assert model.kwargs == [{"method": "function_calling"}] * 2

    assert result.id == "01-x"
    assert result.duration_minutes == 8
    assert [s.question for s in result.steps] == ["q-01-01", None]
    assert [s.id for s in result.steps] == ["s1", "s2"]
    assert [s.citations for s in result.steps] == [["Art. 1", "Art. 113"], ["Art. 3(4)"]]
    assert result.title == "Why the AI Act concerns you"
    assert [s.text for s in result.steps] == ["English step 1", "English step 2"]
    assert result.last_change.by == "ai"


def test_translate_chapter_refuses_a_step_id_the_model_changed():
    model = StubModel(
        payloads={
            TranslatableChapter: english_chapter(),
            TranslatableStep: TranslatableStep(id="s9", text="English step"),
        }
    )
    with pytest.raises(ValueError, match="step id"):
        translate_chapter(model, make_chapter(), "de", "en", date(2026, 9, 16))


def test_translate_question_retries_an_answer_the_proxy_rejected():
    model = StubModel(payloads={TranslatableQuestion: english_question()})
    answer = model.with_structured_output(TranslatableQuestion, method="function_calling")
    model.kwargs.clear()
    calls = {"n": 0}

    def flaky(_schema: type[BaseModel], **kwargs: Any) -> Runnable:
        model.kwargs.append(kwargs)

        def run(messages: list[BaseMessage]) -> Any:
            calls["n"] += 1
            if calls["n"] == 1:
                raise tool_use_failed()
            return answer.invoke(messages)

        return RunnableLambda(run)

    model.with_structured_output = flaky  # type: ignore[method-assign]
    result = translate_question(model, make_question(), "de", "en", date(2026, 9, 16))
    assert calls["n"] == 2
    assert result.question == "Since when does Article 4 apply?"


def content_dir_with_german_only(tmp_path: Path) -> Path:
    """A content directory holding the manifest and one German chapter with one question."""
    content = tmp_path / "content"
    (content / "de" / "chapters").mkdir(parents=True)
    (content / "de" / "questions").mkdir(parents=True)
    (content / "manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "course_version": "0.1.0",
                "law": {"amended_by": ["32026R1744"]},
                "locales": ["de", "en"],
                "reference_locale": "de",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    chapter = make_chapter()
    question = make_question().model_copy(update={"chapter": chapter.id})
    for item, kind in ((chapter, "chapters"), (question, "questions")):
        (content / "de" / kind / f"{item.id}.yaml").write_text(
            yaml.safe_dump(item.model_dump(mode="json"), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    return content


def mark_by_hand(path: Path) -> None:
    """Edit a written item the way a human would, leaving it valid for the loader."""
    item = yaml.safe_load(path.read_text(encoding="utf-8"))
    item["explanation"] = "edited by hand"
    path.write_text(yaml.safe_dump(item, allow_unicode=True, sort_keys=False), encoding="utf-8")


def explanation_of(path: Path) -> str:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["explanation"]


def run_cli(monkeypatch: pytest.MonkeyPatch, content: Path, *args: str) -> StubModel:
    """Run the translate CLI against a stub model and return the stub."""
    model = StubModel(
        payloads={
            TranslatableQuestion: english_question(),
            TranslatableChapter: english_chapter(),
            TranslatableStep: lambda n: TranslatableStep(
                id=f"s{n - 1}", text=f"English step {n - 1}"
            ),
        }
    )
    monkeypatch.setattr(translate, "chat_model", lambda *_args, **_kwargs: model)
    monkeypatch.setattr(translate, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(
        sys,
        "argv",
        ["translate", "--from", "de", "--to", "en", "--content-dir", str(content), *args],
    )
    translate.main()
    return model


def test_the_cli_writes_every_missing_item(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    content = content_dir_with_german_only(tmp_path)
    run_cli(monkeypatch, content)

    chapter = content / "en" / "chapters" / "01-x.yaml"
    question = content / "en" / "questions" / "q-01-03.yaml"
    assert chapter.exists() and question.exists()

    written = yaml.safe_load(question.read_text(encoding="utf-8"))
    assert written["id"] == "q-01-03"
    assert written["correct"] == "B"
    assert written["citations"] == ["Art. 113"]
    assert written["question"] == "Since when does Article 4 apply?"
    assert written["last_change"]["by"] == "ai"


def test_the_cli_leaves_an_item_that_already_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    content = content_dir_with_german_only(tmp_path)
    run_cli(monkeypatch, content)
    question = content / "en" / "questions" / "q-01-03.yaml"
    mark_by_hand(question)

    second = run_cli(monkeypatch, content)
    assert second.calls == []
    assert explanation_of(question) == "edited by hand"


def test_the_cli_overwrites_when_asked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    content = content_dir_with_german_only(tmp_path)
    run_cli(monkeypatch, content)
    question = content / "en" / "questions" / "q-01-03.yaml"
    mark_by_hand(question)

    second = run_cli(monkeypatch, content, "--overwrite")
    assert second.calls != []
    assert explanation_of(question) == "Article 113 names the date."


def test_the_cli_translates_only_the_named_item(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    content = content_dir_with_german_only(tmp_path)
    run_cli(monkeypatch, content, "--only", "q-01-03")

    assert (content / "en" / "questions" / "q-01-03.yaml").exists()
    assert not (content / "en" / "chapters").exists()
