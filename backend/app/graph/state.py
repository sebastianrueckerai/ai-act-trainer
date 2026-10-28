import time
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from app.content.models import Question


class Phase(StrEnum):
    lesson = "lesson"
    free = "free"
    test = "test"
    done = "done"


class Guard(StrEnum):
    ok = "ok"
    cheat = "cheat"
    insult = "insult"
    profanity = "profanity"
    humor = "humor"
    offtopic = "offtopic"


class Intent(StrEnum):
    continue_ = "continue"
    question = "question"
    start_test = "start_test"
    answer = "answer"
    skip = "skip"
    quit_test = "quit_test"
    help = "help"
    choose = "choose"


class Mood(StrEnum):
    neutral = "neutral"
    happy = "happy"
    disappointed = "disappointed"
    surprised = "surprised"


class GradedAnswer(BaseModel):
    question_id: str
    answer: str
    correct: bool
    # False when the message asks, pleads or chats instead of answering: no try counted.
    attempt: bool = True
    matched: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    # The answer repeats the tutor's last message: graded all the same, and said so.
    copied: bool = False
    # Meets no new required point but heads towards the one asked: orange, no try (D119).
    on_track: bool = False
    # A pick that says more than the pick ("Ja, weil ..."): the rest is graded against the
    # why points, so a reason given up front counts (D130).
    more: bool = False
    tries: int = 1
    hint_shown: bool = False
    # The grader's own words, for debugging a disputed verdict. Never shown to the
    # student: feedback is the one-sentence verdict reason, verdict_raw the model's
    # whole structured response, reasoning included where the provider sends it.
    feedback: str = ""
    verdict_raw: str = ""


class TestState(BaseModel):
    question_ids: list[str]
    index: int = 0
    current_tries: int = 1
    answers: list[GradedAnswer] = Field(default_factory=list)
    # Rubric points the first try of the current question already met; the retry's
    # verdict is the union, so a follow-up that only answers the asked gap is not
    # failed for the points it was never asked to restate.
    prior_matched: list[str] = Field(default_factory=list)
    # Orange replies on the open point since the last green; the hint ladder counts them.
    nudges: int = 0
    started_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    practice: bool = False


class Choice(BaseModel):
    key: str
    label: str


class InputHint(BaseModel):
    kind: Literal["text", "yes_no", "choices", "confirm"]
    choices: list[Choice] = Field(default_factory=list)
    label: str | None = None
    asks: bool = False
    # A practice hint may name its own answer, so the picked chip flashes on the
    # click. A test hint never does: the tutor does not give a test answer away,
    # not even into the page source.
    correct_key: str | None = None


def hint_for_question(
    question: Question, reveal: bool = False, position_met: bool = False
) -> InputHint:
    """The position of a closed question is picked; once the pick met it, the why
    points are typed."""
    if question.type == "yes_no" and not position_met:
        return InputHint(kind="yes_no", asks=True)
    if question.type == "multiple_choice" and not position_met:
        return InputHint(
            kind="choices",
            choices=[Choice(key=option.key, label=option.text) for option in question.options],
            asks=True,
            correct_key=question.correct if reveal else None,
        )
    return InputHint(kind="text", asks=True)


class CitationPart(BaseModel):
    ref: str
    title: str
    quote: str
    url: str


class ModelAnswerCard(BaseModel):
    question: str
    model_answer: str
    explanation: str
    citations: list[CitationPart]
    correct: bool
    tries: int = 1


class FilePart(BaseModel):
    url: str
    title: str
    filename: str


class ChapterDonePart(BaseModel):
    chapter_id: str
    index: int
    total: int
    title: str


class ChapterStartPart(BaseModel):
    title: str
    intro: str


Part = ModelAnswerCard | CitationPart | FilePart | ChapterDonePart | ChapterStartPart


class UiEvent(BaseModel):
    name: str
    payload: dict[str, Any] = Field(default_factory=dict)


class TurnScratch(BaseModel):
    guard: Guard = Guard.ok
    intent: Intent = Intent.continue_
    advice: bool = False
    guard_note: str = ""
    draft: str = ""
    closing_line: str = ""
    hedge_added: bool = False
    context_question: str | None = None
    guard_category: Guard | None = None
    parts: list[Part] = Field(default_factory=list)
    ui_events: list[UiEvent] = Field(default_factory=list)
    input_hint: InputHint = Field(default_factory=lambda: InputHint(kind="text"))
    # The situation the writer read, rendered once, so the critics and the voice read the
    # same text. Empty until a node builds it; the persona node builds one for a curated turn.
    brief: str = ""
    # The turn's budget runs from here (govern.deadline).
    started_at: float = Field(default_factory=time.monotonic)
    # The draft is already the persona's own words (a curated reaction): the voice layer
    # leaves it alone instead of rewriting the character into the character.
    voiced: bool = False


class SessionState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    summary: str
    locale: str
    display_locale: str
    persona_id: str
    # The persona's canned greeting, drawn once at the seed: the first line the
    # student sees, instantly, while the opening turn generates.
    opening_line: str
    # Its English rendering, made by the opening route of an English session.
    opening_line_en: str
    phase: Phase
    chapter_idx: int
    step_idx: int
    chapters_done: list[str]
    test: TestState | None
    practice: TestState | None
    # The case a step asks once the student says the concept landed (D96).
    pending_case: str | None
    pending_quit: bool
    pending_start_test: bool
    attempts: int
    streak: int
    streak_before_test: int
    mood: Mood
    user_id: int | None
    session_seed: str
    pending_prompt: str
    last_hint: InputHint
    turn: TurnScratch


def initial_state(
    persona_id: str,
    user_id: int | None = None,
    locale: str = "de",
    display_locale: str = "de",
    session_seed: str = "seed",
) -> SessionState:
    return SessionState(
        messages=[],
        summary="",
        locale=locale,
        display_locale=display_locale,
        persona_id=persona_id,
        phase=Phase.lesson,
        chapter_idx=0,
        step_idx=0,
        chapters_done=[],
        test=None,
        practice=None,
        pending_case=None,
        pending_quit=False,
        pending_start_test=False,
        attempts=0,
        streak=0,
        streak_before_test=0,
        mood=Mood.neutral,
        user_id=user_id,
        session_seed=session_seed,
        pending_prompt="",
        last_hint=InputHint(kind="text"),
        turn=TurnScratch(),
    )
