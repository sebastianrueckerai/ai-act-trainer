import time

from langchain_core.messages import AIMessage, HumanMessage

from app.graph.brief import Brief, build_brief, speaker_lines
from app.graph.state import GradedAnswer, Intent, Phase, TurnScratch, initial_state

MUST_ALLOWED = "nennt, dass du prüfst, ob unser Zweck die Daten über die Kunden trägt"
MUST_COMPETENCE = "nennt, dass du prüfst, ob etwas drin ist, das das Haus geheim hält"
ASK_ALLOWED = "Also, was prüfst du an der Kundenliste, bevor sie in den Assistenten geht?"
ASK_COMPETENCE = (
    "In der Liste stehen auch die Umsätze und Rabatte jedes Kunden. Was prüfst du daran noch?"
)


def _state(message: str, phase: Phase = Phase.lesson) -> dict:
    from app.graph.state import TestState

    state = initial_state("clerk")
    state["phase"] = phase
    state["messages"] = [
        AIMessage("Deine Kollegin sagt, das sei verboten. Was antwortest du ihr?"),
        HumanMessage("hm"),
        AIMessage("Sag es in deinen Worten."),
        HumanMessage(message),
    ]
    state["turn"] = TurnScratch(intent=Intent.answer)
    key = "practice" if phase is Phase.lesson else "test"
    state[key] = TestState(
        question_ids=["q-02-04"],
        practice=phase is Phase.lesson,
        answers=[GradedAnswer(question_id="q-02-04", answer="weiß nicht", correct=False)],
    )
    return state


def _graded() -> GradedAnswer:
    return GradedAnswer(
        question_id="q-02-04",
        answer="Ist erlaubt.",
        correct=False,
        matched=[MUST_ALLOWED],
        missing=[MUST_COMPETENCE],
        feedback="Erlaubt genannt, die Prüfung fehlt.",
    )


def test_the_answer_brief_carries_the_whole_situation(make_deps):
    deps = make_deps()
    question = deps.question("q-03-02")
    must = question.rubric.must_texts
    graded = GradedAnswer(
        question_id="q-03-02",
        answer="Ist erlaubt.",
        correct=False,
        matched=[must[0]],
        missing=[must[1]],
    )
    state = _state("Ist erlaubt.")
    state["practice"] = state["practice"].model_copy(
        update={
            "question_ids": ["q-03-02"],
            "answers": [GradedAnswer(question_id="q-03-02", answer="weiß nicht", correct=False)],
        }
    )
    brief = build_brief(deps, state, "partial", question, graded, tries=2)
    text = brief.text()
    assert "--- COURSE" in text and "Phase: lesson" in text
    assert "--- CHAPTER STEP" in text and "Bewerbungssystem" in brief.step
    assert question.question in text and question.model_answer in text
    assert question.explanation in text and "Art. 26(2)" in text
    assert must[0] in brief.question and must[1] in brief.question
    assert "Required points:\n1. " + must[0] + "\n2. " + must[1] in brief.question
    assert "Optional points:\n3. " in brief.question
    assert "Met:\n1. " + must[0] in brief.verdict
    assert "Missing:\n2. " + must[1] in brief.verdict
    assert "adds nothing to it" in brief.job
    assert "uses none of the missing point's words" in brief.job
    assert brief.missing == {2: must[1]}
    assert "Erlaubt genannt, die Prüfung fehlt." not in text
    assert "Try 2 of 5" in brief.verdict
    assert "- weiß nicht" in brief.tries
    assert "Tutor: Deine Kollegin sagt" in brief.conversation
    assert "Student: hm" in brief.conversation
    assert brief.message == "Ist erlaubt."
    assert brief.job.startswith("Outcome: partial.")
    assert "Coach the student towards the answer" in brief.job
    assert "dein Unternehmen" in brief.style
    assert text.startswith("===== SITUATION FOR THE TUTOR'S NEXT MESSAGE =====")
    assert text.index("CHAPTER STEP") < text.index("QUESTION (") < text.index("VERDICT")
    assert text.index("VERDICT") < text.index("CONVERSATION") < text.index("JOB (")
    assert text.index("JOB (") < text.index("STYLE") < text.index("END OF SITUATION")


def test_the_brief_asks_for_the_first_unmet_must_point(make_deps):
    deps = make_deps(script={})
    question = deps.question("q-02-04")
    graded = GradedAnswer(
        question_id="q-02-04",
        answer="Schwachsinn!",
        correct=False,
        matched=[MUST_ALLOWED],
        missing=[MUST_COMPETENCE],
    )
    brief = build_brief(deps, _state("Schwachsinn!"), "partial", question, graded, 1)
    assert brief.ask == ASK_COMPETENCE
    assert f"Ask now: {ASK_COMPETENCE}" in brief.text()
    assert "Outcome: partial." in brief.text()
    assert "word for word" in brief.job


def test_the_brief_asks_for_point_one_when_only_point_two_is_met(make_deps):
    deps = make_deps(script={})
    question = deps.question("q-02-04")
    graded = GradedAnswer(
        question_id="q-02-04",
        answer="Prüfen.",
        correct=False,
        matched=[MUST_COMPETENCE],
        missing=[MUST_ALLOWED],
    )
    brief = build_brief(deps, _state("Prüfen."), "partial", question, graded, 1)
    assert brief.ask == ASK_ALLOWED


def test_a_wrong_brief_orders_the_ask_word_for_word(make_deps):
    deps = make_deps(script={})
    question = deps.question("q-02-04")
    graded = GradedAnswer(
        question_id="q-02-04",
        answer="Verboten.",
        correct=False,
        missing=[MUST_ALLOWED, MUST_COMPETENCE],
    )
    brief = build_brief(deps, _state("Verboten."), "wrong", question, graded, 1)
    assert brief.ask == ASK_ALLOWED
    assert "word for word" in brief.job


def test_a_settled_brief_has_no_ask(make_deps):
    deps = make_deps(script={})
    question = deps.question("q-02-04")
    graded = GradedAnswer(
        question_id="q-02-04",
        answer="Erlaubt, und ich prüfe.",
        correct=True,
        matched=[MUST_ALLOWED, MUST_COMPETENCE],
    )
    for kind in ("right", "settled"):
        brief = build_brief(deps, _state("x"), kind, question, graded, 1)
        assert brief.ask == ""
        assert "Ask now:" not in brief.text()


def test_a_settled_brief_owes_no_missing_points(make_deps):
    deps = make_deps(script={})
    question = deps.question("q-01-05")
    graded = _graded()
    for kind in ("right", "settled"):
        brief = build_brief(deps, _state("Ist erlaubt."), kind, question, graded, 1)
        assert "The question settles with this try." in brief.verdict
        assert "nothing owed" in brief.verdict
        assert f"Missing:\n2. {MUST_COMPETENCE}" not in brief.verdict
        assert brief.missing == {}


def test_a_non_attempt_brief_asks_for_the_first_point(make_deps):
    deps = make_deps(script={})
    question = deps.question("q-02-04")
    graded = GradedAnswer(
        question_id="q-02-04",
        answer="Was heißt KI-System?",
        correct=False,
        attempt=False,
        missing=[MUST_ALLOWED, MUST_COMPETENCE],
    )
    brief = build_brief(deps, _state("x"), "not_an_attempt", question, graded, 1)
    assert brief.ask == ASK_ALLOWED


def test_a_non_attempt_brief_on_a_yes_no_question_asks_the_question(make_deps):
    deps = make_deps(script={})
    question = deps.question("q-01-01")
    assert question.type == "yes_no" and not question.rubric
    graded = GradedAnswer(
        question_id="q-01-01", answer="Was heißt das?", correct=False, attempt=False
    )
    brief = build_brief(deps, _state("x"), "not_an_attempt", question, graded, 1)
    assert brief.ask == question.question
    assert f"Ask now: {question.question}" in brief.text()


def test_the_test_rule_never_claims_a_practice_question(make_deps):
    # One rule governs both phases (D128): its text may not open by naming one phase.
    deps = make_deps()
    brief = build_brief(
        deps, _state("Ist erlaubt.", Phase.test), "test_retry", deps.question("q-02-04"), _graded()
    )
    assert "not a test" not in brief.job
    assert "practice question" not in brief.job
    assert "as a count" in brief.job


def test_the_test_brief_carries_the_count_rule_and_no_try_limit(make_deps):
    deps = make_deps()
    brief = build_brief(
        deps, _state("Ist erlaubt.", Phase.test), "test_retry", deps.question("q-02-04"), _graded()
    )
    assert "as a count" in brief.job
    assert "Try 1." in brief.verdict
    assert "Try 1 of" not in brief.verdict
    assert "word for word" in brief.job
    assert brief.step == ""


def test_a_brief_with_no_question_open_has_empty_question_sections(make_deps):
    deps = make_deps()
    state = initial_state("clerk")
    state["messages"] = [HumanMessage("Was ist ein Betreiber?")]
    brief = build_brief(deps, state, "free_question")
    assert brief.question == "" and brief.verdict == "" and brief.tries == ""
    assert "Course position:" in brief.step
    assert "no question of the course open" in brief.job
    text = brief.text()
    assert "Question:" not in text and "Verdict:" not in text


def test_a_curated_brief_says_only_the_voice_runs(make_deps):
    deps = make_deps()
    state = initial_state("jester")
    state["messages"] = [HumanMessage("weiter")]
    assert "only the voice runs" in build_brief(deps, state, "curated").job


def test_a_brief_rebuilt_from_its_text_renders_the_same_text(make_deps):
    deps = make_deps()
    brief = build_brief(
        deps, _state("Ist erlaubt."), "partial", deps.question("q-02-04"), _graded()
    )
    assert Brief.from_text(brief.text()).text() == brief.text()


def test_the_conversation_shows_the_label_a_chip_sent_not_its_key(make_deps):
    deps = make_deps()
    state = initial_state("clerk")
    state["messages"] = [
        AIMessage("Zulässig?"),
        HumanMessage("yes", additional_kwargs={"shown": "Ja"}),
        HumanMessage("B", additional_kwargs={"shown": "B. Boot fahren"}),
    ]
    assert speaker_lines(state["messages"]) == [
        "Tutor: Zulässig?",
        "Student: Ja",
        "Student: B. Boot fahren",
    ]
    brief = build_brief(deps, state, "free_question")
    assert brief.message == "B. Boot fahren"


def test_the_conversation_is_the_last_ten_messages_before_the_message(make_deps):
    deps = make_deps()
    state = initial_state("clerk")
    state["messages"] = [HumanMessage(f"m{i}") for i in range(14)]
    brief = build_brief(deps, state, "free_question")
    assert brief.conversation.splitlines()[0] == "Student: m3"
    assert brief.conversation.splitlines()[-1] == "Student: m12"
    assert brief.message == "m13"


def test_the_brief_text_is_a_few_pages(make_deps):
    deps = make_deps()
    brief = build_brief(
        deps, _state("Ist erlaubt."), "partial", deps.question("q-02-04"), _graded()
    )
    assert len(brief.text()) < 12000


def test_the_turn_scratch_stamps_its_start():
    turn = TurnScratch()
    assert time.monotonic() - turn.started_at < 1
    assert turn.brief == ""
    assert not hasattr(turn, "outcome")


def test_earlier_tries_list_only_this_questions_answers(make_deps):
    from app.graph.state import TestState

    deps = make_deps()
    state = initial_state("clerk")
    state["phase"] = Phase.test
    state["messages"] = [AIMessage("Frage 2"), HumanMessage("Erlaubt.")]
    state["test"] = TestState(
        question_ids=["q-01-01", "q-02-04"],
        index=1,
        answers=[GradedAnswer(question_id="q-01-01", answer="yes", correct=True)],
    )
    brief = build_brief(deps, state, "test_retry", deps.question("q-02-04"), _graded())
    assert brief.tries == ""
    assert "Earlier tries" not in brief.text()


def test_a_settled_question_says_so_not_that_a_try_is_used_up(make_deps):
    deps = make_deps()
    brief = build_brief(
        deps, _state("Ist erlaubt."), "settled", deps.question("q-02-04"), _graded()
    )
    assert "The question is settled" in brief.job
    assert "last try is used up" not in brief.job


def test_a_copied_answer_is_named_in_the_verdict_and_the_job(make_deps):
    deps = make_deps()
    question = deps.question("q-02-04")
    graded = _graded().model_copy(update={"copied": True})
    brief = build_brief(deps, _state("Richtig, erlaubt."), "partial", question, graded, tries=1)
    assert "Repeats the tutor's last message." in brief.verdict
    assert "those were the tutor's words" in brief.job
    plain = build_brief(deps, _state("Erlaubt."), "partial", question, _graded(), tries=1)
    assert "Repeats the tutor's" not in plain.verdict
    assert "tutor's words" not in plain.job


def test_the_verdict_is_the_met_and_missing_lists_not_the_graders_note(make_deps):
    # The live grader wrote "nenne bitte, dass die Nutzung erlaubt ist" beside a Met list
    # holding exactly that point, and the critic took the note over the list (2026-09-29).
    deps = make_deps()
    graded = _graded().model_copy(update={"feedback": "Nenne bitte, dass die Nutzung erlaubt ist."})
    brief = build_brief(deps, _state("Blödsinn!"), "partial", deps.question("q-02-04"), graded)
    assert "Nenne bitte" not in brief.text()
    assert "Met:\n1. " + MUST_ALLOWED in brief.verdict


def test_a_partial_confirmation_says_the_student_is_right_and_never_echoes_a_rejection(
    make_deps,
):
    deps = make_deps()
    brief = build_brief(deps, _state("Blödsinn!"), "partial", deps.question("q-02-04"), _graded())
    assert "'Richtig, verboten ist das nicht.'" in brief.job
    assert "Never echo a rejection back ('Das ist nicht richtig.'" in brief.job


def test_a_green_try_that_leaves_the_question_open_reads_as_met_not_as_wrong(make_deps):
    # "correct=False" beside a Met list read as a wrong answer, and the critic vetoed
    # "Richtig" on a green try (2026-09-29).
    deps = make_deps()
    brief = build_brief(
        deps, _state("Schwachsinn!"), "partial", deps.question("q-02-04"), _graded()
    )
    assert "An attempt, every required point met: no.\nMet:\n1. " + MUST_ALLOWED in brief.verdict
    assert "correct=" not in brief.text()


def test_the_on_track_brief_names_the_replies_on_the_point_and_ends_on_the_ask(make_deps):
    deps = make_deps()
    graded = _graded().model_copy(
        update={"matched": [], "missing": [MUST_ALLOWED, MUST_COMPETENCE], "on_track": True}
    )
    brief = build_brief(
        deps,
        _state("Kommt drauf an."),
        "on_track",
        deps.question("q-02-04"),
        graded,
        tries=1,
        nudges=1,
    )
    assert brief.ask == ASK_ALLOWED
    assert "Outcome: on_track." in brief.job
    assert "on the right track" in brief.job
    assert "word for word" in brief.job
    assert "Try 1 of 5, second reply on this point." in brief.verdict


def test_the_try_line_counts_only_the_first_reply_without_nudges(make_deps):
    deps = make_deps()
    brief = build_brief(
        deps, _state("Erlaubt."), "partial", deps.question("q-02-04"), _graded(), tries=1
    )
    assert "Try 1 of 5." in brief.verdict
    assert "reply on this point" not in brief.verdict
