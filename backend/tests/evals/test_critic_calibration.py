"""The critic calibration set against a live proxy (D114): labelled drafts the critic must
ship or send back with the named fault.

Set EVAL_LLM_BASE_URL to the proxy (for the compose stack: http://localhost:4000/v1) and run:

    EVAL_LLM_BASE_URL=http://localhost:4000/v1 uv run pytest tests/evals/ -m eval
"""

import os
from pathlib import Path

import pytest

from tests.evals.critic_eval import load_cases, render, run_calibration
from tests.evals.grading_eval import prepare_env

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not os.environ.get("EVAL_LLM_BASE_URL"),
        reason="EVAL_LLM_BASE_URL must point at a live model proxy",
    ),
]

REPO_ROOT = Path(__file__).resolve().parents[3]
# The floor keeps the tuned run's share (17 of 22 on 2026-09-28) with the same two-case
# slack for prompt variance; the set shrank to 16 cases when the converted questions moved
# to the pick flow and the boss-trick question died (D125, D129).
CALIBRATION_FLOOR = 11


def test_the_critic_hits_the_calibration_floor(tmp_path: Path):
    prepare_env(os.environ["EVAL_LLM_BASE_URL"], REPO_ROOT)

    from app.content.loader import load_content
    from app.corpus.build import load_library
    from app.corpus.search import SearchIndex
    from app.graph.deps import GraphDeps
    from app.llm.models import chat_model
    from app.settings import Settings

    settings = Settings(
        _env_file=None,
        env="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        content_dir=REPO_ROOT / "content",
        personas_dir=REPO_ROOT / "personas",
        corpus_dir=REPO_ROOT / "corpus",
        frontend_dist=tmp_path / "no-dist",
    )
    library = load_library(REPO_ROOT / "corpus")
    deps = GraphDeps(
        library=library,
        content=load_content(REPO_ROOT / "content", REPO_ROOT / "personas"),
        search=SearchIndex.build(library),
        models={"strong": chat_model(settings, "strong"), "fast": chat_model(settings, "fast")},
        settings=settings,
        law_version="eval",
    )
    results = run_calibration(deps, load_cases())
    report = render(results)
    print(report)
    assert sum(r.hit for r in results) >= CALIBRATION_FLOOR, report
