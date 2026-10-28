"""The copy-paste test against a live proxy (D108): no tutor reply, plain or in any persona's
voice, earns a must point the student has not earned.

Set EVAL_LLM_BASE_URL to the proxy (for the compose stack: http://localhost:4000/v1) and run:

    EVAL_LLM_BASE_URL=http://localhost:4000/v1 uv run pytest tests/evals/ -m eval
"""

import os
from pathlib import Path

import pytest

from tests.evals.copy_paste_eval import render, run_copy_paste
from tests.evals.grading_eval import prepare_env

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not os.environ.get("EVAL_LLM_BASE_URL"),
        reason="EVAL_LLM_BASE_URL must point at a live model proxy",
    ),
]

REPO_ROOT = Path(__file__).resolve().parents[3]
PERSONAS = ["jester", "pirate", "sergeant", "marvin", "clerk"]
# The grader credits a hint that names a point's subject on one sample and not the next,
# and the safe line carries the question, whose own text it sometimes credits. The owner
# ruled that not every edge has to hold; one in ten pasted replies is the ceiling, and the
# leaks are printed so a rise is read, not guessed (D108). Measured 8 of 126 on 2026-09-28
# with the gate in the pipeline; 21 of 126 under the governed turn (D114) the same day,
# every one shipped by the critic: two plain drafts the grader credits (a how-question
# that carries the point, a point stated as a fact) and the rest the grader's flips on
# voiced replies. The bar stands; the critic has to earn it.
LEAK_CEILING = 0.1


def test_at_most_one_in_ten_replies_gives_a_missing_point_away(tmp_path: Path):
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
    results = run_copy_paste(deps, PERSONAS)
    assert results
    leaked = sum(1 for r in results if r.leaked)
    assert leaked / len(results) <= LEAK_CEILING, render(results)
