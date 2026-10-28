"""Replay a stuck student through the whole graph, every free-text question, one persona.

Five scripted messages per question: the first must point in plain words, "keine Ahnung",
the first point again, "Sagte ich doch", "weiß nicht". Reports, per question, two replies in
a row that are the same text, a reply that earns a missing must point when pasted back,
the critic retries per turn and the turns that hit the budget. Exits 1 on a repeat.

Requires the compose dev profile with LiteLLM on :4000. Run from the repo root:

    env -u GROQ_API_KEY uv run --project backend python tools/stuck_student.py \\
        [--persona jester] [--question q-01-05]
"""

import argparse
import sys
from pathlib import Path

from structlog.testing import capture_logs

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from tests.evals.grading_eval import prepare_env  # noqa: E402

MESSAGES = ["{point}", "keine Ahnung", "{point}", "Sagte ich doch", "weiß nicht"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:4000/v1")
    parser.add_argument("--persona", default="jester")
    parser.add_argument("--question", action="append", help="only this question id")
    args = parser.parse_args()
    prepare_env(args.base_url, REPO_ROOT)

    from langchain_core.messages import AIMessage, HumanMessage
    from langgraph.checkpoint.memory import InMemorySaver

    from app.content.loader import load_content
    from app.corpus.build import load_library
    from app.corpus.search import SearchIndex
    from app.graph.deps import GraphDeps
    from app.graph.grade import plain_point, practice_step_text
    from app.graph.graph import build_graph
    from app.graph.state import Phase, TestState, initial_state
    from app.llm.models import chat_model
    from app.settings import Settings
    from tests.evals.paste_back import gives_away

    settings = Settings(_env_file=None, env="development")
    library = load_library(REPO_ROOT / "corpus")
    deps = GraphDeps(
        library=library,
        content=load_content(REPO_ROOT / "content", REPO_ROOT / "personas"),
        search=SearchIndex.build(library),
        models={"strong": chat_model(settings, "strong"), "fast": chat_model(settings, "fast")},
        settings=settings,
        law_version="eval",
    )
    repeats = 0
    leaks = 0
    budget_hits = 0
    for question_id, question in sorted(deps.locale_content("de").questions.items()):
        if question.type != "free_text":
            continue
        if args.question and question_id not in args.question:
            continue
        graph = build_graph(deps, InMemorySaver())
        config = {"configurable": {"thread_id": question_id}}
        state = initial_state(args.persona)
        state["phase"] = Phase.lesson
        state["practice"] = TestState(question_ids=[question_id], practice=True)
        point = plain_point(question.rubric.must[0].point)
        point = point[0].upper() + point[1:] + "."
        step = practice_step_text(deps, "de", question_id)
        missing = question.rubric.must_texts[1:]
        print(f"===== {question_id} =====")
        previous = None
        recent = [f"Tutor: {question.question}"]
        for turn, template in enumerate(MESSAGES):
            text = template.format(point=point)
            messages = [AIMessage(question.question), HumanMessage(text)] if turn == 0 else []
            payload = (
                dict(state) | {"messages": messages}
                if turn == 0
                else {"messages": [HumanMessage(text)]}
            )
            with capture_logs() as logs:
                result = graph.invoke(payload, config)
            reply = str(result["messages"][-1].content)
            retries = sum(
                1 for e in logs if e["event"] == "critic_verdict" and e["verdict"] == "retry"
            )
            budget = [e["stage"] for e in logs if e["event"] == "critic_budget"]
            recent.append(f"Student: {text}")
            credited = gives_away(deps, question, reply, missing, step, recent)
            recent.append(f"Tutor: {reply}")
            same = reply == previous
            repeats += same
            leaks += bool(credited)
            budget_hits += bool(budget)
            print(
                f"> {text}\n{reply}\n"
                f"[retries={retries} budget={budget} credited={credited} repeat={same}]\n"
            )
            previous = reply
            if result.get("practice") is None:
                break
    print(
        f"summary: {repeats} repeated replies, {leaks} leaking replies, {budget_hits} budget turns"
    )
    return 1 if repeats else 0


if __name__ == "__main__":
    raise SystemExit(main())
