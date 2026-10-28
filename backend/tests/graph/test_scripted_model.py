import pytest
from langchain_core.messages import AIMessage, SystemMessage
from pydantic import BaseModel

from tests.fakes.scripted import ScriptedChatModel


class Triage(BaseModel):
    """What the triage step decided."""

    guard: str
    intent: str


def test_a_structured_call_returns_the_scripted_object():
    model = ScriptedChatModel(script={"triage": Triage(guard="ok", intent="answer")})
    result = model.with_structured_output(Triage, method="function_calling").invoke(
        [SystemMessage("You are the triage. [node:triage]")]
    )
    assert result == Triage(guard="ok", intent="answer")


def test_a_plain_call_returns_the_scripted_text():
    model = ScriptedChatModel(script={"help": "You can say: weiter."})
    result = model.invoke([SystemMessage("Explain the options. [node:help]")])
    assert isinstance(result, AIMessage)
    assert result.content == "You can say: weiter."


def test_a_list_of_responses_is_consumed_in_order_for_agent_loops():
    model = ScriptedChatModel(
        script={
            "coach": [
                {"tool_calls": [{"name": "search_law", "args": {"query": "Auskunft"}}]},
                "Here is the law.",
            ]
        }
    )
    first = model.invoke([SystemMessage("Coach the student. [node:coach]")])
    assert first.tool_calls[0]["name"] == "search_law"
    second = model.invoke([SystemMessage("Coach the student. [node:coach]")])
    assert second.content == "Here is the law."


def test_a_marker_without_a_script_entry_fails_with_the_marker_named():
    model = ScriptedChatModel(script={})
    with pytest.raises(AssertionError, match="node:persona"):
        model.invoke([SystemMessage("Rewrite. [node:persona]")])


def test_bind_tools_returns_the_model_and_records_calls():
    model = ScriptedChatModel(script={"coach": "Draft."})
    bound = model.bind_tools([lambda q: q])
    assert bound is model
    bound.invoke([SystemMessage("Coach. [node:coach]")])
    assert model.calls == ["coach"]
