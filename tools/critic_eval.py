"""Run the critic calibration set against the live proxy (D114).

Every labelled draft under backend/tests/evals/critic/ goes through the critic with its
brief. Prints one line per case, the misses with the critic's notes, the hits per fault and
the summary, and exits 1 on any miss.

Requires the compose dev profile with LiteLLM on :4000. Run from the repo root:

    env -u GROQ_API_KEY uv run --project backend python tools/critic_eval.py \\
        [--base-url http://localhost:4000/v1] [--question q-01-05]
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from tests.evals.critic_eval import load_cases, render, run_calibration  # noqa: E402
from tests.evals.grading_eval import prepare_env  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:4000/v1")
    parser.add_argument("--question", action="append", help="only this question id")
    args = parser.parse_args()

    prepare_env(args.base_url, REPO_ROOT)

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
    cases = load_cases()
    if args.question:
        cases = [case for case in cases if case.question in args.question]
    results = run_calibration(deps, cases)
    print(render(results))
    return 1 if any(not result.hit for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
