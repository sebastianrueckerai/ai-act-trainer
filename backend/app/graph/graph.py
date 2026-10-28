from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.answer import free_question_node
from app.graph.deps import GraphDeps
from app.graph.dialog import compact_node, help_node, react_node
from app.graph.persona import persona_node
from app.graph.routing import route_after_grade, route_after_triage
from app.graph.state import Mood, SessionState, TurnScratch
from app.graph.teach import lesson_step_node
from app.graph.test_flow import (
    finish_test_node,
    grade_node,
    quit_test_node,
    skip_node,
    start_test_node,
)
from app.graph.translate import translate_node
from app.graph.triage import triage_node


def _begin_node(state: SessionState) -> dict:
    # The pose belongs to this turn. A grade or a reaction sets it again further down.
    return {"turn": TurnScratch(), "mood": Mood.neutral}


def build_graph(
    deps: GraphDeps, checkpointer: BaseCheckpointSaver | None = None
) -> CompiledStateGraph:
    graph = StateGraph(SessionState)
    graph.add_node("begin", _begin_node)
    graph.add_node("compact", compact_node(deps))
    graph.add_node("triage", triage_node(deps))
    graph.add_node("react", react_node(deps))
    graph.add_node("help", help_node(deps))
    graph.add_node("free_question", free_question_node(deps))
    graph.add_node("lesson_step", lesson_step_node(deps))
    graph.add_node("start_test", start_test_node(deps))
    graph.add_node("grade", grade_node(deps))
    graph.add_node("skip", skip_node(deps))
    graph.add_node("quit_test", quit_test_node(deps))
    graph.add_node("finish_test", finish_test_node(deps))
    graph.add_node("persona", persona_node(deps))
    graph.add_node("translate", translate_node(deps))
    graph.add_edge(START, "begin")
    graph.add_edge("begin", "compact")
    graph.add_edge("compact", "triage")
    graph.add_conditional_edges("triage", route_after_triage)
    graph.add_conditional_edges("grade", route_after_grade)
    graph.add_conditional_edges("skip", route_after_grade)
    for node in (
        "react",
        "help",
        "free_question",
        "lesson_step",
        "start_test",
        "quit_test",
        "finish_test",
    ):
        graph.add_edge(node, "persona")
    graph.add_edge("persona", "translate")
    graph.add_edge("translate", END)
    return graph.compile(checkpointer=checkpointer)
