import httpx
import openai
import pytest
from langchain_core.exceptions import ModelInvalidRequestError
from langchain_core.messages import AIMessage
from pydantic import BaseModel, ValidationError

from app.llm.retry import with_retry


class Answer(BaseModel):
    """Two required fields, so a half-filled payload fails to parse."""

    question: str
    explanation: str


class FlakyCall:
    def __init__(self, failures: list[Exception], answer: str = "done"):
        self.failures = failures
        self.answer = answer
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return self.answer


class SequencedCall:
    """A call that hands back one queued AIMessage per invocation, in order."""

    def __init__(self, results: list[AIMessage]):
        self.results = results
        self.calls = 0

    def __call__(self) -> AIMessage:
        self.calls += 1
        return self.results.pop(0)


def cut_off(content: str = "") -> AIMessage:
    """What a reasoning model returns when its hidden reasoning ate the whole token
    budget: no error, just an answer the proxy stopped mid-thought or before it began."""
    return AIMessage(content=content, response_metadata={"finish_reason": "length"})


def finished(content: str) -> AIMessage:
    return AIMessage(content=content, response_metadata={"finish_reason": "stop"})


def tool_use_failed() -> ModelInvalidRequestError:
    return ModelInvalidRequestError(
        'GroqException - {"error":{"message":"Tool choice is required, but model did not '
        'call a tool","code":"tool_use_failed","failed_generation":""}}'
    )


def bad_tool_choice() -> ModelInvalidRequestError:
    """A request the proxy rejects before the model sees it.

    `test_llm_models.py` proves the class this arrives as.
    """
    return ModelInvalidRequestError(
        'GroqException - {"error":{"message":"tool_choice names a tool that is not in '
        'tools","type":"invalid_request_error","code":"invalid_value"}}'
    )


def _request() -> httpx.Request:
    return httpx.Request("POST", "http://litellm:4000/v1/chat/completions")


def dropped_connection() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=_request())


def upstream_status(code: int) -> openai.APIStatusError:
    """What the proxy raises when the provider answers with a status of its own."""
    request = _request()
    return openai.APIStatusError(
        f"Error code: {code}",
        response=httpx.Response(code, request=request, json={"error": "'id'"}),
        body=None,
    )


def parser_failure() -> ValidationError:
    """What the structured-output parser raises when the tool arguments do not fit the schema."""
    try:
        Answer.model_validate({"question": "Since when does Article 4 apply?"})
    except ValidationError as exc:
        return exc
    raise AssertionError("an incomplete payload must not validate")


def test_with_retry_retries_a_failed_tool_call():
    call = FlakyCall([tool_use_failed(), tool_use_failed()])
    assert with_retry(call, attempts=3) == "done"
    assert call.calls == 3


def test_with_retry_retries_an_answer_the_merge_rejected():
    call = FlakyCall([ValueError("translated option keys do not match the source option keys")])
    assert with_retry(call, attempts=3) == "done"
    assert call.calls == 2


def test_with_retry_gives_up_after_the_last_attempt():
    call = FlakyCall([tool_use_failed(), tool_use_failed(), tool_use_failed()])
    with pytest.raises(ModelInvalidRequestError, match="tool_use_failed"):
        with_retry(call, attempts=3)
    assert call.calls == 3


def test_with_retry_retries_a_payload_the_parser_rejected():
    call = FlakyCall([parser_failure()])
    assert with_retry(call, attempts=3) == "done"
    assert call.calls == 2


def test_a_parser_failure_is_a_value_error():
    assert isinstance(parser_failure(), ValueError)


def test_with_retry_does_not_retry_another_bad_request():
    call = FlakyCall([bad_tool_choice()])
    with pytest.raises(ModelInvalidRequestError, match="tool_choice"):
        with_retry(call, attempts=3)
    assert call.calls == 1


def test_with_retry_retries_a_dropped_connection_to_the_proxy():
    call = FlakyCall([dropped_connection()])
    assert with_retry(call, attempts=3) == "done"
    assert call.calls == 2


def test_with_retry_retries_an_upstream_server_error():
    call = FlakyCall([upstream_status(500)])
    assert with_retry(call, attempts=3) == "done"
    assert call.calls == 2


def test_with_retry_does_not_retry_an_upstream_client_error():
    call = FlakyCall([upstream_status(429)])
    with pytest.raises(openai.APIStatusError):
        with_retry(call, attempts=3)
    assert call.calls == 1


def test_with_retry_retries_an_answer_the_token_limit_cut_off_before_it_began():
    call = SequencedCall([cut_off(""), finished("Translated.")])
    result = with_retry(call, attempts=3)
    assert result.content == "Translated."
    assert call.calls == 2


def test_with_retry_retries_an_answer_the_token_limit_cut_off_mid_sentence():
    call = SequencedCall([cut_off("You may only sort"), finished("You may sort CVs.")])
    result = with_retry(call, attempts=3)
    assert result.content == "You may sort CVs."
    assert call.calls == 2


def test_with_retry_gives_up_and_returns_the_cut_off_answer_after_the_last_attempt():
    call = SequencedCall([cut_off(""), cut_off(""), cut_off("almost")])
    result = with_retry(call, attempts=3)
    assert result.content == "almost"
    assert call.calls == 3


def test_with_retry_does_not_retry_an_answer_that_finished_on_its_own():
    call = SequencedCall([finished("ok")])
    result = with_retry(call, attempts=3)
    assert result.content == "ok"
    assert call.calls == 1


def test_with_retry_retries_an_agent_result_the_token_limit_cut_off():
    """create_agent's agent.invoke (free_question_node, write_reply) returns
    a state dict, not a bare AIMessage: the truncation check must look inside it too."""
    call = SequencedCall(
        [
            {"messages": [cut_off("")]},
            {"messages": [finished("You may sort CVs.")]},
        ]
    )
    result = with_retry(call, attempts=3)
    assert result["messages"][-1].content == "You may sort CVs."
    assert call.calls == 2


def test_with_retry_gives_up_and_returns_the_cut_off_agent_result_after_the_last_attempt():
    call = SequencedCall(
        [
            {"messages": [cut_off("")]},
            {"messages": [cut_off("")]},
            {"messages": [cut_off("almost")]},
        ]
    )
    result = with_retry(call, attempts=3)
    assert result["messages"][-1].content == "almost"
    assert call.calls == 3
