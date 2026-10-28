import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

from app.graph.persona import OPENING_NOTE

_MARKER = re.compile(r"\[node:([a-z_]+)\]")
# A scripted persona rewrite that returns the message it was given unchanged: the text after
# the prompt's "The tutor's message:" line. Graph tests use it where the plain text is what
# they assert.
ECHO = "<echo>"


def _marker_of(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, SystemMessage):
            found = _MARKER.search(message.content)
            assert found is not None, "no [node:...] marker in the system prompt"
            return found.group(1)
    raise AssertionError("scripted call without a system message")


class ScriptedChatModel(BaseChatModel):
    """A chat model whose answers come from a script, keyed by node marker.

    A script entry is a single response or a list consumed in order. A Pydantic
    instance is returned by with_structured_output; a dict with "tool_calls"
    becomes an AIMessage carrying tool calls for agent loops; a string becomes
    plain content.
    """

    script: dict[str, Any]
    calls: list[str] = []
    prompts: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _pop(self, marker: str) -> Any:
        assert marker in self.script, f"no scripted response for [node:{marker}]"
        entry = self.script[marker]
        if isinstance(entry, list):
            assert entry, f"script for [node:{marker}] is exhausted"
            entry = entry.pop(0)
        # A scripted exception is the model failing on that call.
        if isinstance(entry, Exception):
            raise entry
        return entry

    def _message(self, response: Any) -> AIMessage:
        if isinstance(response, dict) and "tool_calls" in response:
            return AIMessage(
                content="",
                tool_calls=[
                    {"name": call["name"], "args": call.get("args", {}), "id": f"call_{i}"}
                    for i, call in enumerate(response["tool_calls"])
                ],
            )
        if isinstance(response, BaseModel):
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": type(response).__name__,
                        "args": response.model_dump(),
                        "id": "call_0",
                    }
                ],
            )
        return AIMessage(content=str(response))

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        marker = _marker_of(messages)
        system = next(m for m in reversed(messages) if isinstance(m, SystemMessage))
        self.calls.append(marker)
        self.prompts.append(str(system.content))
        response = self._pop(marker)
        if response == ECHO:
            message = str(system.content).rsplit("The tutor's message:\n", 1)[-1]
            response = message.removesuffix(OPENING_NOTE)
        return ChatResult(generations=[ChatGeneration(message=self._message(response))])

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        include_raw = kwargs.get("include_raw", False)

        def _invoke(messages: list[BaseMessage]) -> Any:
            marker = _marker_of(messages)
            system = next(m for m in reversed(messages) if isinstance(m, SystemMessage))
            self.calls.append(marker)
            self.prompts.append(str(system.content))
            response = self._pop(marker)
            if isinstance(response, BaseModel) and issubclass(schema, type(response)):
                # A script written against the base schema: validate it against the
                # narrower one the node asked for.
                response = schema.model_validate(response.model_dump())
            assert isinstance(response, schema), (
                f"scripted [node:{marker}] response is {type(response).__name__}, "
                f"expected {schema.__name__}"
            )
            if include_raw:
                return {"raw": self._message(response), "parsed": response}
            return response

        return RunnableLambda(_invoke)

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        return self
