"""Load the grading eval cases and measure the grader against their labels.

One computation module, two entry points: tools/grading_eval.py renders the
report and tests/evals/test_grading_fairness.py asserts the floor, both
calling the functions here. Labels are hand-derived from each question's
rubric, never from a grader's output (D32).
"""

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from app.graph.deps import GraphDeps
from app.graph.grade import grade_answer

EVALS_DIR = Path(__file__).parent / "grading"
ROLES = ("strong", "fast")
STRONG_ACCURACY_FLOOR = 0.9
STRONG_FNR_CEILING = 0.1


class EvalCase(BaseModel):
    id: str
    answer: str
    fair: Literal["correct", "wrong"]
    note: str = ""


class QuestionCases(BaseModel):
    question: str
    cases: list[EvalCase] = Field(min_length=1)


class CaseResult(BaseModel):
    question: str
    case: EvalCase
    graded_correct: bool


class RoleReport(BaseModel):
    role: str
    model_name: str
    results: list[CaseResult]

    @property
    def accuracy(self) -> float:
        hit = sum(1 for r in self.results if r.graded_correct == (r.case.fair == "correct"))
        return hit / len(self.results)

    @property
    def fnr(self) -> float | None:
        fair = [r for r in self.results if r.case.fair == "correct"]
        if not fair:
            return None
        wrong = sum(1 for r in fair if not r.graded_correct)
        return wrong / len(fair)

    @property
    def fpr(self) -> float | None:
        unfair = [r for r in self.results if r.case.fair == "wrong"]
        if not unfair:
            return None
        passed = sum(1 for r in unfair if r.graded_correct)
        return passed / len(unfair)

    def per_question(self) -> dict[str, tuple[int, int]]:
        """Question id to (cases, graded matching the label)."""
        out: dict[str, tuple[int, int]] = {}
        for r in self.results:
            total, hit = out.get(r.question, (0, 0))
            out[r.question] = (total + 1, hit + (r.graded_correct == (r.case.fair == "correct")))
        return out


def load_cases(evals_dir: Path = EVALS_DIR) -> dict[str, QuestionCases]:
    cases: dict[str, QuestionCases] = {}
    for path in sorted(evals_dir.glob("*.yaml")):
        question_cases = QuestionCases.model_validate(
            yaml.safe_load(path.read_text(encoding="utf-8"))
        )
        cases[question_cases.question] = question_cases
    return cases


def run_role(deps: GraphDeps, cases: dict[str, QuestionCases]) -> list[CaseResult]:
    results = []
    for question_id, question_cases in sorted(cases.items()):
        question = deps.question(question_id)
        for case in question_cases.cases:
            # The product's transcript for a first try ends on the tutor posing the
            # question (D116): the eval grades the same shape, not a bare answer.
            graded = grade_answer(
                deps, question, case.answer, "de", recent=[f"Tutor: {question.question}"]
            )
            results.append(
                CaseResult(question=question_id, case=case, graded_correct=graded.correct)
            )
    return results


def summarize(role: str, model_name: str, results: list[CaseResult]) -> RoleReport:
    return RoleReport(role=role, model_name=model_name, results=results)


def render_report(reports: list[RoleReport]) -> str:
    lines = [
        "# Grading fairness report",
        "",
        f"Cases: {sum(len(r.results) for r in reports) // len(reports)} per role, "
        "hand-labeled from the rubrics.",
        "",
        "| Role | Model alias | Accuracy | False-negative rate | False-positive rate |",
        "|---|---|---|---|---|",
    ]
    for report in reports:
        lines.append(
            f"| {report.role} | {report.model_name} | {report.accuracy:.2f} "
            f"| {_fmt(report.fnr)} | {_fmt(report.fpr)} |"
        )
    lines += [
        "",
        f"Floor: the strong role must reach accuracy {STRONG_ACCURACY_FLOOR} and a "
        f"false-negative rate of at most {STRONG_FNR_CEILING}. The fast role is measured, "
        "not gated.",
        "",
    ]
    for report in reports:
        failed = [r for r in report.results if r.graded_correct != (r.case.fair == "correct")]
        lines.append(f"## {report.role}: {len(failed)} failed cases")
        for r in failed:
            lines += [
                "",
                f"- **{r.question} / {r.case.id}** (label {r.case.fair}): {r.case.note}",
            ]
        lines += [
            "",
            f"Per question for {report.role}, cases graded matching the label:",
            "",
            "| Question | Cases | Matching the label |",
            "|---|---|---|",
        ]
        for question, (cases, matching) in sorted(report.per_question().items()):
            lines.append(f"| {question} | {cases} | {matching} |")
        lines.append("")
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def prepare_env(base_url: str, repo_root: Path) -> None:
    """Load the repo .env, point the client at base_url, drop the dead export."""
    for line in (repo_root / ".env").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.split(" #")[0].strip().strip('"'))
    os.environ["LLM_BASE_URL"] = base_url
    os.environ.pop("GROQ_API_KEY", None)
