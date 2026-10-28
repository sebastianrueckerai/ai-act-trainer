import json
import re
import time

import structlog
from langchain_core.messages import AIMessage, SystemMessage
from pydantic import BaseModel, Field

from app.content.models import Question
from app.graph.deps import GraphDeps
from app.graph.guards import parse_choice, parse_yes_no
from app.graph.prompts import GRADE, PROSE, mark
from app.graph.state import GradedAnswer
from app.llm.retry import with_retry

log = structlog.get_logger(__name__)

PRACTICE_RULE = (
    "This is a practice question inside the chapter, a learning prompt, not a test. Read the "
    "answer in the context of the case: a short answer that takes a position on the case "
    "counts for every rubric point that position states (a student who replies to the "
    "colleague's 'that is now forbidden' with 'wrong, we may' has stated that the use is "
    "allowed, and a bare 'Falsch!' with no elaboration at all states exactly the same "
    "position, as does any short reply that rejects the claim: 'Blödsinn!', 'Unsinn.', "
    "'Quatsch', 'Stimmt nicht', 'Nein!'). Who and why are separate points: "
    "an answer that names the right who meets that point even when it gives no "
    'reason at all, and only the reason is then unmet. One word can be a whole answer: "Ich" '
    'to "Wer steht dafür gerade?" is right. Everyday wording carries a point: "man muss das '
    'immer doppelchecken" states that the result gets checked. Give the benefit of the doubt '
    "on wording; only what the answer contradicts or omits entirely is unmet."
)

_LEADING_VERB = re.compile(r"^\w+(?:\s+\w+)*?,?\s+(?=(dass|warum|wer|wie|ob|was)\b)")


class Verdict(BaseModel):
    """A free-text answer graded against the question's rubric, points by number."""

    correct: bool
    attempt: bool = True
    matched: list[int] = Field(default_factory=list)
    missing: list[int] = Field(default_factory=list)
    feedback: str = ""
    # The answer repeats the tutor's last message, word for word or nearly.
    copied: bool = False
    # The answer meets no new required point but heads towards the one asked (D119).
    on_track: bool = False


class ProseChoice(BaseModel):
    """A yes/no or option answer recovered from a free-form sentence."""

    answer: str
    # The reply gives more than the answer: a reason, a condition or a further claim.
    reason: bool = False


def call_structured[T](deps: GraphDeps, role: str, schema: type[T], prompt: str) -> tuple[T, str]:
    """The parsed schema answer and the model's whole structured response, reasoning
    included where the provider sends it: a disputed verdict has to be debuggable
    after the fact, from the checkpoint or the log."""
    model = deps.models[role]
    outcome = with_retry(
        lambda: model.with_structured_output(
            schema, method="function_calling", include_raw=True
        ).invoke([SystemMessage(prompt)])
    )
    if isinstance(outcome, dict) and "parsed" in outcome:
        return outcome["parsed"], raw_text(outcome.get("raw"))
    # A test double that never saw include_raw.
    return outcome, ""


def content_fields(deps: GraphDeps, **fields: object) -> dict[str, object]:
    """Student text and raw model completions reach the log only where transcripts are
    kept (DATA_LEVEL=2); every other deployment logs lengths and verdicts only."""
    return dict(fields) if deps.settings.data_level >= 2 else {}


def raw_text(raw: object) -> str:
    if not isinstance(raw, AIMessage):
        return ""
    parts = [str(raw.content)]
    if raw.tool_calls:
        parts.append(json.dumps(raw.tool_calls, ensure_ascii=False, default=str))
    if raw.additional_kwargs:
        parts.append(json.dumps(raw.additional_kwargs, ensure_ascii=False, default=str))
    return "\n".join(part for part in parts if part)[:4000]


def _not_an_attempt(question: Question, answer_text: str) -> GradedAnswer:
    return GradedAnswer(question_id=question.id, answer=answer_text, correct=False, attempt=False)


def _yes_no_prose_prompt(asked: str, answer_text: str) -> str:
    return mark(
        "You read one student reply to a yes/no question and recover the answer in it.\n"
        f"Question: {asked}\n"
        f"Student reply: {answer_text}\n"
        'answer is exactly "yes" or "no" when the reply commits to one, and "unclear" '
        "when it does not.\n"
        "reason is true when the reply also gives a reason, a condition or a further "
        "claim beyond the answer ('Ja, weil wir es prüfen', 'Nein, das muss erst der "
        "Chef sehen'), and false for a bare answer ('Glaub schon!', 'Auf keinen Fall').\n"
        "Return your decision by calling the function ProseChoice.",
        PROSE,
    )


def _choice_prose_prompt(question: Question, answer_text: str) -> str:
    options = "\n".join(f"{option.key}: {option.text}" for option in question.options)
    return mark(
        "You read one student reply to a multiple-choice question and recover the chosen "
        "option.\n"
        f"Question: {question.question}\n"
        f"Options:\n{options}\n"
        f"Student reply: {answer_text}\n"
        "answer is exactly the key of the option the reply chooses, also when the reply "
        'paraphrases its text, and "none" when it commits to no option.\n'
        "reason is true when the reply also gives a reason, a condition or a further "
        "claim beyond the answer ('Ja, weil wir es prüfen', 'Nein, das muss erst der "
        "Chef sehen'), and false for a bare answer ('Glaub schon!', 'Auf keinen Fall').\n"
        "Return your decision by calling the function ProseChoice.",
        PROSE,
    )


def _rubric_points(question: Question) -> list[str]:
    return question.rubric.must_texts + list(question.rubric.should)


def _grade_prompt(
    question: Question,
    answer_text: str,
    practice_context: str | None,
    recent: list[str],
) -> str:
    points = _rubric_points(question)
    must_count = len(question.rubric.must)
    numbered = "\n".join(f"{i}. {point}" for i, point in enumerate(points, 1))
    step = (
        f"The chapter step the question follows:\n{practice_context}\n" if practice_context else ""
    )
    lenient = f"{PRACTICE_RULE}\n" if practice_context is not None else ""
    transcript = (
        "The conversation so far, oldest first, exactly as the student saw it. The last "
        "Student line is the answer to grade: it replies to the Tutor line directly above "
        "it, whatever that line asks, so 'Ja' under 'Ist das zulässig?' states that it is "
        "allowed. Earlier Student lines answered earlier Tutor lines and are graded "
        "already. When the last Student line repeats the tutor's last message, word for "
        "word or nearly, copied is true; grade what it states all the same, a point "
        "stated there is met. A question the tutor asked, repeated back, states nothing "
        "and meets no point.\n" + "\n".join([*recent, f"Student: {answer_text}"]) + "\n"
    )
    return mark(
        "You grade the last Student line of the conversation against the question's "
        "rubric.\n"
        f"{step}"
        f"The case the conversation is about:\n{question.question}\n"
        f"{transcript}"
        f"Rubric points, numbered 1 to {len(points)}. Points 1 to {must_count} are "
        f"required, the rest optional:\n{numbered}\n"
        f"Model answer, a reference for the meaning, not the wording:\n"
        f"{question.model_answer}\n"
        "A point is met when the last Student line shows understanding of it, in whatever words, "
        "directly or by clear implication: reasoning or a safeguard that only makes "
        "sense because the point holds counts as meeting it, even when the point's own "
        "wording never appears. Own words, no article numbers and a colloquial tone "
        "still count. A citation alone, with no sentence saying in words what the cited "
        "rule requires, meets no point: the answer must state the rule, not just name where "
        "it lives. A point that bundles more than one idea is met when the answer's "
        "gist carries its core, even without spelling out every part of it. A point is "
        "missed when the answer says nothing about it and implies nothing about it, and "
        "contradicted when the answer asserts or implies the opposite.\n"
        f"{lenient}"
        "attempt is true when the message tries to answer the question, however short, "
        "hedged or wrong, and false when it asks something, asks for help, says it does not "
        "understand, or says nothing about the case. matched lists every point the last "
        "Student line states, whether or not it is an attempt.\n"
        "on_track is true when the answer is an attempt that meets no new required point, "
        "states nothing wrong about the case and moves towards the point asked: a right "
        "observation, a right first half, a correct statement too general to meet the "
        "point. It is false when the answer contradicts a point, names the wrong actor, "
        "or says nothing about the case.\n"
        "matched and missing each list the numbers of points, never their text. correct "
        f"is true only when every one of points 1 to {must_count} is in matched. copied is "
        "true only when the last Student line repeats the tutor's last message. feedback "
        "is one short German sentence to the student.\n"
        "Return your verdict by calling the function Verdict.",
        GRADE,
    )


def _resolve_yes_no(deps: GraphDeps, asked: str, text: str) -> tuple[bool | None, bool]:
    """A reply to a yes/no question, and whether it says more than the answer: the chip's
    key read by code, a typed reply read by the fast model."""
    parsed = parse_yes_no(text)
    if parsed is not None:
        return parsed, False
    resolved, raw = call_structured(deps, "fast", ProseChoice, _yes_no_prose_prompt(asked, text))
    log.info(
        "prose_resolution",
        kind="yes_no",
        asked=asked,
        reply_len=len(text),
        resolved=resolved.answer,
        reason=resolved.reason,
        **content_fields(deps, reply=text, verdict_raw=raw),
    )
    return {"yes": True, "no": False}.get(resolved.answer), resolved.reason


def read_yes_no(deps: GraphDeps, asked: str, text: str) -> bool | None:
    """A reply to a yes/no question. None when it commits to neither."""
    return _resolve_yes_no(deps, asked, text)[0]


def _resolve_choice(deps: GraphDeps, question: Question, text: str) -> tuple[str | None, bool]:
    """A reply to a multiple-choice question, and whether it says more than the choice: the
    chip's key or a bare letter read by code, a typed reply read by the fast model."""
    key = parse_choice(text, question)
    if key is not None:
        return key, False
    resolved, raw = call_structured(deps, "fast", ProseChoice, _choice_prose_prompt(question, text))
    log.info(
        "prose_resolution",
        kind="choice",
        question=question.id,
        reply_len=len(text),
        resolved=resolved.answer,
        reason=resolved.reason,
        **content_fields(deps, reply=text, verdict_raw=raw),
    )
    chosen = resolved.answer if resolved.answer in {o.key for o in question.options} else None
    return chosen, resolved.reason


def read_choice(deps: GraphDeps, question: Question, text: str) -> str | None:
    """A reply to a multiple-choice question. None when it commits to no option."""
    return _resolve_choice(deps, question, text)[0]


def _grade_yes_no(deps: GraphDeps, question: Question, answer_text: str) -> GradedAnswer:
    parsed, reason = _resolve_yes_no(deps, question.question, answer_text)
    if parsed is None:
        return _not_an_attempt(question, answer_text)
    return GradedAnswer(
        question_id=question.id,
        answer=answer_text,
        correct=parsed == (question.correct == "yes"),
        more=reason,
    )


def _grade_choice(deps: GraphDeps, question: Question, answer_text: str) -> GradedAnswer:
    key, reason = _resolve_choice(deps, question, answer_text)
    if key is None:
        return _not_an_attempt(question, answer_text)
    return GradedAnswer(
        question_id=question.id,
        answer=answer_text,
        correct=key == question.correct,
        more=reason,
    )


def _sentences(text: str) -> list[str]:
    return [
        " ".join(part.lower().split()).rstrip("?.!").strip()
        for part in re.findall(r"[^.!?]+[.!?]*", text)
        if part.strip()
    ]


def _repeats_the_course_text(question: Question, answer_text: str) -> bool:
    """Every sentence of the answer is a sentence of the question or of one of its asks: it
    names what is wanted and states none of it (D116, D118)."""
    curated = {question.question, *(p.ask for p in question.rubric.must if p.ask)}
    known = {sentence for text in curated for sentence in _sentences(text)}
    said = _sentences(answer_text)
    return bool(said) and all(sentence in known for sentence in said)


def _grade_free_text(
    deps: GraphDeps,
    question: Question,
    answer_text: str,
    practice_context: str | None,
    recent: list[str],
) -> GradedAnswer:
    started = time.perf_counter()
    verdict, raw = call_structured(
        deps, "strong", Verdict, _grade_prompt(question, answer_text, practice_context, recent)
    )
    points = _rubric_points(question)

    def _texts(indexes: list[int]) -> list[str]:
        return [points[i - 1] for i in indexes if 1 <= i <= len(points)]

    log.info(
        "grade_verdict",
        question=question.id,
        correct=verdict.correct,
        attempt=verdict.attempt,
        matched=verdict.matched,
        missing=verdict.missing,
        copied=verdict.copied,
        on_track=verdict.on_track,
        practice=practice_context is not None,
        seconds=round(time.perf_counter() - started, 2),
        answer_len=len(answer_text),
        **content_fields(deps, feedback=verdict.feedback, verdict_raw=raw),
    )
    return GradedAnswer(
        question_id=question.id,
        answer=answer_text,
        correct=verdict.correct,
        attempt=verdict.attempt,
        matched=_texts(verdict.matched),
        missing=_texts(verdict.missing),
        copied=verdict.copied,
        on_track=verdict.on_track and verdict.attempt,
        feedback=verdict.feedback,
        verdict_raw=raw,
    )


def grade_answer(
    deps: GraphDeps,
    question: Question,
    answer_text: str,
    locale: str,
    practice_context: str | None = None,
    recent: list[str] | None = None,
    typed: bool = False,
) -> GradedAnswer:
    """practice_context is the chapter step the question follows, and marks the answer as a
    practice try: the rubric is then read leniently, in the context of the case (D87).
    recent is the conversation before the answer, oldest first, as Student and Tutor lines.
    typed reads a closed question's answer as free text: the pick already met its
    position point, and the answer works on the why points."""
    if typed or question.type == "free_text":
        if _repeats_the_course_text(question, answer_text):
            return _not_an_attempt(question, answer_text)
        return _grade_free_text(deps, question, answer_text, practice_context, recent or [])
    if question.type == "yes_no":
        return _grade_yes_no(deps, question, answer_text)
    return _grade_choice(deps, question, answer_text)


def plain_point(text: str) -> str:
    """A rubric point without its grading verb, so it reads as a sentence to the student."""
    return _LEADING_VERB.sub("", text, count=1)


def practice_step_text(deps: GraphDeps, locale: str, question_id: str) -> str:
    """The chapter step whose question this is, text and example, or "" for a question no
    step asks."""
    for chapter in deps.chapters(locale):
        for step in chapter.steps:
            if step.question == question_id:
                return "\n\n".join([step.text] + ([step.example] if step.example else []))
    return ""
