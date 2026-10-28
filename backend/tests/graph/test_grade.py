import structlog

from app.graph.grade import (
    PRACTICE_RULE,
    ProseChoice,
    Verdict,
    _grade_prompt,
    grade_answer,
    plain_point,
    practice_step_text,
)
from app.graph.state import ModelAnswerCard
from app.graph.test_flow import grade_node

OPTION_B_TEXT = "Auf unserer Website beantwortet ein KI-Chatfenster die Fragen von Kunden."
MUST_ALLOWED = "nennt, dass du prüfst, ob unser Zweck die Daten über die Kunden trägt"
MUST_COMPETENCE = "nennt, dass du prüfst, ob etwas drin ist, das das Haus geheim hält"
SHOULD_PERSONS = "nennt, dass du zuerst prüfst, ob überhaupt Daten über Personen drin sind"
SHOULD_FALLBACK = "nennt das Anonymisieren oder den Datenschutzbeauftragten als Weg im Zweifel"
SHOULD_ARTICLE = (
    "nennt Art. 6 Abs. 1 Buchst. f DSGVO für das berechtigte Interesse oder § 2 Nr. "
    "1 GeschGehG für das Geschäftsgeheimnis"
)


def test_a_yes_key_grades_correct_without_a_model_call(make_deps):
    deps = make_deps(script={})
    graded = grade_answer(deps, deps.question("q-01-01"), "yes", "de")
    assert graded.question_id == "q-01-01"
    assert graded.answer == "yes"
    assert graded.correct is True
    assert graded.matched == []
    assert graded.missing == []
    assert graded.tries == 1
    assert graded.hint_shown is False
    assert deps.models["fast"].calls == []


def test_a_no_key_grades_wrong_for_a_yes_question(make_deps):
    deps = make_deps(script={})
    graded = grade_answer(deps, deps.question("q-01-01"), "no", "de")
    assert graded.correct is False
    assert graded.answer == "no"
    assert graded.matched == []
    assert graded.missing == []
    assert deps.models["fast"].calls == []


def test_an_option_letter_grades_correct_for_the_choice_question(make_deps):
    deps = make_deps(script={})
    graded = grade_answer(deps, deps.question("q-01-03"), "b", "de")
    assert graded.correct is True
    assert deps.models["fast"].calls == []


def test_a_wrong_option_letter_grades_wrong_without_the_unrecognized_note(make_deps):
    deps = make_deps(script={})
    graded = grade_answer(deps, deps.question("q-01-03"), "a", "de")
    assert graded.correct is False
    assert graded.missing == []


def test_a_free_text_verdict_carries_the_graders_own_words(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(
                correct=False,
                matched=[1],
                missing=[2],
                feedback="Erlaubt genannt, die Prüfung fehlt.",
            )
        }
    )
    graded = grade_answer(deps, deps.question("q-02-04"), "Ist erlaubt.", "de")
    assert graded.feedback == "Erlaubt genannt, die Prüfung fehlt."
    # The scripted model answers as a tool call; the raw dump keeps it whole.
    assert "Erlaubt genannt" in graded.verdict_raw
    assert "Verdict" in graded.verdict_raw


def test_the_grade_log_carries_the_verdict_not_the_texts(make_deps):
    deps = make_deps(script={"grade": Verdict(correct=True, matched=[1, 2], feedback="Passt.")})
    with structlog.testing.capture_logs() as logs:
        grade_answer(deps, deps.question("q-02-04"), "Erlaubt, ich pruefe.", "de")
    entry = next(entry for entry in logs if entry["event"] == "grade_verdict")
    assert entry["question"] == "q-02-04"
    assert entry["correct"] is True
    assert entry["matched"] == [1, 2]
    assert entry["answer_len"] == len("Erlaubt, ich pruebe.")
    assert "seconds" in entry
    assert "answer" not in entry and "feedback" not in entry and "verdict_raw" not in entry


def test_the_grade_log_carries_the_texts_only_where_transcripts_are_kept(make_deps):
    deps = make_deps(
        script={"grade": Verdict(correct=True, matched=[1], feedback="Passt.")}, data_level=2
    )
    with structlog.testing.capture_logs() as logs:
        grade_answer(deps, deps.question("q-02-04"), "Erlaubt, ich pruefe.", "de")
    entry = next(entry for entry in logs if entry["event"] == "grade_verdict")
    assert entry["feedback"] == "Passt."
    assert "Verdict" in entry["verdict_raw"]


def test_no_log_record_of_a_grade_carries_the_students_text(make_deps):
    answer = "Auf unserer Website beantwortet ein KI-Chatfenster die Fragen von Kunden."
    deps = make_deps(
        script={"prose": ProseChoice(answer="B"), "grade": Verdict(correct=True, matched=[1])}
    )
    with structlog.testing.capture_logs() as logs:
        grade_answer(deps, deps.question("q-01-03"), answer, "de")
    assert any(entry["event"] == "prose_resolution" for entry in logs)
    for entry in logs:
        assert answer not in str(entry.values())


def test_the_full_option_text_is_read_by_the_fast_model(make_deps):
    deps = make_deps(script={"prose": ProseChoice(answer="B")})
    graded = grade_answer(deps, deps.question("q-01-03"), OPTION_B_TEXT, "de")
    assert graded.correct is True
    assert deps.models["fast"].calls == ["prose"]


def test_a_paraphrased_option_is_resolved_by_the_prose_model(make_deps):
    deps = make_deps(script={"prose": ProseChoice(answer="B")})
    graded = grade_answer(
        deps, deps.question("q-01-03"), "das KI-Chatfenster auf der Website", "de"
    )
    assert graded.correct is True
    assert deps.models["fast"].calls == ["prose"]


def test_a_paraphrased_yes_no_reply_is_resolved_by_the_prose_model(make_deps):
    deps = make_deps(script={"prose": ProseChoice(answer="no")})
    graded = grade_answer(deps, deps.question("q-01-01"), "Auf keinen Fall", "de")
    assert graded.correct is False
    assert graded.missing == []
    assert deps.models["fast"].calls == ["prose"]


def test_a_correct_free_text_verdict_carries_matched_and_missing(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(
                correct=True,
                matched=[1, 2, 3, 4, 5],
                missing=[],
                feedback="Gut gemacht.",
            )
        }
    )
    answer = "Das ist erlaubt, dafür braucht es keine Genehmigung, nur Kontrolle."
    graded = grade_answer(deps, deps.question("q-02-04"), answer, "de")
    assert graded.question_id == "q-02-04"
    assert graded.answer == answer
    assert graded.correct is True
    assert graded.matched == [
        MUST_ALLOWED,
        MUST_COMPETENCE,
        SHOULD_PERSONS,
        SHOULD_FALLBACK,
        SHOULD_ARTICLE,
    ]
    assert graded.missing == []
    assert deps.models["strong"].calls == ["grade"]


def test_a_wrong_free_text_verdict_is_carried_as_wrong(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(
                correct=False,
                matched=[1],
                missing=[2, 3, 4, 5],
                feedback="Halb.",
            )
        }
    )
    graded = grade_answer(deps, deps.question("q-02-04"), "Ist doch erlaubt.", "de")
    assert graded.correct is False
    assert graded.matched == [MUST_ALLOWED]
    assert graded.missing == [MUST_COMPETENCE, SHOULD_PERSONS, SHOULD_FALLBACK, SHOULD_ARTICLE]


def test_an_out_of_range_verdict_index_is_dropped_not_raised(make_deps):
    deps = make_deps(
        script={"grade": Verdict(correct=False, matched=[1], missing=[0, 99], feedback="")}
    )
    graded = grade_answer(deps, deps.question("q-02-04"), "Teilantwort.", "de")
    assert graded.matched == [MUST_ALLOWED]
    assert graded.missing == []


PRACTICE_STEP = "q-03-02"
FOLLOW_UP = (
    "Richtig, du sagst, das Verfassen ist erlaubt.\n\n"
    "Zur Kundenmail deiner Kollegin: worauf musst du bei der KI noch achten, bevor sie rausgeht?"
)
LEAKY_FOLLOW_UP = (
    "Dir fehlt noch: nennt, dass es stattdessen auf KI-Kompetenz ankommt: die Risiken des "
    "Werkzeugs kennen oder sein Ergebnis prüfen"
)
RIGHT_REPLY = "Genau, das darfst du. Wichtig ist nur, dass du den Entwurf vor dem Absenden liest."
SETTLED_REPLY = "Erlaubt ist es, und du prüfst den Entwurf vor dem Absenden."


def _practice_state(deps, question_id: str, message: str, step_idx: int = 2, chapter_idx: int = 0):
    from langchain_core.messages import HumanMessage

    from app.graph.state import Intent, Phase, TestState, TurnScratch, initial_state

    state = initial_state("clerk")
    state["phase"] = Phase.lesson
    state["chapter_idx"] = chapter_idx
    state["step_idx"] = step_idx
    state["messages"] = [HumanMessage(message)]
    state["turn"] = TurnScratch(intent=Intent.answer)
    state["practice"] = TestState(question_ids=[question_id], practice=True)
    return state


def _test_state(deps, question_id: str, message: str):
    from langchain_core.messages import HumanMessage

    from app.graph.state import Intent, Phase, TestState, TurnScratch, initial_state

    state = initial_state("clerk")
    state["phase"] = Phase.test
    state["messages"] = [HumanMessage(message)]
    state["turn"] = TurnScratch(intent=Intent.answer)
    state["test"] = TestState(question_ids=[question_id, "q-01-01"])
    return state


def test_the_step_a_practice_question_follows_is_found_by_the_question_id(make_deps):
    deps = make_deps(script={})
    step = next(
        s for chapter in deps.chapters("de") for s in chapter.steps if s.question == PRACTICE_STEP
    )
    context = practice_step_text(deps, "de", PRACTICE_STEP)
    assert context.startswith(step.text)
    assert practice_step_text(deps, "de", "q-01-01") == ""


def test_a_practice_grading_prompt_carries_the_step_and_reads_the_rubric_leniently(make_deps):
    deps = make_deps(script={})
    question = deps.question(PRACTICE_STEP)
    step = next(
        s for chapter in deps.chapters("de") for s in chapter.steps if s.question == PRACTICE_STEP
    )
    context = practice_step_text(deps, "de", PRACTICE_STEP)
    lenient = _grade_prompt(question, "Falsch, wir dürfen!", context, [])
    assert context in lenient
    assert PRACTICE_RULE in lenient
    strict = _grade_prompt(question, "Falsch, wir dürfen!", None, [])
    assert PRACTICE_RULE not in strict
    assert step.text not in strict


def test_the_grader_grades_the_transcript_not_a_detached_field(make_deps):
    question = make_deps(script={}).question(PRACTICE_STEP)
    prompt = _grade_prompt(question, "Ja", "Schritt", ["Tutor: Aber ist das zulässig?"])
    assert "You grade the last Student line of the conversation" in prompt
    assert "The case the conversation is about:" in prompt
    assert f"Question: {question.question}" not in prompt
    assert "Student answer:" not in prompt
    assert prompt.index("Tutor: Aber ist das zulässig?") < prompt.index("Student: Ja")
    assert "The last Student line is the answer to grade" in prompt
    assert "it replies to the Tutor line directly above it" in prompt
    assert "Earlier Student lines answered earlier Tutor lines" in prompt
    bare = _grade_prompt(question, "Ja", "Schritt", [])
    assert "Student: Ja" in bare
    assert "The last Student line is the answer to grade" in bare


def test_a_graded_test_answer_keeps_its_card_and_calls_no_practice_writer(make_deps):
    deps = make_deps(script={"grade": Verdict(correct=True, matched=[1, 2]), "practice": "Genau."})
    question = deps.question(PRACTICE_STEP)
    result = grade_node(deps)(_test_state(deps, PRACTICE_STEP, "Erlaubt, und ich prüfe es."))
    card = result["turn"].parts[0]
    assert isinstance(card, ModelAnswerCard)
    assert card.question == question.question
    assert [part.ref for part in card.citations] == ["Art. 26(2)"]
    assert deps.models["strong"].calls == ["grade"]


def test_a_practice_rubric_point_loses_its_grading_verb_for_the_student(make_deps):
    assert plain_point(MUST_ALLOWED) == (
        "dass du prüfst, ob unser Zweck die Daten über die Kunden trägt"
    )
    assert plain_point("begründet es damit, dass der Lieferant seine Preise nicht nennt") == (
        "dass der Lieferant seine Preise nicht nennt"
    )
    assert plain_point("nennt § 2 Nr. 1 GeschGehG für das Geschäftsgeheimnis") == (
        "nennt § 2 Nr. 1 GeschGehG für das Geschäftsgeheimnis"
    )


def test_q_01_12_settles_on_who_stands_for_it(make_deps):
    # "Ich" answers it (D110): the reason is a should point, the actor the one must point.
    question = make_deps().question("q-01-12")
    assert question.rubric.must_texts == [
        "nennt, dass du dafür geradestehst, nicht der Anbieter des Werkzeugs und nicht die KI"
    ]
    assert len(question.rubric.should) == 3


def test_the_grader_sees_the_recent_conversation(make_deps):
    deps = make_deps(script={"grade": Verdict(correct=False, matched=[1], missing=[2])})
    grade_answer(
        deps,
        deps.question("q-02-04"),
        "Ja",
        "de",
        recent=["Tutor: Ist das zulässig?", "Student: hm"],
    )
    prompt = deps.models["strong"].prompts[-1]
    assert "Tutor: Ist das zulässig?\nStudent: hm" in prompt
    assert (
        "matched lists every point the last Student line states, whether or not it is "
        "an attempt" in prompt
    )


def test_the_grade_prompt_names_a_copied_tutor_line(make_deps):
    question = make_deps(script={}).question(PRACTICE_STEP)
    prompt = _grade_prompt(question, "Ja", "Schritt", ["Tutor: Aber ist das zulässig?"])
    assert "repeats the tutor's last message" in prompt
    assert "copied is true" in prompt
    assert "A question the tutor asked, repeated back, states nothing" in prompt


def test_a_copied_answer_is_marked_so_and_still_graded(make_deps):
    deps = make_deps(
        script={"grade": Verdict(correct=False, matched=[1], missing=[2], copied=True)}
    )
    graded = grade_answer(
        deps,
        deps.question("q-02-04"),
        "Richtig, das ist erlaubt.",
        "de",
        recent=["Tutor: Richtig, das ist erlaubt."],
    )
    assert graded.copied is True
    assert graded.matched == [MUST_ALLOWED]


def test_a_message_that_is_no_attempt_is_marked_so(make_deps):
    deps = make_deps(
        script={"grade": Verdict(correct=False, attempt=False, matched=[], missing=[1, 2])}
    )
    graded = grade_answer(deps, deps.question("q-02-04"), "Was meinst du damit?", "de")
    assert graded.attempt is False
    assert graded.correct is False


def test_an_unresolved_yes_no_reply_is_no_attempt(make_deps):
    deps = make_deps(script={"prose": ProseChoice(answer="unclear")})
    graded = grade_answer(deps, deps.question("q-01-01"), "Wie meinst du das?", "de")
    assert graded.attempt is False
    assert graded.correct is False
    assert graded.missing == []


def test_an_unresolved_choice_reply_is_no_attempt(make_deps):
    deps = make_deps(script={"prose": ProseChoice(answer="none")})
    graded = grade_answer(deps, deps.question("q-01-03"), "Keine Ahnung.", "de")
    assert graded.attempt is False
    assert graded.correct is False
    assert graded.missing == []


ASK = "In der Liste stehen auch die Umsätze und Rabatte jedes Kunden. Was prüfst du daran noch?"


def test_the_tutors_question_pasted_back_is_no_attempt_and_calls_no_model(make_deps):
    deps = make_deps(script={})
    question = deps.question("q-02-04")
    for pasted in [ASK, "Was prüfst du vorher?", "  was prüfst du vorher "]:
        graded = grade_answer(
            deps, question, pasted, "de", recent=[f"Tutor: Richtig, verboten ist das nicht. {ASK}"]
        )
        assert graded.attempt is False
        assert graded.matched == []
    assert deps.models["strong"].calls == []


def test_a_pasted_tutor_statement_or_an_own_question_still_goes_to_the_grader(make_deps):
    deps = make_deps(script={"grade": [Verdict(correct=False, matched=[], missing=[1, 2])] * 2})
    question = deps.question("q-02-04")
    recent = [f"Tutor: Richtig, verboten ist das nicht. {ASK}"]
    grade_answer(deps, question, "Richtig, verboten ist das nicht.", "de", recent=recent)
    grade_answer(deps, question, "Muss sie den Entwurf prüfen?", "de", recent=recent)
    assert deps.models["strong"].calls == ["grade", "grade"]


def test_an_on_track_verdict_lands_on_the_graded_answer(make_deps):
    deps = make_deps(
        script={"grade": Verdict(correct=False, matched=[], missing=[1, 2], on_track=True)}
    )
    graded = grade_answer(deps, deps.question("q-02-04"), "Kommt auf die Mail an.", "de")
    assert graded.attempt is True
    assert graded.on_track is True
    assert graded.matched == []


def test_the_grade_prompt_defines_on_track(make_deps):
    prompt = _grade_prompt(make_deps().question("q-02-04"), "x", None, [])
    assert "on_track is true when" in prompt
    assert "states nothing wrong about the case" in prompt
    assert "contradicts a point, names the wrong actor" in prompt
