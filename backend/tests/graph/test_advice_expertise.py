from langchain_core.messages import AIMessage, HumanMessage

from app.graph.answer import free_question_prompt
from app.graph.brief import build_brief
from app.graph.critic import Critique
from app.graph.prompts import EXPERTISE_RULES
from app.graph.state import Phase, SessionState, initial_state
from app.graph.triage import Triage
from app.i18n import t

HEDGE = t("de", "hedge")
ANSWER = "Das hängt von den Umständen Ihres Falles ab."
SHIP = Critique(verdict="ship", score=5)


def _last_text(result: dict) -> str:
    message = result["messages"][-1]
    assert isinstance(message, AIMessage)
    return str(message.content)


def _free(persona_id: str | None = None) -> SessionState:
    state = initial_state(persona_id)
    state["phase"] = Phase.free
    return state


def _say(graph, state: SessionState, message: str, thread: str) -> dict:
    return graph.invoke(
        dict(state) | {"messages": [HumanMessage(message)]},
        {"configurable": {"thread_id": thread}},
    )


def test_the_models_advice_flag_appends_the_hedge(make_deps, make_graph):
    deps = make_deps(
        script={
            "triage": Triage(guard="ok", intent="question", advice=True),
            "free_question": ANSWER,
            "critic": SHIP,
        }
    )
    graph = make_graph(deps=deps)
    result = _say(graph, _free(), "Wenn mir das mit der KI passiert: kann ich klagen?", "advice")
    assert result["turn"].advice is True
    assert result["turn"].hedge_added is True
    assert _last_text(result) == f"{ANSWER}\n\n{HEDGE}"
    assert deps.models["strong"].calls == ["triage", "free_question", "critic"]


def test_without_the_flag_no_hedge_is_added(make_deps, make_graph):
    deps = make_deps(
        script={
            "triage": Triage(guard="ok", intent="question", advice=False),
            "free_question": ANSWER,
            "critic": SHIP,
        }
    )
    graph = make_graph(deps=deps)
    result = _say(graph, _free(), "Kann ich dagegen klagen?", "no-advice")
    assert result["turn"].advice is False
    assert _last_text(result) == ANSWER


def test_the_hedge_survives_a_kept_persona_rewrite(make_deps, make_graph):
    answer = "Ob Sie etwas tun können, hängt von den Umständen Ihres Falles ab."
    rewrite = f"Gern, der Reihe nach. {answer}\n\n{HEDGE}"
    deps = make_deps(
        script={
            "triage": Triage(guard="ok", intent="question", advice=True),
            "free_question": answer,
            "critic": SHIP,
            "persona": rewrite,
            "voice_critic": SHIP,
        }
    )
    graph = make_graph(deps=deps)
    result = _say(graph, _free(persona_id="clerk"), "Kann ich meinen Arbeitgeber klagen?", "hedge")
    assert result["turn"].advice is True
    assert result["turn"].hedge_added is True
    # The clerk is told to add no opener of his own (D99); the hedge still closes the turn.
    assert _last_text(result) == rewrite
    assert HEDGE in _last_text(result)
    assert "adds nothing of his own" in deps.models["fast"].prompts[-2]
    assert deps.models["fast"].calls == [
        "triage",
        "free_question",
        "critic",
        "persona",
        "voice_critic",
    ]


def test_free_question_prompt_carries_the_expertise_block_verbatim(make_deps):
    deps = make_deps()
    state = _free()
    state["messages"] = [HumanMessage("Was gilt?")]
    prompt = free_question_prompt(deps, build_brief(deps, state, "free_question"))
    assert EXPERTISE_RULES in prompt


def test_the_outside_expertise_refusal_is_delivered_verbatim(make_deps, make_graph):
    refusal = t("de", "outside_expertise")
    deps = make_deps(
        script={
            "triage": Triage(guard="ok", intent="question"),
            "free_question": refusal,
            "critic": SHIP,
        }
    )
    graph = make_graph(deps=deps)
    result = _say(graph, _free(), "Was gilt in China?", "outside")
    assert _last_text(result) == refusal
    assert result["turn"].draft == refusal
    assert result["turn"].parts == []
    assert deps.models["strong"].calls == ["triage", "free_question", "critic"]
