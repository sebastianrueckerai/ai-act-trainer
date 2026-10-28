"""Grade the eval set through the real path against the live proxy.

Every case comes from backend/tests/evals/grading/, every label was written by
hand from the rubric. Both roles run: the model under test sits in the grading
slot, one role per pass. Prints one line per case; --write also renders the
fairness report.

Requires the compose dev profile with LiteLLM on :4000. Run from the repo root:

    env -u GROQ_API_KEY uv run --project backend python tools/grading_eval.py \
        [--base-url http://localhost:4000/v1] [--write runs/grading-report.md]
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from tests.evals.grading_eval import (  # noqa: E402
    ROLES,
    STRONG_ACCURACY_FLOOR,
    STRONG_FNR_CEILING,
    load_cases,
    prepare_env,
    render_report,
    run_role,
    summarize,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:4000/v1")
    parser.add_argument("--write", type=Path, default=None)
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
        for result in results:
            graded = "correct" if result.graded_correct else "wrong"
            print(
                f"{role:6} {result.question} {result.case.id:15} "
                f"label={result.case.fair:7} graded={graded}"
            )
        model_name = settings.llm_model_strong if role == "strong" else settings.llm_model_fast
        reports.append(summarize(role, model_name, results))

    strong = next(report for report in reports if report.role == "strong")
    print(
        f"strong: accuracy {strong.accuracy:.2f} (floor {STRONG_ACCURACY_FLOOR}), "
        f"fnr {strong.fnr:.2f} (ceiling {STRONG_FNR_CEILING})"
    )
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(render_report(reports), encoding="utf-8")
        print(f"report written to {args.write}")


if __name__ == "__main__":
    main()
