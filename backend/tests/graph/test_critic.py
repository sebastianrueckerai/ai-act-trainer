import pytest
import structlog
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

from app.graph.brief import build_brief
from app.graph.critic import (
    REPLY_CHECKLIST,
    REPLY_EXAMPLES,
    Critique,
    VoiceCritique,
    critique_reply,
    critique_voice,
)
from app.graph.state import GradedAnswer, initial_state

DRAFT = "Richtig, das ist erlaubt.\n\nAber wer liest den Entwurf, bevor er rausgeht?"


def _brief(deps):
    from app.graph.state import TestState

    state = initial_state("clerk")
    state["messages"] = [AIMessage("Was antwortest du ihr?"), HumanMessage("Ist erlaubt.")]
    state["practice"] = TestState(question_ids=["q-02-04"], practice=True)
    question = deps.question("q-02-04")
    graded = GradedAnswer(
        question_id="q-02-04",
        answer="Ist erlaubt.",
        correct=False,
        matched=[question.rubric.must[0].point],
        missing=[question.rubric.must[1].point],
    )
    return build_brief(deps, state, "partial", question, graded)


def test_the_reply_critic_reads_the_brief_the_draft_and_its_checklist(make_deps):
    deps = make_deps(script={"critic": Critique(verdict="ship", score=5)})
    verdict = critique_reply(deps, _brief(deps), DRAFT)
    assert verdict.verdict == "ship"
    prompt = deps.models["strong"].prompts[-1]
    assert prompt.startswith("[node:critic]")
    assert "You are the checker of the tutor's next message" in prompt
    assert _brief(deps).text() in prompt
    assert f"===== THE DRAFT TO CHECK =====\n{DRAFT}\n===== END OF THE DRAFT =====" in prompt
    assert "--- CHECKS (in this order)" in prompt
    assert "--- WORKED EXAMPLES" in prompt
    assert "do the paste-back test literally" in prompt
    assert "read the last Tutor line under Conversation" in prompt
    assert "Urlaubsanträge" in prompt
    assert "'Das ist nicht richtig.' or 'Du hast recht, das ist nicht korrekt.'" in prompt
    assert deps.models["strong"].calls == ["critic"]


def test_the_reply_checklist_guards_the_ask():
    assert "Ask now" in REPLY_CHECKLIST
    assert "the ask itself repeats by design" in REPLY_CHECKLIST


def test_the_answer_giving_check_only_runs_while_the_question_is_open(make_deps):
    deps = make_deps(script={"critic": Critique(verdict="ship", score=5)})
    closed = _brief(deps).model_copy(update={"kind": "settled"})
    critique_reply(deps, closed, "So ist es: erlaubt, und du prüfst das Ergebnis.")
    closed_prompt = deps.models["strong"].prompts[-1]
    critique_reply(deps, _brief(deps), DRAFT)
    open_prompt = deps.models["strong"].prompts[-1]
    assert "do the paste-back test literally" in open_prompt
    assert "do the paste-back test literally" not in closed_prompt


def test_a_credited_list_on_a_closed_reply_changes_nothing(make_deps):
    deps = make_deps(script={"critic": Critique(verdict="ship", score=5, credited=[1, 2])})
    brief = _brief(deps).model_copy(update={"kind": "settled"})
    verdict = critique_reply(deps, brief, "So ist es: erlaubt, und du prüfst das Ergebnis.")
    assert verdict.verdict == "ship"
    assert verdict.faults == []


def test_the_critic_log_carries_the_verdict_not_the_texts(make_deps):
    deps = make_deps(
        script={
            "critic": Critique(
                verdict="retry", faults=["leak"], notes="Die Frage nennt den Punkt.", score=2
            )
        }
    )
    with structlog.testing.capture_logs() as logs:
        critique_reply(deps, _brief(deps), DRAFT)
    entry = next(entry for entry in logs if entry["event"] == "critic_verdict")
    assert entry["verdict"] == "retry"
    assert entry["faults"] == ["leak"]
    assert "notes" not in entry and "verdict_raw" not in entry


def test_the_reply_critic_returns_faults_and_notes(make_deps):
    deps = make_deps(
        script={
            "critic": Critique(
                verdict="retry", faults=["leak"], notes="Die Frage nennt den Punkt.", score=2
            )
        }
    )
    verdict = critique_reply(deps, _brief(deps), DRAFT)
    assert verdict.faults == ["leak"] and verdict.score == 2
    assert verdict.notes == "Die Frage nennt den Punkt."


def test_the_voice_critic_reads_draft_and_rewrite_with_the_fidelity_job(make_deps):
    deps = make_deps(
        script={"voice_critic": Critique(verdict="retry", faults=["question"], score=3)}
    )
    verdict = critique_voice(deps, _brief(deps), DRAFT, DRAFT + " Und wer noch?")
    assert verdict.faults == ["question"]
    assert deps.models["strong"].calls == ["voice_critic"]
    prompt = deps.models["strong"].prompts[-1]
    assert f"The tutor's draft:\n{DRAFT}" in prompt
    assert f"The rewrite in the character's voice:\n{DRAFT} Und wer noch?" in prompt
    assert "a fact, a rule or a hint about the case was added" in prompt
    assert "paste-back" not in prompt


def test_a_critique_needs_a_score_between_one_and_five():
    with pytest.raises(ValueError):
        Critique(verdict="ship", score=6)


def test_a_credited_missing_point_is_a_leak_whatever_the_verdict_line_says(make_deps):
    deps = make_deps(
        script={
            "critic": Critique(verdict="ship", score=5, credited=[2], notes="Eine passende Frage.")
        }
    )
    brief = _brief(deps)
    assert list(brief.missing) == [2]
    assert "Missing:\n2. " in brief.text()
    verdict = critique_reply(deps, brief, DRAFT)
    assert verdict.verdict == "retry"
    assert verdict.faults == ["leak"]
    assert verdict.credited == [2]
    # The critic's own notes praised the draft; the writer gets the paste-back finding.
    assert "Eine passende Frage." not in verdict.notes
    assert "2. " + brief.missing[2] in verdict.notes
    assert "end on the Ask now line" in verdict.notes
    assert "Ask a new question" not in verdict.notes
    assert "point by point" in deps.models["strong"].prompts[-1]


def test_a_number_that_names_a_met_point_or_no_point_is_not_a_leak(make_deps):
    deps = make_deps(script={"critic": Critique(verdict="ship", score=5, credited=[1, 0, 9])})
    assert critique_reply(deps, _brief(deps), DRAFT).verdict == "ship"


def test_an_empty_credited_list_changes_nothing(make_deps):
    deps = make_deps(script={"critic": Critique(verdict="ship", score=5)})
    assert critique_reply(deps, _brief(deps), DRAFT).verdict == "ship"


def test_the_reply_critic_asks_for_a_schema_without_voice_faults(make_deps):
    deps = make_deps(script={"critic": Critique(verdict="retry", score=2, faults=["meaning"])})
    with pytest.raises(ValidationError):
        critique_reply(deps, _brief(deps), DRAFT)


def test_the_closing_line_names_the_function_the_model_must_call(make_deps):
    deps = make_deps(
        script={
            "critic": Critique(verdict="ship", score=5),
            "voice_critic": Critique(verdict="ship", score=5),
        }
    )
    critique_reply(deps, _brief(deps), DRAFT)
    assert deps.models["strong"].prompts[-1].endswith("calling the function ReplyCritique.")
    critique_voice(deps, _brief(deps), DRAFT, DRAFT)
    assert deps.models["strong"].prompts[-1].endswith("calling the function VoiceCritique.")


def test_the_voice_critic_has_no_style_fault():
    with pytest.raises(ValidationError):
        VoiceCritique(verdict="retry", score=2, faults=["style"])


def test_the_voice_critic_asks_for_a_schema_without_reply_faults(make_deps):
    deps = make_deps(script={"voice_critic": Critique(verdict="retry", score=2, faults=["leak"])})
    with pytest.raises(ValidationError):
        critique_voice(deps, _brief(deps), DRAFT, DRAFT)


def test_after_a_green_try_no_hint_is_owed_so_unhelpful_alone_ships(make_deps):
    deps = make_deps(
        script={"critic": Critique(verdict="retry", score=3, faults=["unhelpful"], notes="x")}
    )
    verdict = critique_reply(deps, _brief(deps), DRAFT)
    assert verdict.verdict == "ship"
    assert verdict.faults == []


def test_after_a_green_try_other_faults_still_send_the_draft_back(make_deps):
    deps = make_deps(
        script={
            "critic": Critique(
                verdict="retry", score=2, faults=["unhelpful", "question"], notes="x"
            )
        }
    )
    verdict = critique_reply(deps, _brief(deps), DRAFT)
    assert verdict.verdict == "retry"
    assert verdict.faults == ["question"]


def test_a_shipped_settled_reply_that_asks_a_question_goes_back(make_deps):
    deps = make_deps(
        script={
            "critic": Critique(
                verdict="ship", score=5, notes="Der Entwurf stellt die erforderliche Frage."
            )
        }
    )
    brief = _brief(deps).model_copy(update={"kind": "right", "ask": ""})
    verdict = critique_reply(
        deps, brief, "Richtig, du prüfst den Entwurf. Wie sorgst du künftig dafür?"
    )
    assert verdict.verdict == "retry"
    assert verdict.faults == ["question"]
    assert "Drop the question" in verdict.notes
    assert "erforderliche Frage" not in verdict.notes


def test_a_settled_reply_the_checker_already_flagged_keeps_its_notes(make_deps):
    deps = make_deps(
        script={
            "critic": Critique(
                verdict="retry", score=2, faults=["question"], notes="Die Frage muss weg."
            )
        }
    )
    brief = _brief(deps).model_copy(update={"kind": "settled", "ask": ""})
    verdict = critique_reply(deps, brief, "Richtig. Und warum?")
    assert verdict.verdict == "retry"
    assert verdict.faults == ["question"]
    assert verdict.notes == "Die Frage muss weg."


def test_the_question_check_is_scoped_by_outcome():
    assert "- question, while the question is open" in REPLY_CHECKLIST
    assert "- question, when the outcome is right or settled" in REPLY_CHECKLIST


def test_the_worked_examples_carry_a_right_reply_with_no_question():
    assert "the outcome right, no question" in REPLY_EXAMPLES
    assert "the outcome right:" in REPLY_EXAMPLES


def test_a_settled_reply_with_no_question_mark_has_no_question_fault(make_deps):
    deps = make_deps(
        script={"critic": Critique(verdict="retry", score=3, faults=["question"], notes="x")}
    )
    brief = _brief(deps).model_copy(update={"kind": "right", "ask": ""})
    assert critique_reply(deps, brief, "Richtig, du prüfst den Entwurf.").verdict == "ship"
    assert critique_reply(deps, brief, "Richtig. Und warum?").verdict == "retry"


def test_the_reply_checklist_names_the_on_track_register():
    assert "Du bist auf dem richtigen Weg" in REPLY_CHECKLIST
    assert "on the right track" in REPLY_CHECKLIST


def test_after_an_orange_try_unhelpful_stands(make_deps):
    deps = make_deps(
        script={"critic": Critique(verdict="retry", score=3, faults=["unhelpful"], notes="x")}
    )
    brief = _brief(deps).model_copy(update={"kind": "on_track"})
    assert critique_reply(deps, brief, DRAFT).verdict == "retry"
