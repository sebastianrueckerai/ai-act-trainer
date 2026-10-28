"""Every ask pasted back as the answer and graded by the model, past the product's echo guard
(D118): an ask that earns its own point leaks."""

from pydantic import BaseModel

from app.graph.deps import GraphDeps
from app.graph.grade import _grade_free_text, practice_step_text


class AskResult(BaseModel):
    question_id: str
    point_index: int
    ask: str
    own: bool
    others: list[int]

    @property
    def leaked(self) -> bool:
        return self.own


def run_asks(deps: GraphDeps, question_ids: list[str] | None = None) -> list[AskResult]:
    results = []
    for question_id, question in sorted(deps.locale_content("de").questions.items()):
        if question_ids is not None and question_id not in question_ids:
            continue
        if question.rubric is None:
            continue
        step = practice_step_text(deps, "de", question_id)
        must = question.rubric.must_texts
        for index, point in enumerate(question.rubric.must, 1):
            if point.ask is None:
                # The pick point of a closed question is never pasted (D125).
                continue
            graded = _grade_free_text(
                deps,
                question,
                point.ask,
                practice_context=step,
                # The ask is the tutor's last line when a student could paste it (D116).
                recent=[f"Tutor: {question.question}", f"Tutor: {point.ask}"],
            )
            earned = [
                i for i, text in enumerate(must, 1) if graded.attempt and text in graded.matched
            ]
            results.append(
                AskResult(
                    question_id=question_id,
                    point_index=index,
                    ask=point.ask,
                    own=index in earned,
                    others=[i for i in earned if i != index],
                )
            )
    return results


def render(results: list[AskResult]) -> str:
    lines = []
    for r in results:
        if r.own:
            lines.append(f"{r.question_id} {r.point_index} LEAK: {r.ask}")
        else:
            earns = f" (earns {', '.join(map(str, r.others))})" if r.others else ""
            lines.append(f"{r.question_id} {r.point_index} ok{earns}")
    leaks = sum(r.own for r in results)
    lines.append(f"{leaks} of {len(results)} asks earn their own point")
    return "\n".join(lines)
