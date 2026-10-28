from collections.abc import Iterable
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.content.manifest import CourseManifest

QuestionType = Literal["yes_no", "multiple_choice", "free_text"]
REACTION_KEYS = {"cheat", "insult", "profanity", "humor", "offtopic"}
VERDICT_KEYS = {"right", "wrong"}
MILESTONE_COUNTS = {"chapter": 3, "course": 1}


class LastChange(BaseModel):
    date: date
    by: Literal["human", "ai"]
    trigger: str
    summary: str


class LawSummary(BaseModel):
    node: str
    summary: str
    source_sha: str
    children: list["LawSummary"] = []


class LawSummaryFile(LawSummary):
    last_change: LastChange


class Step(BaseModel):
    id: str
    text: str
    example: str | None = None
    citations: list[str] = []
    question: str | None = None


class Chapter(BaseModel):
    id: str
    title: str
    intro: str
    duration_minutes: int = Field(ge=1)
    steps: list[Step] = Field(min_length=1)
    stub: bool = False
    summary: str
    # What the chapter lets the student do, or what they now know, taken from the summary
    # with its citation: the last line of the chapter's closing turn.
    may: str
    last_change: LastChange


class Option(BaseModel):
    key: str = Field(pattern=r"^[A-F]$")
    text: str


class MustPoint(BaseModel):
    point: str = Field(min_length=1)
    # The question the tutor asks when this point is the next one missing (D118). The
    # first point of a closed question is the pick and carries none.
    ask: str | None = None

    @field_validator("ask")
    @classmethod
    def ends_in_a_question_mark(cls, value: str | None) -> str | None:
        if value is not None and not value.rstrip().endswith("?"):
            raise ValueError("an ask ends in a question mark")
        return value


class Rubric(BaseModel):
    must: list[MustPoint] = Field(min_length=1)
    should: list[str] = []

    @property
    def must_texts(self) -> list[str]:
        return [p.point for p in self.must]

    def next_ask(self, met: Iterable[str]) -> str | None:
        """The ask of the first must point not in met; None once every one is met."""
        done = set(met)
        return next((p.ask for p in self.must if p.point not in done), None)


class Question(BaseModel):
    id: str
    chapter: str
    type: QuestionType
    difficulty: int = Field(ge=1, le=3)
    question: str
    options: list[Option] = []
    correct: str | None = None
    rubric: Rubric | None = None
    model_answer: str
    explanation: str
    citations: list[str] = Field(min_length=1)
    last_change: LastChange

    # The chat finds the question a turn asks by its question mark (D131).
    @field_validator("question")
    @classmethod
    def ends_in_a_question_mark(cls, value: str) -> str:
        if not value.rstrip().endswith("?"):
            raise ValueError("a question ends in a question mark")
        return value

    @model_validator(mode="after")
    def check_shape(self) -> "Question":
        if self.type == "yes_no":
            if self.correct not in {"yes", "no"}:
                raise ValueError("yes_no questions need correct: yes or no")
            if self.options:
                raise ValueError("yes_no questions carry no options")
        elif self.type == "multiple_choice":
            keys = [option.key for option in self.options]
            if len(keys) < 2 or len(set(keys)) != len(keys):
                raise ValueError(
                    "multiple_choice questions need at least two options with unique keys"
                )
            if self.correct not in keys:
                raise ValueError("multiple_choice correct must name one of the option keys")
        else:
            if self.rubric is None:
                raise ValueError("free_text questions need a rubric")
            if self.correct is not None or self.options:
                raise ValueError("free_text questions carry no correct key and no options")
            return self
        if self.rubric is not None:
            points = self.rubric.must
            if points[0].ask is not None:
                raise ValueError(
                    "a closed question's first must point is the pick, it carries no ask"
                )
            if any(point.ask is None for point in points[1:]):
                raise ValueError("every must point after the pick needs an ask")
        return self


# The steps of a turn the page can name while they run, in the order they run.
WORKING_STEPS = ("reading", "grading", "writing", "rewriting", "checking", "voicing", "translating")


class PersonaManifest(BaseModel):
    id: str
    name: dict[str, str]
    tagline: dict[str, str]
    voice: str
    style_rules: list[str] = Field(min_length=1)
    reactions: dict[Literal["cheat", "insult", "profanity", "humor", "offtopic"], str]
    # The character's own line on a clear pick, right or wrong: a picked answer gets its
    # reaction from here with no rewrite, so it arrives at once (D130).
    verdicts: dict[Literal["right", "wrong"], list[str]] = {}
    # The character's own line on a finished chapter ("{n}" is its number) and on the
    # finished course, curated like the verdicts.
    milestones: dict[Literal["chapter", "course"], list[str]] = {}
    image_prompt: str = ""
    scene_prompt: str = ""
    # Where the character stands on the picker, and whether the portrait is part machine:
    # the course is about AI, so every tutor but the clerk looks the part.
    rank: int = 99
    machine: bool = True
    # A character with no flavour adds no opener, closer or interjection: his turn is the
    # draft in his voice, and therefore shorter.
    spice: bool = True
    emotions: list[str] = ["neutral", "happy", "disappointed", "surprised"]
    # Twelve set greetings per character: one is drawn at the seed and opens the
    # course instantly, while the real first turn generates behind it.
    openings: list[str] = Field(default_factory=list)
    prompts: dict[str, str] = {}
    image_words: list[str] = []
    banned_phrases: list[str] = []
    # What the character says beside the typing dots while a step runs, per step; a
    # step without lines falls back to the locale's plain line.
    working: dict[str, list[str]] = {}

    @field_validator("working")
    @classmethod
    def _working_steps_exist(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        unknown = sorted(set(value) - set(WORKING_STEPS))
        if unknown:
            raise ValueError(f"unknown working steps: {unknown}")
        empty = sorted(step for step, lines in value.items() if not lines)
        if empty:
            raise ValueError(f"working steps without a line: {empty}")
        return value

    @model_validator(mode="after")
    def check_reactions(self) -> "PersonaManifest":
        missing = REACTION_KEYS - set(self.reactions)
        if missing:
            raise ValueError(f"persona {self.id} lacks reactions for: {', '.join(sorted(missing))}")
        lacking = sorted(key for key in VERDICT_KEYS if not self.verdicts.get(key))
        if lacking:
            raise ValueError(f"persona {self.id} lacks verdict lines for: {', '.join(lacking)}")
        counts = {key: len(self.milestones.get(key, [])) for key in MILESTONE_COUNTS}
        if counts != MILESTONE_COUNTS:
            raise ValueError(
                f"persona {self.id} needs milestone lines {MILESTONE_COUNTS}: {counts}"
            )
        return self


class LocaleContent(BaseModel):
    locale: str
    chapters: dict[str, Chapter]
    questions: dict[str, Question]


class ContentBundle(BaseModel):
    manifest: CourseManifest
    locales: dict[str, LocaleContent]
    personas: dict[str, PersonaManifest]
    law: dict[str, LawSummary] = {}
