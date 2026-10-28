from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel

from app.content.loader import ContentBundle
from app.content.models import Chapter, LocaleContent, PersonaManifest, Question
from app.corpus.model import Library
from app.corpus.search import SearchIndex
from app.settings import Settings


class CompletionRecord(BaseModel):
    user_id: int
    course_version: str
    law_version: str
    locale: str
    persona_id: str
    passed_at: datetime


@dataclass
class GraphDeps:
    library: Library
    content: ContentBundle
    search: SearchIndex
    models: Mapping[Literal["strong", "fast"], BaseChatModel]
    settings: Settings
    law_version: str
    record_completion: Callable[[CompletionRecord], None] | None = None
    # English chapter titles, rendered once per process on first need (the stage under en).
    titles_en: dict[str, str] = field(default_factory=dict)

    def locale_content(self, locale: str) -> LocaleContent:
        return self.content.locales[locale]

    def chapters(self, locale: str) -> list[Chapter]:
        locale_content = self.locale_content(locale)
        return [locale_content.chapters[key] for key in sorted(locale_content.chapters)]

    def question(self, question_id: str) -> Question:
        for locale_content in self.content.locales.values():
            if question_id in locale_content.questions:
                return locale_content.questions[question_id]
        raise KeyError(question_id)

    def persona(self, persona_id: str | None) -> PersonaManifest | None:
        if persona_id is None:
            return None
        return self.content.personas.get(persona_id)
