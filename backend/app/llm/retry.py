from collections.abc import Callable

import openai
from langchain_core.exceptions import ModelInvalidRequestError
from langchain_core.messages import AIMessage

ATTEMPTS = 3


def _recoverable(exc: Exception) -> bool:
    if isinstance(exc, ModelInvalidRequestError):
        return "tool_use_failed" in str(exc)
    if isinstance(exc, openai.APIConnectionError):
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code >= 500
    return isinstance(exc, ValueError)


def _last_ai_message(result: object) -> AIMessage | None:
    """The answer a call actually produced: the message itself for a plain model.invoke,
    or the last AIMessage in the state an agent.invoke returns."""
    if isinstance(result, AIMessage):
        return result
    if isinstance(result, dict) and isinstance(result.get("messages"), list):
        return next((m for m in reversed(result["messages"]) if isinstance(m, AIMessage)), None)
    return None


def _truncated(result: object) -> bool:
    """True when a reasoning model spent its whole token budget thinking and the proxy
    cut it off before (or partway through) the visible answer: no exception, just an
    AIMessage the model never got to finish."""
    message = _last_ai_message(result)
    return message is not None and message.response_metadata.get("finish_reason") == "length"


def with_retry[T](call: Callable[[], T], attempts: int = ATTEMPTS) -> T:
    """Run one model call, retrying the ways a model answer comes back unusable.

    Open-weight models behind the proxy answer a forced tool call in plain text every few
    requests, which the proxy reports as a bad request naming tool_use_failed. They also
    drop a field now and then, which the merge rejects. The proxy itself drops a connection
    or answers 5xx under load. A reasoning model occasionally burns its whole token budget
    on hidden reasoning and answers with nothing at all, or a cut-off sentence. The same
    prompt works on the next try, so retry those and nothing else.
    """
    for attempt in range(1, attempts + 1):
        try:
            result = call()
        except Exception as exc:
            if attempt == attempts or not _recoverable(exc):
                raise
            print(f"unusable answer, retrying ({attempt} of {attempts - 1}): {type(exc).__name__}")
            continue
        if attempt < attempts and _truncated(result):
            print(f"answer cut short by the token limit, retrying ({attempt} of {attempts - 1})")
            continue
        return result
    raise AssertionError("unreachable")
