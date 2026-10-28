from langchain_core.messages import AIMessage, HumanMessage

from app.graph.brief import build_brief
from app.graph.critic import Critique
from app.graph.reply import governed_reply, write_reply
from app.graph.state import GradedAnswer, Intent, Phase, TurnScratch, initial_state

MUST_ALLOWED = "nennt, dass das Entwerfen einer Kundenmail mit einem KI-System erlaubte Nutzung ist"
MUST_COMPETENCE = (
    "nennt, dass es stattdessen auf KI-Kompetenz ankommt: die Risiken des Werkzeugs kennen "
    "oder sein Ergebnis prüfen"
)
CLEAN = "Richtig, das ist erlaubt.\n\nAber wer liest den Entwurf, bevor er rausgeht?"
LEAKY = "Richtig. Du musst das Ergebnis prüfen, bevor es rausgeht. Oder?"


def _state(message: str, phase: Phase = Phase.lesson) -> dict:
    from app.graph.state import TestState

    state = initial_state("clerk")
    state["phase"] = phase
    state["messages"] = [
        AIMessage("Deine Kollegin sagt, das sei verboten. Was antwortest du ihr?"),
        HumanMessage(message),
    ]
    state["turn"] = TurnScratch(intent=Intent.answer)
    key = "practice" if phase is Phase.lesson else "test"
    state[key] = TestState(question_ids=["q-02-04"], practice=phase is Phase.lesson)
    return state


def _graded(matched: list[str], missing: list[str], attempt: bool = True) -> GradedAnswer:
    return GradedAnswer(
        question_id="q-02-04",
        answer="Ist erlaubt.",
        correct=not missing,
        attempt=attempt,
        matched=matched,
        missing=missing,
        feedback="Erlaubt genannt, die Prüfung fehlt.",
    )


def _partial() -> GradedAnswer:
    return _graded([MUST_ALLOWED], [MUST_COMPETENCE])


def _brief(deps, state, kind="partial", tries=1):
    return build_brief(deps, state, kind, deps.question("q-02-04"), _partial(), tries)


def test_the_writer_gets_the_brief_the_law_index_and_the_examples(make_deps):
    deps = make_deps(script={"reply": CLEAN})
    brief = _brief(deps, _state("Ist erlaubt."), tries=2)
    assert write_reply(deps, brief) == CLEAN
    prompt = deps.models["strong"].prompts[-1]
    assert prompt.startswith("[node:reply]")
    assert brief.text() in prompt
    assert "- ai_act" in prompt
    assert "Urlaubsanträge" in prompt
    assert "Write the reply." in prompt
    assert "previous draft" not in prompt


def test_a_retry_carries_the_whole_finding_and_the_proposed_revision(make_deps):
    deps = make_deps(script={"reply": CLEAN})
    critique = Critique(
        verdict="retry",
        faults=["leak"],
        notes="Die Frage selbst ist gut. Nenn die Prüfung nicht.",
        score=2,
        revision="Richtig. Und wer liest den Entwurf, bevor er rausgeht?",
    )
    write_reply(deps, _brief(deps, _state("Ist erlaubt.")), LEAKY, critique)
    prompt = deps.models["strong"].prompts[-1]
    assert "--- RETRY: the checker rejected your last draft" in prompt
    assert f"--- YOUR LAST DRAFT\n{LEAKY}" in prompt
    assert "Fault: leak (the draft hands a missing rubric point to the student)" in prompt
    assert "Notes: Die Frage selbst ist gut. Nenn die Prüfung nicht." in prompt
    assert (
        "--- THE CHECKER'S PROPOSED REVISION (a suggestion, not an order)\n"
        "Richtig. Und wer liest den Entwurf, bevor er rausgeht?" in prompt
    )
    assert "JOB and STYLE win" in prompt
    assert "Adopt the proposed revision" in prompt


def test_a_revision_identical_to_the_draft_is_not_offered_twice(make_deps):
    deps = make_deps(script={"reply": CLEAN})
    critique = Critique(verdict="retry", faults=["unhelpful"], notes="x", score=2, revision=LEAKY)
    write_reply(deps, _brief(deps, _state("Ist erlaubt.")), LEAKY, critique)
    assert "PROPOSED REVISION" not in deps.models["strong"].prompts[-1]


def test_a_governed_reply_ships_the_draft_the_critic_passes(make_deps):
    deps = make_deps(
        script={
            "reply": [LEAKY, CLEAN],
            "critic": [
                Critique(verdict="retry", faults=["leak"], notes="Nenn den Punkt nicht.", score=2),
                Critique(verdict="ship", score=5),
            ],
        }
    )
    state = _state("Ist erlaubt.")
    brief, governed = governed_reply(
        deps, state, "partial", deps.question("q-02-04"), _partial(), 1
    )
    assert governed.text == CLEAN and governed.shipped
    assert deps.models["strong"].calls == ["reply", "critic", "reply", "critic"]
    assert brief.text() in deps.models["strong"].prompts[1]
    assert LEAKY in deps.models["strong"].prompts[2]


def test_three_rejected_drafts_ship_the_best_one_never_a_template(make_deps):
    deps = make_deps(
        script={
            "reply": ["eins", "zwei", "drei"],
            "critic": [
                Critique(verdict="retry", faults=["leak"], notes="a", score=1),
                Critique(verdict="retry", faults=["repeat"], notes="b", score=4),
                Critique(verdict="retry", faults=["leak"], notes="c", score=2),
            ],
        }
    )
    state = _state("Ist erlaubt.")
    _, governed = governed_reply(deps, state, "partial", deps.question("q-02-04"), _partial(), 1)
    assert governed.text == "zwei" and not governed.shipped
    assert governed.faults == ["repeat"]
    assert deps.models["strong"].calls.count("reply") == 3


def test_a_right_reply_is_written_and_judged_too(make_deps):
    deps = make_deps(
        script={"reply": "Genau, so ist es.", "critic": Critique(verdict="ship", score=5)}
    )
    state = _state("Ist erlaubt.")
    _, governed = governed_reply(
        deps,
        state,
        "right",
        deps.question("q-02-04"),
        _graded([MUST_ALLOWED, MUST_COMPETENCE], []),
        1,
    )
    assert governed.text == "Genau, so ist es."
    assert "Outcome: right." in deps.models["strong"].prompts[0]
    assert deps.models["strong"].calls == ["reply", "critic"]


def test_the_test_phase_brief_reaches_the_writer(make_deps):
    deps = make_deps(
        script={"reply": "1 von 2. Noch einmal?", "critic": Critique(verdict="ship", score=4)}
    )
    state = _state("Ist erlaubt.", Phase.test)
    brief, _ = governed_reply(deps, state, "test_retry", deps.question("q-02-04"), _partial(), 1)
    assert "as a count" in brief.job
    assert "Try 1." in deps.models["strong"].prompts[0]
