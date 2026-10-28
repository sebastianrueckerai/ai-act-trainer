from typing import Literal

from langchain_core.messages import AnyMessage
from pydantic import BaseModel, Field

from app.content.models import Question, Step
from app.graph.deps import GraphDeps
from app.graph.grade import practice_step_text
from app.graph.prompts import CITE_RULE, GENDER_RULE, NODE_ID_RULE, PLAIN_TEXT_RULE
from app.graph.state import GradedAnswer, Phase, SessionState

Kind = Literal[
    "right",
    "partial",
    "wrong",
    "on_track",
    "settled",
    "not_an_attempt",
    "test_retry",
    "free_question",
    "curated",
]

PRACTICE_TRIES = 5
RECENT_MESSAGES = 10

PRACTICE_RULE = (
    "Coach the student towards the answer. The help is one or two statements before the "
    "Ask now line; after a green try the confirmation is enough, or the ask alone. The "
    "Ask now line is the reply's only question. The help grows with the replies on the "
    "open point: the try number, plus the ordinal the Verdict section adds after an "
    "orange. On the first and "
    "second reply it narrows the case and carries none of the missing point's content: "
    "point at who is involved, what happens next, what the colleague would do, what could "
    "go wrong. From the third reply on it "
    "may point at the chapter step or the article and name the concept, the answer itself "
    "still withheld. Never state a missing point as a fact before the question settles, and "
    "never tell the student what to add. A help sentence or a question of your own that "
    "carries the missing point ('Wie sorgst du dafür, dass du das Ergebnis prüfst?') hands "
    "it over: the student only has to say yes. 'Wie stellst du sicher, dass ...' or 'Wie "
    "könntest du dafür sorgen, dass ...' followed by the point is the same hand-over. On a "
    "retry after a leak, drop the sentence that leaked and help with one that uses none of "
    "the missing point's words. Answer what the student said first, a pushback, a question "
    "about the law, not knowing, then help and end on the Ask now line. The help never "
    "repeats your last message's help."
)
TEST_COUNT_RULE = (
    "This is the test. The reply names how many of the required points the answer has, as a "
    "count, before the guidance. A picked question has no count."
)
FREE_RULE = (
    "The student asked a question with no question of the course open. Answer from the "
    "bundled acts, the conclusion first, at most three short paragraphs."
)
COPIED_RULE = (
    "The verdict says the answer repeats the tutor's last message. Say so in one kind "
    "sentence: those were the tutor's words, and the student's own are still owed. Then go "
    "on as the outcome says."
)
CURATED_RULE = (
    "This turn's message is curated course text: a chapter step, a confirmation or a "
    "result. It is written already; only the voice runs."
)

OUTCOMES: dict[str, str] = {
    "right": "The answer is right. Confirm it and say why in one or two sentences. Do not "
    "ask the question again and end on no question.",
    "partial": "This try met a required point and the question stays open. Open by "
    "confirming that part in one short sentence that adds nothing to it: no reason, no "
    "condition, no 'weil'. The confirmation says the student is right and states the met "
    "part as a fact of the case: 'Richtig, verboten ist das nicht.' Never echo a rejection "
    "back ('Das ist nicht richtig.', 'Stimmt nicht.'): right after the answer, the student "
    "reads it as a verdict on that answer. Then end on the Ask now line of the Question "
    "section, word for word, as the only question.",
    "wrong": "This try met no new required point. Say so kindly, help one step, and end "
    "on the Ask now line of the Question section, word for word, as the only question.",
    "on_track": "This try met no new required point, but it is on the right track: nothing "
    "in it is wrong, it is not there yet. Say so in one sentence, help one step towards "
    "the point, and end on the Ask now line of the Question section, word for word, as "
    "the only question.",
    "settled": "The question is settled. Give the answer and the why, kindly, with no "
    "verdict on the try and no question.",
    "not_an_attempt": "The message is not an attempt at the question. Answer what the "
    "student said or asked, with no verdict, then end on the Ask now line of the Question "
    "section, word for word, as the only question.",
    "test_retry": "A miss in the test, which cannot be failed: tries are unlimited and "
    "the answer is guided until it is right. Say how many required points the answer "
    "has, as a count, then help one step towards the missing point, and end on the Ask "
    "now line of the Question section, word for word.",
}

# The outcomes that keep the question open: the reply ends on the ask of the turn.
OPEN_KINDS = ("partial", "wrong", "on_track", "not_an_attempt", "test_retry")

STYLE = (
    "Two short paragraphs at most, du-form, plain German, no Markdown. Their company is "
    "dein Unternehmen, never wir. Name an article only as a pointer, never as the answer. "
    "Write a 'Fundstellen:' line only when the student asked about the law; it stands last "
    "and the app shows it under the bubble, so the question is still the last thing the "
    f"student reads. {CITE_RULE} {NODE_ID_RULE} {PLAIN_TEXT_RULE} {GENDER_RULE}"
)


class Brief(BaseModel):
    """The situation of one turn, on a few pages, read by the writer, the critics and the
    voice alike."""

    tutor: str
    step: str = ""
    question: str = ""
    verdict: str = ""
    tries: str = ""
    # The tutor's question for this turn: the ask of the first must point not met (D118).
    ask: str = ""
    kind: str = ""
    conversation: str
    message: str
    job: str
    style: str = STYLE
    # The points still missing by their rubric number: the Question section numbers every
    # point once, the Verdict section reuses those numbers, and the critic names a point
    # it sees earned by that number.
    missing: dict[int, str] = Field(default_factory=dict)
    # A brief rebuilt from its rendered text (the turn stores the text, not the model).
    rendered: str = ""

    @classmethod
    def from_text(cls, text: str) -> "Brief":
        return cls(tutor="", conversation="", message="", job="", style="", rendered=text)

    def text(self) -> str:
        if self.rendered:
            return self.rendered
        sections = [
            (
                "COURSE (the tutor's voice, the phase and the locale)",
                self.tutor,
            ),
            (
                "CHAPTER STEP (verbatim course text, the lesson the open question follows)",
                self.step,
            ),
            (
                "QUESTION (the open course question with its points and answer)",
                self.question + (f"\nAsk now: {self.ask}" if self.ask else ""),
            ),
            (
                "VERDICT (the grader's machine output on the student's last message)",
                self.verdict,
            ),
            (
                "EARLIER TRIES (the student's answers on this question so far)",
                self.tries,
            ),
            (
                "CONVERSATION (the chat so far, verbatim, oldest first)",
                self.conversation,
            ),
            (
                "MESSAGE (the student's last message, verbatim, the one this reply answers)",
                self.message,
            ),
            ("JOB (what the tutor's reply this turn must do)", self.job),
            ("STYLE (how the reply is written)", self.style),
        ]
        body = "\n\n".join(f"--- {name}\n{sec}" for name, sec in sections if sec)
        return (
            "===== SITUATION FOR THE TUTOR'S NEXT MESSAGE =====\n\n"
            f"{body}\n\n===== END OF SITUATION ====="
        )


def shown_text(message: AnyMessage) -> str:
    """What the student saw of their own message: a chip's label, else the text."""
    if message.type == "human":
        shown = message.additional_kwargs.get("shown")
        if shown:
            return str(shown)
    return str(message.content)


def speaker_lines(messages: list[AnyMessage]) -> list[str]:
    """The conversation as the prompts show it: one Student or Tutor line per message."""
    return [
        f"{'Student' if message.type == 'human' else 'Tutor'}: {shown_text(message)}"
        for message in messages
    ]


def shown_step(deps: GraphDeps, state: SessionState) -> Step | None:
    """The step on screen. step_idx already points past it, at the step still to come."""
    chapters = deps.chapters(state.get("locale", "de"))
    chapter_idx = state.get("chapter_idx", 0)
    if chapter_idx >= len(chapters):
        return None
    steps = chapters[chapter_idx].steps
    step_idx = state.get("step_idx", 0)
    return steps[step_idx - 1] if 0 < step_idx <= len(steps) else None


def course_position(deps: GraphDeps, state: SessionState) -> str:
    chapters = deps.chapters(state.get("locale", "de"))
    chapter_idx = state.get("chapter_idx", 0)
    if chapter_idx >= len(chapters):
        return "Course position: the student has finished all course chapters."
    title = chapters[chapter_idx].title
    step = shown_step(deps, state)
    if step is None:
        return f'Course position: chapter "{title}", before its first step.'
    return f'Course position: chapter "{title}", current step: {step.text}'


def _question_section(question: Question) -> str:
    lines = [question.question]
    if question.options:
        lines.append("Options:\n" + "\n".join(f"{o.key}: {o.text}" for o in question.options))
    if question.rubric:
        numbered = list(enumerate([*question.rubric.must_texts, *question.rubric.should], 1))
        must = numbered[: len(question.rubric.must)]
        should = numbered[len(question.rubric.must) :]
        if must:
            lines.append("Required points:\n" + "\n".join(f"{i}. {p}" for i, p in must))
        if should:
            lines.append("Optional points:\n" + "\n".join(f"{i}. {p}" for i, p in should))
    lines.append(f"Model answer: {question.model_answer}")
    lines.append(f"Why: {question.explanation}")
    lines.append(f"Citations: {', '.join(question.citations)}")
    return "\n".join(lines)


def point_numbers(question: Question | None) -> dict[str, int]:
    """Each rubric point's number: must points first, optional points after them."""
    if question is None or not question.rubric:
        return {}
    return {p: i for i, p in enumerate([*question.rubric.must_texts, *question.rubric.should], 1)}


def _numbered(points: list[str], numbers: dict[str, int]) -> str:
    return "\n".join(f"{numbers[p]}. {p}" if p in numbers else f"- {p}" for p in points)


_ORDINALS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth")


def _ordinal(n: int) -> str:
    if 0 < n <= len(_ORDINALS):
        return _ORDINALS[n - 1]
    suffix = "th" if n % 100 in (11, 12, 13) else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _verdict_section(
    graded: GradedAnswer,
    numbers: dict[str, int],
    tries: int,
    limit: int | None,
    nudges: int = 0,
    settled: bool = False,
) -> str:
    head = (
        "An attempt" if graded.attempt else "Not an attempt"
    ) + f", every required point met: {'yes' if graded.correct else 'no'}."
    if settled:
        # Unmet points on a settled question read as still owed and bait a leak fault
        # over the very why the reply is ordered to state.
        head += " The question settles with this try."
    return (
        head
        + "\nMet:\n"
        + (_numbered(graded.matched, numbers) or "- nothing yet")
        + "\nMissing:\n"
        + (
            "- nothing owed: the reply may state the unmet points"
            if settled
            else (_numbered(graded.missing, numbers) or "- nothing")
        )
        + ("\nRepeats the tutor's last message." if graded.copied else "")
        + (f"\nTry {tries} of {limit}" if limit else f"\nTry {tries}")
        + (f", {_ordinal(tries + nudges)} reply on this point." if nudges else ".")
    )


def _job(kind: Kind, phase: Phase) -> str:
    if kind == "free_question":
        return FREE_RULE
    if kind == "curated":
        return CURATED_RULE
    rule = PRACTICE_RULE + (f"\n{TEST_COUNT_RULE}" if phase is Phase.test else "")
    return f"Outcome: {kind}. {OUTCOMES[kind]}\n{rule}"


def build_brief(
    deps: GraphDeps,
    state: SessionState,
    kind: Kind,
    question: Question | None = None,
    graded: GradedAnswer | None = None,
    tries: int = 1,
    nudges: int = 0,
) -> Brief:
    locale = state.get("locale", "de")
    phase = Phase(state.get("phase", Phase.lesson))
    messages = list(state.get("messages", []))
    practice = phase is not Phase.test
    if question is None:
        step = course_position(deps, state)
    else:
        step = practice_step_text(deps, locale, question.id) if practice else ""
    attempt = state.get("practice") if practice else state.get("test")
    prior = (
        [g.answer for g in attempt.answers if g.question_id == question.id]
        if attempt is not None and question is not None
        else []
    )
    numbers = point_numbers(question)
    ask = ""
    if kind in OPEN_KINDS and question is not None and graded is not None:
        ask = (
            question.rubric.next_ask(graded.matched) if question.rubric else question.question
        ) or ""
    settled = kind in ("right", "settled")
    return Brief(
        tutor=(
            "The tutor of a German course on the EU AI Act, in a plain voice, du-form.\n"
            f"Phase: {phase.value}. Locale: {locale}."
        ),
        step=step,
        question=_question_section(question) if question is not None else "",
        verdict=(
            _verdict_section(
                graded,
                numbers,
                tries,
                PRACTICE_TRIES if practice else None,
                nudges,
                settled=settled,
            )
            if graded is not None
            else ""
        ),
        tries="\n".join(f"- {a}" for a in prior),
        ask=ask,
        missing=(
            {}
            if settled
            else (
                {numbers[p]: p for p in graded.missing if p in numbers}
                if graded is not None
                else {}
            )
        ),
        conversation="\n".join(speaker_lines(messages[-RECENT_MESSAGES - 1 : -1])) or "none",
        message=shown_text(messages[-1]) if messages else "",
        kind=kind,
        job=_job(kind, phase)
        + (f"\n{COPIED_RULE}" if graded is not None and graded.copied else ""),
    )
