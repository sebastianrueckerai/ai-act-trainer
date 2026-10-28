from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.api.chat_events import PartOut
from app.auth.identity import Principal
from app.graph.state import InputHint
from app.llm.budget import BudgetState


class StatusResponse(BaseModel):
    status: str


class ReadyChecks(BaseModel):
    startup: bool
    database: bool
    database_error: str | None = None
    content: bool


class ReadyStatus(BaseModel):
    status: str
    checks: ReadyChecks


class ActInfo(BaseModel):
    id: str
    short_name: str
    version: str
    articles: int


class LawVersion(BaseModel):
    celex: str
    consolidated: date
    amended_by: list[str] = []


class VersionInfo(BaseModel):
    app: str
    course: str
    law: LawVersion
    locales: list[str]
    reference_locale: str
    acts: list[ActInfo]


class MeResponse(BaseModel):
    principal: Principal
    data_level: int
    stored: list[str]


class AuthOptions(BaseModel):
    backend: Literal["dev", "invite"]
    guest: bool


class DevUser(BaseModel):
    subject: str
    name: str


class ThemeResponse(BaseModel):
    primary: str
    secondary: str
    accent: str
    background: str
    look: str


class ChatMessageOut(BaseModel):
    # The stored message's id: the page matches a flipped thread by it, since the
    # server compacts old turns away while the page keeps them.
    id: str | None = None
    role: Literal["user", "assistant"]
    text: str
    parts: list[PartOut] = Field(default_factory=list)
    # The hint the turn ended on, in the display locale; null on a student message.
    hint: InputHint | None = None
    # The text still shows the stored German while its translation is on its way.
    translating: bool = False


class StagePersona(BaseModel):
    id: str
    name: str
    image_url: str | None
    # The portrait the reaction decays back to after its moment.
    neutral_image_url: str | None = None
    scene_url: str | None = None
    scene_light_url: str | None = None


class StageChapter(BaseModel):
    id: str
    title: str
    stub: bool
    state: Literal["locked", "current", "done"]
    steps: int
    # The steps whose case is settled, on the current chapter only.
    step: int | None


class StageAttempt(BaseModel):
    kind: Literal["test", "practice"]
    index: int
    results: list[bool]
    total: int


class StageBlock(BaseModel):
    persona: StagePersona | None
    mood: str
    streak: int
    chapters: list[StageChapter]
    attempt: StageAttempt | None


class SessionRequest(BaseModel):
    persona_id: str = Field(min_length=1, max_length=64)
    display_locale: Literal["de", "en"] = "de"


class DisplayLocaleRequest(BaseModel):
    display_locale: Literal["de", "en"]


class SessionResponse(BaseModel):
    id: int
    persona_id: str
    phase: str
    display_locale: str
    hint: InputHint
    messages: list[ChatMessageOut]
    stage: StageBlock
    budget: BudgetState


class TurnRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    # What the student saw on the option they pressed. The graph reads `text`, the key;
    # the thread replays this, so a reloaded answer is a sentence and not a bare letter.
    shown: str | None = Field(default=None, max_length=4000)
