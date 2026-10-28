from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from app.content.citations import de_ref
from app.graph.state import (
    ChapterDonePart,
    ChapterStartPart,
    CitationPart,
    FilePart,
    InputHint,
    ModelAnswerCard,
    Part,
)
from app.llm.budget import BudgetState


class CitationsOut(BaseModel):
    kind: Literal["citations"] = "citations"
    ref: str
    title: str
    quote: str
    url: str


class CardOut(BaseModel):
    kind: Literal["card"] = "card"
    question: str
    model_answer: str
    explanation: str
    citations: list[CitationsOut]
    correct: bool
    tries: int = 1


class FileOut(BaseModel):
    kind: Literal["file"] = "file"
    url: str
    title: str
    filename: str


class ChapterDoneOut(BaseModel):
    kind: Literal["chapter_done"] = "chapter_done"
    chapter_id: str
    index: int
    total: int
    title: str


class ChapterStartOut(BaseModel):
    kind: Literal["chapter_start"] = "chapter_start"
    title: str
    intro: str


PartOut = Annotated[
    CardOut | CitationsOut | FileOut | ChapterDoneOut | ChapterStartOut,
    Field(discriminator="kind"),
]


def part_out(part: Part, *, localize: bool = True) -> PartOut:
    """localize=False for a part whose citation labels are already in their final display
    form (the translate node's English output); de_ref would otherwise convert an English
    "Art. 4(1)" back into German, since it reads the same as the untranslated canonical form.
    """
    if isinstance(part, ModelAnswerCard):
        return CardOut(
            question=part.question,
            model_answer=part.model_answer,
            explanation=part.explanation,
            citations=[_citations_out(c, localize) for c in part.citations],
            correct=part.correct,
            tries=part.tries,
        )
    if isinstance(part, FilePart):
        return FileOut(url=part.url, title=part.title, filename=part.filename)
    if isinstance(part, ChapterDonePart):
        return ChapterDoneOut(**part.model_dump())
    if isinstance(part, ChapterStartPart):
        return ChapterStartOut(**part.model_dump())
    return _citations_out(part, localize)


def _citations_out(part: CitationPart, localize: bool) -> CitationsOut:
    ref = de_ref(part.ref) if localize else part.ref
    return CitationsOut(ref=ref, title=part.title, quote=part.quote, url=part.url)


class StatusEvent(BaseModel):
    event: Literal["status"] = "status"
    node: str


class WorkingEvent(BaseModel):
    """The step that runs now, in the character's words, for the line beside the dots."""

    event: Literal["working"] = "working"
    step: str
    text: str


class TokenEvent(BaseModel):
    event: Literal["token"] = "token"
    text: str


class UiPayloadEvent(BaseModel):
    event: Literal["ui"] = "ui"
    name: str
    payload: dict[str, Any] = Field(default_factory=dict)


class PartEvent(BaseModel):
    event: Literal["part"] = "part"
    part: PartOut


class InputHintEvent(BaseModel):
    event: Literal["input_hint"] = "input_hint"
    hint: InputHint


class MessageEvent(BaseModel):
    event: Literal["message"] = "message"
    id: str | None = None
    text: str
    parts: list[PartOut] = Field(default_factory=list)
    hint: InputHint
    # The turn ran in German under a flag that flipped meanwhile: its rendering follows.
    translating: bool = False


class ErrorEvent(BaseModel):
    event: Literal["error"] = "error"
    code: str
    message: str
    budget: BudgetState | None = None


ChatEvent = (
    StatusEvent
    | WorkingEvent
    | TokenEvent
    | UiPayloadEvent
    | PartEvent
    | InputHintEvent
    | MessageEvent
    | ErrorEvent
)


def format_sse(event: ChatEvent) -> str:
    return f"event: {event.event}\ndata: {event.model_dump_json()}\n\n"
