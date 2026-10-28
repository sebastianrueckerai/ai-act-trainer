"""The critic calibration set: labelled drafts the critic must ship or send back."""

from pathlib import Path

import yaml
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from app.graph.brief import build_brief
from app.graph.critic import critique_reply
from app.graph.deps import GraphDeps
from app.graph.state import GradedAnswer, Phase, TestState, initial_state

CASES_DIR = Path(__file__).resolve().parent / "critic"


class Case(BaseModel):
    question: str
    name: str
    history: list[list[str]] = Field(default_factory=list)
    message: str
    outcome: str
    tries: int = 1
    met: list[int] = Field(default_factory=list)
    draft: str
    expect: str
    faults: list[str] = Field(default_factory=list)


class CaseResult(BaseModel):
    case: Case
    verdict: str
    faults: list[str]
    notes: str

    @property
    def hit(self) -> bool:
        if self.verdict != self.case.expect:
            return False
        return self.verdict == "ship" or any(f in self.faults for f in self.case.faults)


def load_cases(directory: Path = CASES_DIR) -> list[Case]:
    cases = []
    for path in sorted(directory.glob("q-*.yaml")):
        for raw in yaml.safe_load(path.read_text(encoding="utf-8")):
            cases.append(Case(question=path.stem, **raw))
    return cases


def _state(case: Case) -> dict:
    state = initial_state("clerk")
    state["phase"] = Phase.lesson
    state["messages"] = [
        AIMessage(text) if role == "tutor" else HumanMessage(text) for role, text in case.history
    ] + [HumanMessage(case.message)]
    state["practice"] = TestState(
        question_ids=[case.question], practice=True, current_tries=case.tries
    )
    return state


def run_calibration(deps: GraphDeps, cases: list[Case]) -> list[CaseResult]:
    results = []
    for case in cases:
        question = deps.question(case.question)
        must = question.rubric.must_texts
        matched = [must[i - 1] for i in case.met]
        missing = [p for p in must if p not in matched]
        graded = GradedAnswer(
            question_id=case.question,
            answer=case.message,
            correct=not missing,
            attempt=case.outcome != "not_an_attempt",
            matched=matched,
            missing=missing,
        )
        brief = build_brief(deps, _state(case), case.outcome, question, graded, case.tries)
        critique = critique_reply(deps, brief, case.draft.strip())
        results.append(
            CaseResult(
                case=case,
                verdict=critique.verdict,
                faults=list(critique.faults),
                notes=critique.notes,
            )
        )
    return results


def render(results: list[CaseResult]) -> str:
    lines = []
    by_fault: dict[str, list[bool]] = {}
    for result in results:
        mark = "hit " if result.hit else "MISS"
        lines.append(
            f"{mark} {result.case.question} {result.case.name}: {result.verdict} {result.faults}"
        )
        if not result.hit:
            lines.append(
                f"     expected {result.case.expect} {result.case.faults}; notes: {result.notes}"
            )
        for fault in result.case.faults or ["ship"]:
            by_fault.setdefault(fault, []).append(result.hit)
    for fault, hits in sorted(by_fault.items()):
        lines.append(f"{fault}: {sum(hits)} of {len(hits)} hits")
    lines.append(f"summary: {sum(r.hit for r in results)} of {len(results)} hits")
    return "\n".join(lines)
