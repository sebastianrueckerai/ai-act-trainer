"""the owner's test, run against every free-text question: a partial answer goes through
grade, write and gate, then each persona, and the reply pasted back must earn no must point
the student had not earned."""

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from app.graph.deps import GraphDeps
from app.graph.grade import grade_answer, plain_point, practice_step_text
from app.graph.persona import persona_node
from app.graph.reply import governed_reply
from app.graph.state import Intent, Phase, TestState, TurnScratch, initial_state
from tests.evals.paste_back import gives_away


class PasteResult(BaseModel):
    question: str
    persona: str
    reply: str
    credited: list[str]

    @property
    def leaked(self) -> bool:
        return bool(self.credited)


def partial_answer(deps: GraphDeps, question_id: str) -> str:
    """A student who states only the first must point, in plain words."""
    point = plain_point(deps.question(question_id).rubric.must[0].point)
    return point[0].upper() + point[1:] + "."


def run_copy_paste(
    deps: GraphDeps, personas: list[str], question_ids: list[str] | None = None
) -> list[PasteResult]:
    results = []
    for question_id, question in sorted(deps.locale_content("de").questions.items()):
        if question.type != "free_text":
            continue
        if question_ids is not None and question_id not in question_ids:
            continue
        answer = partial_answer(deps, question_id)
        step = practice_step_text(deps, "de", question_id)
        state = initial_state("clerk")
        state["phase"] = Phase.lesson
        state["messages"] = [AIMessage(question.question), HumanMessage(answer)]
        state["turn"] = TurnScratch(intent=Intent.answer)
        state["practice"] = TestState(question_ids=[question_id], practice=True)
        recent = [f"Tutor: {question.question}"]
        graded = grade_answer(deps, question, answer, "de", practice_context=step, recent=recent)
        recent.append(f"Student: {answer}")
        missing = [p for p in question.rubric.must_texts if p not in graded.matched]
        if not missing:
            continue
        outcome = "partial" if graded.matched else "wrong"
        brief, governed = governed_reply(deps, state, outcome, question, graded, 1)
        reply = governed.text
        for persona_id in [None, *personas]:
            text = reply
            if persona_id is not None:
                voiced_state = {**state, "persona_id": persona_id}
                voiced_state["turn"] = TurnScratch(
                    draft=reply, context_question=question_id, brief=brief.text()
                )
                text = str(persona_node(deps)(voiced_state)["messages"][0].content)
            results.append(
                PasteResult(
                    question=question_id,
                    persona=persona_id or "none",
                    reply=text,
                    credited=gives_away(deps, question, text, missing, step, recent),
                )
            )
    return results


def render(results: list[PasteResult]) -> str:
    lines = []
    for result in results:
        lines.append(
            f"{result.question} {result.persona:8} leaked={'yes' if result.leaked else 'no'}"
        )
        if result.leaked:
            lines.append(f"    credited: {'; '.join(result.credited)}")
            lines.append(f"    reply: {result.reply}")
    leaked = sum(1 for result in results if result.leaked)
    lines.append(f"summary: {leaked} of {len(results)} replies leaked")
    return "\n".join(lines)
