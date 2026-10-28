"""The live fairness floor, run only against a real proxy (D32).

Set EVAL_LLM_BASE_URL to the proxy (for the compose stack:
http://localhost:4000/v1) and run:

    EVAL_LLM_BASE_URL=http://localhost:4000/v1 uv run pytest tests/evals/ -m eval

The strong role is gated; the fast role is measured and printed in failures.
"""

import os
from pathlib import Path

import pytest

from tests.evals.grading_eval import (
    ROLES,
    STRONG_ACCURACY_FLOOR,
    STRONG_FNR_CEILING,
    load_cases,
    prepare_env,
    run_role,
    summarize,
)

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not os.environ.get("EVAL_LLM_BASE_URL"),
        reason="EVAL_LLM_BASE_URL must point at a live model proxy",
    ),
]

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_the_strong_role_meets_the_floor(tmp_path: Path):
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
    content = load_content(REPO_ROOT / "content", REPO_ROOT / "personas")
    search = SearchIndex.build(library)
    cases = load_cases()

    reports = []
    for role in ROLES:
        model = chat_model(settings, role)
        deps = GraphDeps(
            library=library,
            content=content,
            search=search,
            models={"strong": model, "fast": model},
            settings=settings,
            law_version="eval",
        )
        results = run_role(deps, cases)
        model_name = settings.llm_model_strong if role == "strong" else settings.llm_model_fast
        reports.append(summarize(role, model_name, results))

    strong = next(report for report in reports if report.role == "strong")
    assert strong.accuracy >= STRONG_ACCURACY_FLOOR, strong.results
    assert strong.fnr is not None and strong.fnr <= STRONG_FNR_CEILING, strong.results
