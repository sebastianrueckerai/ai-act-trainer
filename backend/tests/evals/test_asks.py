"""Every ask pasted back against a live proxy (D118): no ask earns its own point.

Set EVAL_LLM_BASE_URL to the proxy (for the compose stack: http://localhost:4000/v1) and run:

    EVAL_LLM_BASE_URL=http://localhost:4000/v1 uv run pytest tests/evals/test_asks.py -m eval
"""

import os
from pathlib import Path

import pytest

from tests.evals.asks_eval import render, run_asks
from tests.evals.grading_eval import prepare_env

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not os.environ.get("EVAL_LLM_BASE_URL"),
        reason="EVAL_LLM_BASE_URL must point at a live model proxy",
    ),
]

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_no_ask_earns_its_own_point():
    prepare_env(os.environ["EVAL_LLM_BASE_URL"], REPO_ROOT)

    from app.content.loader import load_content
    from app.corpus.build import load_library
    from app.corpus.search import SearchIndex
    from app.graph.deps import GraphDeps
    from app.llm.models import chat_model
    from app.settings import Settings

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
    results = run_asks(deps)
    print(render(results))
    assert [r for r in results if r.leaked] == []
