from collections.abc import Iterator, Mapping
from contextvars import ContextVar
from typing import Literal

from langchain_openai import ChatOpenAI

from app.settings import Settings

Role = Literal["strong", "fast"]
ROLES: tuple[Role, ...] = ("strong", "fast")

# The proxy key of the caller the current request serves, set by the chat endpoints.
caller_key: ContextVar[str | None] = ContextVar("caller_key", default=None)


def chat_model(settings: Settings, role: Role, api_key: str | None = None) -> ChatOpenAI:
    model_name = settings.llm_model_strong if role == "strong" else settings.llm_model_fast
    return ChatOpenAI(
        model=model_name,
        base_url=settings.llm_base_url,
        api_key=api_key or settings.llm_api_key,
        timeout=settings.llm_timeout_seconds,
        max_retries=2,
        temperature=0,
        # Groq's default completion budget for these reasoning models is far too small: the
        # hidden reasoning alone has been observed using over 2000 tokens before a single
        # visible one, leaving the answer truncated. Room for both, reliably.
        max_tokens=8192,
    )


class CallerModels(Mapping[Role, ChatOpenAI]):
    """The chat model per role for the caller's key, one instance per role and key."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.built: dict[tuple[Role, str], ChatOpenAI] = {}

    def __getitem__(self, role: Role) -> ChatOpenAI:
        if role not in ROLES:
            raise KeyError(role)
        key = caller_key.get()
        if key is None:
            if self.settings.litellm_admin_key:
                # With budgets on, a call without its caller's key would spend uncapped.
                raise RuntimeError("no caller key is bound to this request")
            key = self.settings.llm_api_key
        if (role, key) not in self.built:
            self.built[(role, key)] = chat_model(self.settings, role, key)
        return self.built[(role, key)]

    def __iter__(self) -> Iterator[Role]:
        return iter(ROLES)

    def __len__(self) -> int:
        return len(ROLES)
