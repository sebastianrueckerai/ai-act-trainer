"""Replies to "Klar soweit?" triaged by the live fast model: a no asks what did not land.

EVAL_LLM_BASE_URL=http://localhost:4000/v1 uv run pytest tests/evals/test_checkin_triage.py -m eval
"""

import os
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from tests.evals.grading_eval import prepare_env

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not os.environ.get("EVAL_LLM_BASE_URL"),
        reason="EVAL_LLM_BASE_URL must point at a live model proxy",
    ),
]

REPO_ROOT = Path(__file__).resolve().parents[3]

REPLIES = {
    "nee": "help",
    "nein": "help",
    "nicht wirklich": "help",
    "hä?": "help",
    "nicht so ganz": "help",
    "ja": "continue",
    "passt": "continue",
    "klar": "continue",
    "Was heißt Betreiber genau?": "question",
}


def test_a_no_to_the_check_in_is_help():
    prepare_env(os.environ["EVAL_LLM_BASE_URL"], REPO_ROOT)

    from app.content.loader import load_content
    from app.graph.deps import GraphDeps
    from app.graph.state import InputHint, Phase, initial_state
    from app.graph.triage import triage_node
    from app.llm.models import chat_model
    from app.settings import Settings

    settings = Settings(_env_file=None, env="development")
    deps = GraphDeps(
        library=None,
        content=load_content(REPO_ROOT / "content", REPO_ROOT / "personas"),
        search=None,
        models={"fast": chat_model(settings, "fast")},
        settings=settings,
        law_version="eval",
    )
    chapter = deps.chapters("de")[0]
    step = next(i for i, s in enumerate(chapter.steps) if s.question is not None)
    wrong = {}
    for reply, expected in REPLIES.items():
        state = initial_state("clerk")
        state.update(
            phase=Phase.lesson,
            step_idx=step + 1,
            pending_case=chapter.steps[step].question,
            pending_prompt="Klar soweit?",
            last_hint=InputHint(kind="confirm", label="Ja, weiter"),
            messages=[
                AIMessage(f"{chapter.steps[step].text}\n\nKlar soweit?"),
                HumanMessage(reply),
            ],
        )
        got = triage_node(deps)(state)["turn"].intent.value
        if got != expected:
            wrong[reply] = got
    assert wrong == {}
