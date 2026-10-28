"""the owner's paste-back test (D108): the tutor's reply pasted back as the answer must earn
nothing the student has not earned. The eval's bar, not the pipeline's gate (D114)."""

from app.content.models import Question
from app.graph.deps import GraphDeps
from app.graph.grade import grade_answer

STATES_THE_ANSWER = "the draft states the answer"


def gives_away(
    deps: GraphDeps,
    question: Question,
    draft: str,
    missing: list[str],
    step: str = "",
    recent: list[str] | None = None,
) -> list[str]:
    """The missing must points the lenient practice grader credits the draft with, graded
    in context: recent is the exchange before the draft, and the draft is the tutor's last
    line, so the grader reads a pasted question as the tutor's, not as an answer. For a
    yes/no or multiple-choice question the whole answer is the one point: the draft
    leaks when it grades correct or, for a choice, quotes the right option's text."""
    if question.type == "multiple_choice":
        right = next(o for o in question.options if o.key == question.correct)
        if right.text.lower() in draft.lower():
            return [STATES_THE_ANSWER]
    if question.type == "free_text" and not missing:
        return []
    graded = grade_answer(
        deps,
        question,
        draft,
        "de",
        practice_context=step,
        recent=[*(recent or []), f"Tutor: {draft}"],
    )
    if question.type != "free_text":
        return [STATES_THE_ANSWER] if graded.correct else []
    return [point for point in missing if point in graded.matched]
