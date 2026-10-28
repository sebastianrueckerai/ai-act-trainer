import contextvars

import httpx
import openai
import pytest
from langchain_core.exceptions import (
    ContextOverflowError,
    ModelAPIError,
    ModelInvalidRequestError,
)
from langchain_openai import ChatOpenAI

from app.llm.models import CallerModels, caller_key, chat_model
from app.settings import Settings

BASE_URL = "http://proxy:4000/v1"
BAD_TOOL_CHOICE = {
    "error": {
        "message": "tool_choice names a tool that is not in tools",
        "type": "invalid_request_error",
        "code": "invalid_value",
    }
}
CONTEXT_OVERFLOW = {
    "error": {
        "message": "This model's maximum context length is 8192 tokens",
        "type": "invalid_request_error",
        "code": "context_length_exceeded",
    }
}


def make_settings() -> Settings:
    return Settings(
        _env_file=None,
        llm_base_url=BASE_URL,
        llm_api_key="sk-unit",
        llm_model_strong="strong-alias",
        llm_model_fast="fast-alias",
        llm_timeout_seconds=12.5,
    )


def answer_every_request(model: ChatOpenAI, status: int, body: dict) -> list[httpx.Request]:
    """Answer the model's requests from memory and return the list they land in."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    model.client = openai.OpenAI(
        base_url=BASE_URL,
        api_key="sk-unit",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ).chat.completions
    return seen


def test_chat_model_builds_the_strong_role():
    model = chat_model(make_settings(), "strong")
    assert model.model_name == "strong-alias"
    assert model.openai_api_base == BASE_URL
    assert model.openai_api_key.get_secret_value() == "sk-unit"
    assert model.request_timeout == 12.5
    assert model.temperature == 0
    assert model.max_retries == 2
    assert model.max_tokens == 8192


def test_chat_model_builds_the_fast_role_the_same_way():
    model = chat_model(make_settings(), "fast")
    assert model.model_name == "fast-alias"
    assert model.openai_api_base == BASE_URL
    assert model.openai_api_key.get_secret_value() == "sk-unit"
    assert model.request_timeout == 12.5
    assert model.temperature == 0
    assert model.max_retries == 2
    assert model.max_tokens == 8192


def test_chat_model_retries_a_proxy_error_twice():
    model = chat_model(make_settings(), "strong")
    seen = answer_every_request(model, 500, {"error": {"message": "proxy is restarting"}})
    with pytest.raises(ModelAPIError, match="restarting"):
        model.invoke("hallo")
    assert len(seen) == 3


def test_a_bad_tool_choice_reaches_the_code_as_an_invalid_request():
    model = chat_model(make_settings(), "strong")
    seen = answer_every_request(model, 400, BAD_TOOL_CHOICE)
    with pytest.raises(ModelInvalidRequestError, match="tool_choice"):
        model.invoke("hallo")
    assert len(seen) == 1
    assert seen[0].url.path == "/v1/chat/completions"


def test_an_exhausted_context_reaches_the_code_as_something_else():
    model = chat_model(make_settings(), "strong")
    seen = answer_every_request(model, 400, CONTEXT_OVERFLOW)
    with pytest.raises(ContextOverflowError) as raised:
        model.invoke("hallo")
    assert not isinstance(raised.value, ModelInvalidRequestError)
    assert len(seen) == 1


def test_chat_model_carries_the_key_it_is_given():
    model = chat_model(make_settings(), "fast", "sk-caller")
    assert model.openai_api_key.get_secret_value() == "sk-caller"


def _under_key(key, read):
    def bound():
        caller_key.set(key)
        return read()

    return contextvars.copy_context().run(bound)


def test_caller_models_build_one_model_per_role_and_key():
    models = CallerModels(make_settings())
    first = _under_key("sk-a", lambda: models["fast"])
    again = _under_key("sk-a", lambda: models["fast"])
    other = _under_key("sk-b", lambda: models["fast"])
    strong = _under_key("sk-a", lambda: models["strong"])

    assert first is again
    assert first.openai_api_key.get_secret_value() == "sk-a"
    assert other.openai_api_key.get_secret_value() == "sk-b"
    assert strong.model_name == "strong-alias"
    assert strong.openai_api_key.get_secret_value() == "sk-a"
    assert list(models) == ["strong", "fast"]
    assert len(models) == 2
    with pytest.raises(KeyError):
        models["embed"]


def test_caller_models_use_the_deployment_key_while_budgets_are_off():
    models = CallerModels(make_settings())
    assert models["strong"].openai_api_key.get_secret_value() == "sk-unit"


def test_caller_models_refuse_a_call_without_a_caller_key_while_budgets_are_on():
    settings = make_settings().model_copy(update={"litellm_admin_key": "sk-admin"})
    with pytest.raises(RuntimeError, match="no caller key"):
        CallerModels(settings)["fast"]
