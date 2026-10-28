import random

from langchain_core.messages import HumanMessage

from app.files.tokens import read_file_token
from app.graph.brief import build_brief
from app.graph.critic import Critique
from app.graph.draw import draw_questions
from app.graph.grade import ProseChoice, Verdict
from app.graph.state import (
    FilePart,
    GradedAnswer,
    InputHint,
    Intent,
    Mood,
    Phase,
    TurnScratch,
    hint_for_question,
    initial_state,
)
from app.graph.test_flow import (
    finish_test_node,
    grade_node,
    quit_test_node,
    skip_node,
    start_test_node,
    verdict_payload,
)
from app.i18n import t

CHAPTER_TITLE = "Was du mit KI am Arbeitsplatz darfst"
MUST_ALLOWED = "nennt, dass du prüfst, ob unser Zweck die Daten über die Kunden trägt"
MUST_COMPETENCE = "nennt, dass du prüfst, ob etwas drin ist, das das Haus geheim hält"
MUST_ALLOWED_HINT = "dass du prüfst, ob unser Zweck die Daten über die Kunden trägt"
MUST_COMPETENCE_HINT = "dass du prüfst, ob etwas drin ist, das das Haus geheim hält"
ASK_ALLOWED = "Also, was prüfst du an der Kundenliste, bevor sie in den Assistenten geht?"
ASK_COMPETENCE = (
    "In der Liste stehen auch die Umsätze und Rabatte jedes Kunden. Was prüfst du daran noch?"
)


def _attempt_state(question_ids, index=0, current_tries=1, message="yes"):
    from app.graph.state import TestState

    state = initial_state("clerk")
    state["phase"] = Phase.test
    state["streak"] = 0
    state["messages"] = [HumanMessage(message)]
    state["turn"] = TurnScratch(intent=Intent.answer)
    state["test"] = TestState(question_ids=question_ids, index=index, current_tries=current_tries)
    return state


def _practice_state(question_ids, index, message="yes"):
    from app.graph.state import TestState

    state = _attempt_state(question_ids, index, message=message)
    state["phase"] = Phase.lesson
    state["test"] = None
    state["practice"] = TestState(question_ids=question_ids, index=index, practice=True)
    return state


def _no_attempt_state(message, intent):
    state = initial_state("clerk")
    state["phase"] = Phase.test
    state["messages"] = [HumanMessage(message)]
    state["turn"] = TurnScratch(intent=intent)
    state["pending_prompt"] = t("de", "step_prompt")
    state["last_hint"] = InputHint(kind="confirm", label=t("de", "continue_label"))
    return state


def _quit_state(message, pending_quit):
    state = _attempt_state(["q-01-01", "q-02-04"])
    state["messages"] = [HumanMessage(message)]
    state["pending_quit"] = pending_quit
    state["turn"] = TurnScratch(intent=Intent.quit_test)
    return state


def _finish_state(correct_flags):
    from app.graph.state import GradedAnswer, TestState

    question_ids = [f"q-01-{n:02d}" for n in range(1, 11)]
    answers = [
        GradedAnswer(question_id=qid, answer="x", correct=correct)
        for qid, correct in zip(question_ids, correct_flags, strict=True)
    ]
    state = initial_state("clerk")
    state["phase"] = Phase.test
    state["messages"] = [HumanMessage("yes")]
    state["user_id"] = 7
    state["test"] = TestState(question_ids=question_ids, index=10, answers=answers)
    return state


def test_a_correct_yes_no_answer_advances_with_confetti_and_a_happy_streak(make_deps):
    deps = make_deps(script={})
    pool = deps.locale_content("de").questions
    state = _attempt_state(["q-01-01", "q-02-04"])
    result = grade_node(deps)(state)
    first, second = pool["q-01-01"], pool["q-02-04"]
    assert result["test"].index == 1
    assert result["test"].current_tries == 1
    assert result["test"].answers[0].correct is True
    assert result["streak"] == 1
    assert result["mood"] == "happy"
    assert [event.name for event in result["turn"].ui_events] == ["answer_result", "confetti"]
    assert result["turn"].ui_events[0].payload == {"verdict": "correct", "settled": True}
    card = result["turn"].parts[0]
    assert card.question == first.question
    assert card.model_answer == first.model_answer
    assert card.explanation == first.explanation
    assert [citation.ref for citation in card.citations] == ["Art. 4(1)", "Q&A 14"]
    assert card.correct is True
    lead = t("de", "next_question_lead", n=2, total=2)
    # A pick settles on curated text: the persona's own verdict line, then the next
    # question, with no persona rewrite (D130).
    lines = deps.persona("clerk").verdicts["right"]
    assert any(
        result["turn"].draft == f"{line}\n\n{lead}\n\n{second.question}" for line in lines
    ), result["turn"].draft
    assert result["turn"].voiced is True
    assert result["turn"].input_hint == hint_for_question(second)
    assert result["turn"].context_question == "q-02-04"
    assert result["turn"].closing_line == lead
    assert result["pending_prompt"] == second.question
    assert deps.models["fast"].calls == []
    assert deps.models["strong"].calls == []


def test_a_wrong_multiple_choice_answer_keeps_the_question_open_and_resets_the_streak(
    make_deps,
):
    deps = make_deps(script={})
    state = _attempt_state(["q-01-03", "q-01-01"], message="a")
    state["streak"] = 3
    result = grade_node(deps)(state)
    assert result["test"].index == 0
    assert result["test"].answers == []
    assert result["streak"] == 0
    assert result["mood"] is Mood.disappointed
    assert result["turn"].ui_events[-1].payload == {"verdict": "wrong", "settled": False}
    assert not any(part.kind == "card" for part in result["turn"].parts)
    assert result["turn"].input_hint.kind == "choices"
    assert result["turn"].input_hint.correct_key is None
    assert deps.models["fast"].calls == []


def test_streak_counts_consecutive_correct_and_resets(make_deps):
    deps = make_deps(
        script={
            "reply": "Noch nicht ganz. Lies die Optionen noch einmal.",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _attempt_state(["q-01-01", "q-01-02", "q-01-03"], message="yes")
    first = grade_node(deps)(state)
    assert first["streak"] == 1
    assert first["mood"] == "happy"
    second = grade_node(deps)({**state, **first, "messages": [HumanMessage("no")]})
    assert second["streak"] == 2
    assert second["mood"] == "happy"
    third = grade_node(deps)({**state, **first, **second, "messages": [HumanMessage("a")]})
    assert third["streak"] == 0
    assert third["mood"] is Mood.disappointed
    # A wrong pick no longer settles the question, but it still breaks the streak.
    assert third["test"].index == 2


def test_skip_resets_streak(make_deps):
    deps = make_deps(script={})
    state = _attempt_state(["q-01-01", "q-02-04"], message="yes")
    correct = grade_node(deps)(state)
    assert correct["streak"] == 1
    skipped = skip_node(deps)({**state, **correct})
    assert skipped["streak"] == 0
    assert skipped["mood"] == "disappointed"


def test_an_unresolved_yes_no_reply_is_no_attempt_and_the_question_stays_open(make_deps):
    deps = make_deps(
        script={
            "prose": ProseChoice(answer="unclear"),
            "reply": "Die Frage will ein Ja oder ein Nein.\n\nWie entscheidest du?",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _attempt_state(["q-01-01", "q-02-04"], message="Jein")
    result = grade_node(deps)(state)
    assert result["test"].index == 0
    assert result["test"].current_tries == 1
    assert result["test"].answers == []
    assert "Outcome: not_an_attempt." in result["turn"].brief
    assert result["turn"].input_hint.kind == "yes_no"
    assert deps.models["fast"].calls == ["prose", "reply", "critic"]


def test_a_wrong_first_test_answer_gets_a_written_retry(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, matched=[1], missing=[2]),
            "reply": "Noch nicht ganz: 1 von 2 Punkten. Noch einmal, was fehlt?",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _attempt_state(["q-02-04", "q-01-01"], message="Ist doch erlaubt.")
    state["test"] = state["test"].model_copy(update={"prior_matched": [MUST_ALLOWED]})
    result = grade_node(deps)(state)
    assert result["test"].current_tries == 2
    assert result["test"].index == 0
    assert result["test"].prior_matched == [MUST_ALLOWED]
    assert result["turn"].ui_events[-1].payload == {"verdict": "wrong", "settled": False}
    assert "Outcome: test_retry." in result["turn"].brief
    assert f"Missing:\n2. {MUST_COMPETENCE}" in result["turn"].brief
    assert result["turn"].draft.startswith("Noch nicht ganz")
    assert result["turn"].context_question == "q-02-04"
    assert result["pending_prompt"] == ASK_COMPETENCE
    assert "This is the test" in deps.models["strong"].prompts[-2]
    assert deps.models["strong"].calls == ["grade", "reply", "critic"]


def test_a_question_during_the_test_is_written_and_gated(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, attempt=False, matched=[], missing=[1, 2]),
            "reply": "Betreiber ist, wer das System einsetzt.\n\nUnd deine Antwort?",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _attempt_state(["q-02-04", "q-01-01"], message="Was ist ein Betreiber?")
    result = grade_node(deps)(state)
    assert "Outcome: not_an_attempt." in result["turn"].brief
    assert result["test"].current_tries == 1
    assert result["test"].answers == []
    assert not any(e.name == "answer_result" for e in result["turn"].ui_events)
    assert deps.models["strong"].calls == ["grade", "reply", "critic"]


def test_a_non_attempt_never_credits_a_point_the_grader_saw_in_it(make_deps):
    # "Stimmt es, dass das erlaubt ist?" names a point without earning it: the open points
    # and what the writer hears as met come from the earlier tries alone.
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, attempt=False, matched=[1], missing=[2]),
            "reply": "Das klärt sich gleich.\n\nWie lautet deine Antwort?",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _attempt_state(["q-02-04", "q-01-01"], message="Stimmt es, dass das erlaubt ist?")
    result = grade_node(deps)(state)
    assert "Outcome: not_an_attempt." in result["turn"].brief
    assert f"Missing:\n1. {MUST_ALLOWED}\n2. {MUST_COMPETENCE}" in result["turn"].brief
    assert result["test"].prior_matched == []
    assert "Met:\n- nothing yet" in deps.models["strong"].prompts[1]


def test_a_right_practice_reply_loses_its_inline_citations_in_the_bubble(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=True, matched=[1, 2]),
            "reply": "Genau, erlaubt (Art. 4 Abs. 1).\n\nFundstellen: Art. 4 Abs. 1",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _practice_state(["q-02-04"], 0, message="Erlaubt, und ich lese es.")
    result = grade_node(deps)(state)
    assert result["turn"].draft == "Genau, erlaubt."


def test_a_correct_test_answer_settles_with_the_card_and_no_writer(make_deps):
    deps = make_deps(script={"grade": Verdict(correct=True, matched=[1, 2])})
    state = _attempt_state(["q-02-04", "q-01-01"], message="Erlaubt, und ich prüfe.")
    result = grade_node(deps)(state)
    assert type(result["turn"].parts[0]).__name__ == "ModelAnswerCard"
    assert result["turn"].brief == ""
    assert deps.models["strong"].calls == ["grade"]


def test_a_wrong_first_free_text_try_keeps_its_met_points_for_the_retry(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, matched=[1], missing=[2]),
            "reply": "Noch nicht ganz: 1 von 2 Punkten. Noch einmal, was fehlt?",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _attempt_state(["q-02-04", "q-01-01"], message="Erlaubt.")
    result = grade_node(deps)(state)
    assert result["test"].current_tries == 1
    assert result["test"].prior_matched == [MUST_ALLOWED]
    assert result["turn"].ui_events[-1].payload == {"verdict": "correct", "settled": False}
    assert result["streak"] == 0
    assert result["mood"] is Mood.happy
    assert result["pending_prompt"] == ASK_COMPETENCE
    assert "Outcome: partial." in result["turn"].brief


def test_a_retry_merges_the_points_the_first_try_already_met(make_deps):
    # The follow-up asked only for the why; its answer is graded against the whole
    # rubric and misses the who it was never asked to restate.
    deps = make_deps(script={"grade": Verdict(correct=False, matched=[2], missing=[1])})
    state = _attempt_state(
        ["q-02-04", "q-01-01"],
        current_tries=2,
        message="Ich pruefe die Ausgabe, wie es meine Aufgabe ist.",
    )
    state["test"] = state["test"].model_copy(update={"prior_matched": [MUST_ALLOWED]})
    result = grade_node(deps)(state)
    answer = result["test"].answers[0]
    assert answer.correct is True
    assert answer.matched == [MUST_ALLOWED, MUST_COMPETENCE]
    assert answer.missing == []


def test_a_practice_retry_that_closes_the_gap_celebrates(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, matched=[2], missing=[1]),
            "reply": "Genau, das darfst du. Den Entwurf liest du vorher noch einmal.",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _practice_state(["q-02-04"], 0, message="Ich pruefe die Ausgabe.")
    state["practice"] = state["practice"].model_copy(
        update={"current_tries": 2, "prior_matched": [MUST_ALLOWED]}
    )
    result = grade_node(deps)(state)
    # The practice attempt clears as the chapter goes on; the verdict lives on the
    # event and the mood.
    events = result["turn"].ui_events
    assert [event.name for event in events] == ["answer_result", "confetti"]
    assert events[0].payload == {"verdict": "correct", "settled": True}
    assert result["mood"] is Mood.happy
    assert "Outcome: right." in result["turn"].brief
    assert "Missing:\n- nothing" in result["turn"].brief
    assert result["practice"] is None
    assert [type(p).__name__ for p in result["turn"].parts] == ["CitationPart"] * len(
        result["turn"].parts
    )
    assert deps.models["strong"].calls == ["grade", "reply", "critic"]


def test_a_retry_that_matches_nothing_new_stays_open(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, matched=[], missing=[2]),
            "reply": "Noch nicht ganz.",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _attempt_state(["q-02-04", "q-01-01"], current_tries=2, message="Keine Ahnung.")
    state["test"] = state["test"].model_copy(update={"prior_matched": [MUST_ALLOWED]})
    result = grade_node(deps)(state)
    assert result["test"].index == 0
    assert result["test"].answers == []
    assert result["test"].prior_matched == [MUST_ALLOWED]


def test_two_green_tries_settle_a_two_point_question_as_won(make_deps):
    deps = make_deps(script={"grade": Verdict(correct=False, matched=[2], missing=[1])})
    state = _attempt_state(["q-02-04", "q-01-01"], message="Ich prüfe den Entwurf.")
    state["streak"] = 2
    state["test"] = state["test"].model_copy(update={"prior_matched": [MUST_ALLOWED]})
    result = grade_node(deps)(state)
    answer = result["test"].answers[0]
    assert answer.correct is True
    assert answer.tries == 1
    assert answer.hint_shown is False
    assert result["streak"] == 3
    assert [event.name for event in result["turn"].ui_events] == ["answer_result", "confetti"]
    assert result["turn"].ui_events[0].payload == {"verdict": "correct", "settled": True}


def test_one_try_that_covers_both_points_settles_at_once(make_deps):
    deps = make_deps(script={"grade": Verdict(correct=True, matched=[1, 2])})
    state = _attempt_state(["q-02-04", "q-01-01"], message="Erlaubt, ich prüfe nur nach.")
    result = grade_node(deps)(state)
    assert result["test"].answers[0].correct is True
    assert result["test"].answers[0].tries == 1
    assert result["turn"].ui_events[0].payload == {"verdict": "correct", "settled": True}


def test_a_green_try_that_skips_a_point_asks_for_the_first_unmet_one(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, matched=[2], missing=[1]),
            "reply": f"Stimmt, prüfen musst du. {ASK_ALLOWED}",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _practice_state(["q-02-04"], 0, message="Ich prüfe den Entwurf.")
    state["streak"] = 2
    result = grade_node(deps)(state)
    assert result["practice"].current_tries == 1
    assert result["practice"].prior_matched == [MUST_COMPETENCE]
    assert result["streak"] == 2
    assert result["pending_prompt"] == ASK_ALLOWED
    assert f"Ask now: {ASK_ALLOWED}" in result["turn"].brief
    assert result["turn"].ui_events[0].payload == {"verdict": "correct", "settled": False}


def _on_track():
    return Verdict(correct=False, matched=[], missing=[1, 2], on_track=True)


def test_an_on_track_try_is_orange_and_uses_no_try(make_deps):
    deps = make_deps(
        script={
            "grade": _on_track(),
            "reply": f"Du bist auf dem richtigen Weg. {ASK_ALLOWED}",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _practice_state(["q-02-04"], 0, message="Kommt drauf an, was in der Mail steht.")
    state["streak"] = 2
    result = grade_node(deps)(state)
    assert result["practice"].current_tries == 1
    assert result["practice"].nudges == 1
    assert result["practice"].prior_matched == []
    assert result["streak"] == 2
    assert result["mood"] is Mood.neutral
    assert result["pending_prompt"] == ASK_ALLOWED
    assert "Outcome: on_track." in result["turn"].brief
    assert "Try 1 of 5." in result["turn"].brief
    assert "reply on this point" not in result["turn"].brief
    assert result["turn"].ui_events[0].payload == {"verdict": "partial", "settled": False}


def test_the_reply_after_an_orange_is_the_second_on_the_point(make_deps):
    deps = make_deps(
        script={
            "grade": _on_track(),
            "reply": f"Fast. {ASK_ALLOWED}",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _practice_state(["q-02-04"], 0, message="Kommt drauf an, wer sie liest.")
    state["practice"] = state["practice"].model_copy(update={"nudges": 1})
    result = grade_node(deps)(state)
    assert "Try 1 of 5, second reply on this point." in result["turn"].brief
    assert result["practice"].nudges == 2


def test_an_orange_try_on_the_last_try_keeps_the_question_open(make_deps):
    deps = make_deps(
        script={
            "grade": _on_track(),
            "reply": f"Fast. {ASK_ALLOWED}",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _practice_state(["q-02-04"], 0, message="Kommt drauf an.")
    state["practice"] = state["practice"].model_copy(update={"current_tries": 5, "nudges": 3})
    result = grade_node(deps)(state)
    assert result["practice"] is not None
    assert result["practice"].current_tries == 5
    assert result["practice"].nudges == 4
    assert result["turn"].ui_events[0].payload == {"verdict": "partial", "settled": False}


def test_a_green_after_oranges_resets_the_nudges(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, matched=[1], missing=[2]),
            "reply": f"Richtig. {ASK_COMPETENCE}",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _practice_state(["q-02-04"], 0, message="Erlaubt.")
    state["practice"] = state["practice"].model_copy(update={"nudges": 2})
    result = grade_node(deps)(state)
    assert result["practice"].nudges == 0
    assert result["turn"].ui_events[0].payload == {"verdict": "correct", "settled": False}


def test_a_green_that_settles_after_an_orange_is_a_win(make_deps):
    deps = make_deps(script={"grade": Verdict(correct=False, matched=[1], missing=[2])})
    state = _attempt_state(["q-02-04", "q-01-01"], message="Erlaubt.")
    state["test"] = state["test"].model_copy(
        update={"nudges": 1, "prior_matched": [MUST_COMPETENCE]}
    )
    result = grade_node(deps)(state)
    answer = result["test"].answers[0]
    assert answer.correct is True
    assert answer.tries == 1
    assert answer.hint_shown is False
    assert "confetti" in [event.name for event in result["turn"].ui_events]
    assert result["test"].nudges == 0


def test_a_miss_after_an_orange_uses_one_try(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, matched=[], missing=[1, 2]),
            "reply": f"Nein. {ASK_ALLOWED}",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _practice_state(["q-02-04"], 0, message="Verboten.")
    state["practice"] = state["practice"].model_copy(update={"nudges": 1})
    result = grade_node(deps)(state)
    assert result["practice"].current_tries == 2
    assert result["practice"].nudges == 1
    assert result["turn"].ui_events[0].payload == {"verdict": "wrong", "settled": False}


def test_an_orange_in_the_test_gets_the_count_line_and_uses_no_try(make_deps):
    deps = make_deps(
        script={
            "grade": _on_track(),
            "reply": f"{t('de', 'test_count', met=0, total=2)}\n\n{ASK_ALLOWED}",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _attempt_state(["q-02-04", "q-01-01"], message="Kommt drauf an.")
    result = grade_node(deps)(state)
    assert result["test"].current_tries == 1
    assert result["test"].nudges == 1
    assert "Outcome: test_retry." in result["turn"].brief
    assert result["turn"].ui_events[0].payload == {"verdict": "partial", "settled": False}


def test_a_non_attempt_keeps_the_nudges(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, attempt=False, matched=[], missing=[1, 2]),
            "reply": f"Ein KI-System ist Software. {ASK_ALLOWED}",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _practice_state(["q-02-04"], 0, message="Was ist ein KI-System?")
    state["practice"] = state["practice"].model_copy(update={"nudges": 2})
    result = grade_node(deps)(state)
    assert result["practice"].nudges == 2
    assert [e.name for e in result["turn"].ui_events] == []


def test_a_choice_answer_is_never_orange(make_deps):
    deps = make_deps(
        script={
            "reply": "Noch nicht ganz. Lies die Optionen noch einmal.",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _attempt_state(["q-01-03", "q-01-01"], message="A")
    result = grade_node(deps)(state)
    assert result["turn"].ui_events[-1].payload["verdict"] in ("correct", "wrong")


MUST_SIGN = "nennt, dass es dabeistehen muss"
ASK_SIGN_WHY = "Das Marketing fragt, wer den Hinweis jetzt dazuschreiben muss. Was sagst du?"


def test_the_draw_is_mainly_free_text_and_keeps_its_spread(make_deps):
    deps = make_deps(script={})
    pool = deps.locale_content("de").questions
    drawn = draw_questions(pool, random.Random("seed:1"))
    types = [pool[q].type for q in drawn]
    assert len(drawn) == 10
    assert types.count("free_text") == 7
    assert types.count("yes_no") == 2
    assert types.count("multiple_choice") == 1


def test_skip_during_a_chained_why_records_the_missing_whys(make_deps):
    deps = make_deps(script={})
    state = _attempt_state(["q-01-13", "q-01-01"])
    state["test"] = state["test"].model_copy(update={"prior_matched": [MUST_SIGN]})
    state["turn"] = TurnScratch(intent=Intent.skip)
    result = skip_node(deps)(state)
    answer = result["test"].answers[0]
    assert answer.question_id == "q-01-13"
    assert answer.correct is False
    assert answer.missing == ["nennt, dass unser Unternehmen das dazuschreibt"]
    assert result["test"].index == 1


def test_a_wrong_pick_resolves_the_practice_question_and_teaches_on(make_deps):
    deps = make_deps(script={})
    pool = deps.locale_content("de").questions
    state = _practice_state(["q-01-13"], 0, message="no")
    result = grade_node(deps)(state)
    assert result["practice"] is None
    question = pool["q-01-13"]
    # The settle is curated (D125): the verdict line and the model answer, no model.
    assert result["turn"].draft == f"Leider nicht.\n\n{question.model_answer}"
    assert result["turn"].brief == ""
    events = result["turn"].ui_events
    assert [event.name for event in events] == ["answer_result"]
    assert events[0].payload == {"verdict": "wrong", "settled": True}
    assert result["mood"] is Mood.disappointed
    assert result["streak"] == 0
    assert deps.models["fast"].calls == []


def test_a_correct_pick_opens_the_typed_why(make_deps):
    deps = make_deps(script={})
    state = _practice_state(["q-01-13"], 0, message="yes")
    result = grade_node(deps)(state)
    assert result["practice"] is not None
    assert result["practice"].prior_matched == [MUST_SIGN]
    assert result["practice"].current_tries == 1
    turn = result["turn"]
    # The reply is curated: the persona's verdict line and the follow-up (D130).
    lines = deps.persona("clerk").verdicts["right"]
    assert any(turn.draft == f"{line}\n\n{ASK_SIGN_WHY}" for line in lines), turn.draft
    assert turn.voiced is True
    assert turn.brief == ""
    assert turn.input_hint.kind == "text"
    assert result["pending_prompt"] == ASK_SIGN_WHY
    assert [event.name for event in turn.ui_events] == ["answer_result"]
    assert turn.ui_events[0].payload == {"verdict": "correct", "settled": False}
    assert result["mood"] is Mood.happy
    assert deps.models["fast"].calls == []


def test_a_right_pick_with_a_reason_grades_the_reason_and_can_settle(make_deps):
    deps = make_deps(
        script={
            "prose": ProseChoice(answer="yes", reason=True),
            "grade": Verdict(correct=True, matched=[1, 2]),
        }
    )
    pool = deps.locale_content("de").questions
    state = _practice_state(["q-01-13"], 0, message="Ja, und wir schreiben es selbst dazu.")
    result = grade_node(deps)(state)
    # The reason counts: both points are met in one message and the question settles.
    assert result["practice"] is None
    assert result["turn"].draft == f"Richtig.\n\n{pool['q-01-13'].model_answer}"
    assert deps.models["fast"].calls == ["prose", "grade"]


def test_a_right_pick_with_a_reason_that_misses_asks_the_follow_up(make_deps):
    deps = make_deps(
        script={
            "prose": ProseChoice(answer="yes", reason=True),
            "grade": Verdict(correct=False, matched=[1], missing=[2]),
        }
    )
    state = _practice_state(["q-01-13"], 0, message="Ja, weil es schöner aussieht.")
    result = grade_node(deps)(state)
    assert result["practice"].prior_matched == [MUST_SIGN]
    assert result["turn"].draft.endswith(ASK_SIGN_WHY)
    assert result["turn"].voiced is True
    assert deps.models["fast"].calls == ["prose", "grade"]


def test_the_typed_why_grades_and_settles(make_deps):
    deps = make_deps(script={"grade": Verdict(correct=True, matched=[2])})
    pool = deps.locale_content("de").questions
    state = _practice_state(["q-01-13"], 0, message="Wir schreiben es selbst dazu.")
    state["practice"] = state["practice"].model_copy(update={"prior_matched": [MUST_SIGN]})
    result = grade_node(deps)(state)
    assert result["practice"] is None
    question = pool["q-01-13"]
    # A closed question settles on curated text even when the last answer was typed (D125).
    assert result["turn"].draft == f"Richtig.\n\n{question.model_answer}"
    events = result["turn"].ui_events
    assert [event.name for event in events] == ["answer_result", "confetti"]
    assert events[0].payload == {"verdict": "correct", "settled": True}
    assert result["mood"] is Mood.happy
    assert result["streak"] == 1
    assert deps.models["fast"].calls == ["grade"]


def test_a_typed_answer_while_the_grid_is_open_still_reads_as_a_pick(make_deps):
    deps = make_deps(script={"prose": ProseChoice(answer="no")})
    state = _practice_state(["q-01-13"], 0, message="Da muss nichts dabeistehen")
    result = grade_node(deps)(state)
    assert result["practice"] is None
    events = result["turn"].ui_events
    assert events[0].payload == {"verdict": "wrong", "settled": True}
    assert deps.models["fast"].calls == ["prose"]


def test_a_try_that_meets_only_an_optional_point_is_a_miss(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, matched=[3], missing=[1, 2]),
            "reply": f"Das stimmt zwar, aber es geht um etwas anderes. {ASK_ALLOWED}",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _practice_state(["q-02-04"], 0, message="Eine Genehmigung braucht es nicht.")
    state["streak"] = 2
    result = grade_node(deps)(state)
    assert result["practice"].current_tries == 2
    assert result["streak"] == 0
    assert result["mood"] is Mood.disappointed
    assert result["turn"].ui_events[0].payload == {"verdict": "wrong", "settled": False}
    assert "Outcome: wrong." in result["turn"].brief


def test_the_test_brief_has_no_try_limit(make_deps):
    deps = make_deps(script={})
    question = deps.locale_content("de").questions["q-02-04"]
    graded = GradedAnswer(
        question_id="q-02-04",
        answer="Keine Ahnung.",
        correct=False,
        matched=[],
        missing=[question.rubric.must_texts[0]],
    )
    state = _attempt_state(["q-02-04", "q-01-01"], current_tries=3, message="Keine Ahnung.")
    brief = build_brief(deps, state, "test_retry", question, graded, tries=3)
    assert "Try 3." in brief.verdict
    assert "Try 3 of" not in brief.verdict
    assert "No hint of any kind" not in brief.job


def test_a_test_question_survives_any_number_of_misses(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, matched=[], missing=[1, 2]),
            "reply": "Noch nicht ganz. Ein Hinweis, dann noch einmal.",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _attempt_state(["q-02-04", "q-01-01"], current_tries=7, message="Keine Ahnung.")
    result = grade_node(deps)(state)
    assert result["test"] is not None
    assert result["test"].index == 0
    assert result["test"].answers == []
    assert not any(part.kind == "card" for part in result["turn"].parts)
    assert result["turn"].input_hint.kind == "text"
    assert result["test"].current_tries == 8


def test_a_wrong_closed_pick_in_the_test_re_offers_the_grid(make_deps):
    deps = make_deps(script={})
    pool = deps.locale_content("de").questions
    state = _attempt_state(["q-01-13", "q-01-01"], message="no")
    result = grade_node(deps)(state)
    assert result["test"].index == 0
    assert result["test"].answers == []
    assert result["test"].current_tries == 2
    assert not any(part.kind == "card" for part in result["turn"].parts)
    # A wrong pick in the test is curated too: the verdict line and the question again,
    # with its buttons (D130).
    lines = deps.persona("clerk").verdicts["wrong"]
    question = pool["q-01-13"].question
    assert any(result["turn"].draft == f"{line}\n\n{question}" for line in lines)
    assert result["turn"].voiced is True
    assert result["turn"].input_hint.kind == "yes_no"
    assert result["turn"].input_hint.correct_key is None
    assert result["turn"].ui_events[-1].payload == {"verdict": "wrong", "settled": False}
    assert result["mood"] is Mood.disappointed
    assert deps.models["fast"].calls == []


def test_the_second_miss_in_the_test_keeps_the_question_open(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, matched=[], missing=[1, 2]),
            "reply": "Noch nicht ganz. Einer fehlt noch.",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _attempt_state(["q-02-04", "q-01-01"], current_tries=2, message="Keine Ahnung.")
    result = grade_node(deps)(state)
    assert result["test"].index == 0
    assert result["test"].current_tries == 3
    assert result["turn"].ui_events[-1].payload == {"verdict": "wrong", "settled": False}


def test_a_non_attempt_after_a_green_keeps_the_met_points(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, attempt=False, matched=[], missing=[2]),
            "reply": (
                f"Ein KI-System ist Software, die aus Eingaben Ausgaben ableitet. {ASK_COMPETENCE}"
            ),
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _practice_state(["q-02-04"], 0, message="Was ist ein KI-System?")
    state["practice"] = state["practice"].model_copy(update={"prior_matched": [MUST_ALLOWED]})
    result = grade_node(deps)(state)
    assert result["practice"].current_tries == 1
    assert result["practice"].prior_matched == [MUST_ALLOWED]
    assert result["pending_prompt"] == ASK_COMPETENCE
    assert [event.name for event in result["turn"].ui_events] == []


def test_the_pending_prompt_is_the_ask_of_the_turn(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, matched=[], missing=[1, 2]),
            "reply": f"Noch nicht. {ASK_ALLOWED}",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _practice_state(["q-02-04"], 0, message="Verboten.")
    result = grade_node(deps)(state)
    assert result["pending_prompt"] == ASK_ALLOWED


def test_the_test_count_line_ends_on_the_ask_when_a_hint_leaked(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, matched=[1], missing=[2]),
            "reply": "Richtig. Du musst das Ergebnis prüfen, oder?",
            "critic": Critique(verdict="retry", score=1, faults=["leak"], credited=[2]),
        }
    )
    state = _attempt_state(["q-02-04", "q-01-01"], message="Erlaubt.")
    result = grade_node(deps)(state)
    draft = result["turn"].draft
    assert draft.endswith(ASK_COMPETENCE)
    assert t("de", "test_count", met=1, total=2) in draft


LEAKING_DRAFT = (
    "Richtig, erlaubt ist das. Du musst das Ergebnis prüfen. Wie könntest du sicherstellen, "
    f"dass der Entwurf stimmt? {ASK_COMPETENCE}"
)


def _spent_practice(make_deps, critique):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, matched=[1], missing=[2]),
            "reply": LEAKING_DRAFT,
            "critic": critique,
        }
    )
    return grade_node(deps)(_practice_state(["q-02-04"], 0, message="Erlaubt."))


def test_a_spent_practice_budget_with_a_leak_ships_the_ask_alone(make_deps):
    result = _spent_practice(
        make_deps, Critique(verdict="retry", score=1, faults=["leak"], credited=[2])
    )
    assert result["turn"].draft == ASK_COMPETENCE
    assert result["turn"].ui_events[0].payload == {"verdict": "correct", "settled": False}


def test_a_spent_practice_budget_with_a_second_question_ships_the_ask_alone(make_deps):
    result = _spent_practice(make_deps, Critique(verdict="retry", score=1, faults=["question"]))
    assert result["turn"].draft == ASK_COMPETENCE
    assert result["turn"].ui_events[0].payload == {"verdict": "correct", "settled": False}


def test_a_spent_practice_budget_without_leak_or_question_ships_the_best_draft(make_deps):
    result = _spent_practice(make_deps, Critique(verdict="retry", score=1, faults=["repeat"]))
    assert result["turn"].draft == LEAKING_DRAFT


def test_a_spent_practice_budget_on_a_non_attempt_ships_the_best_draft(make_deps):
    draft = f"Ein KI-System ist Software. Willst du mehr wissen? {ASK_ALLOWED}"
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, attempt=False, matched=[], missing=[1, 2]),
            "reply": draft,
            "critic": Critique(verdict="retry", score=1, faults=["question"]),
        }
    )
    result = grade_node(deps)(_practice_state(["q-02-04"], 0, message="Was ist ein KI-System?"))
    assert result["turn"].draft == draft
    assert "answer_result" not in [event.name for event in result["turn"].ui_events]


def test_a_spent_practice_budget_on_a_non_attempt_never_ships_a_leak(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, attempt=False, matched=[], missing=[1, 2]),
            "reply": f"Ein KI-System ist Software. Und: {MUST_ALLOWED_HINT}. {ASK_ALLOWED}",
            "critic": Critique(verdict="retry", score=1, faults=["leak"], credited=[1]),
        }
    )
    result = grade_node(deps)(_practice_state(["q-02-04"], 0, message="Was ist ein KI-System?"))
    assert result["turn"].draft == ASK_ALLOWED
    assert "answer_result" not in [event.name for event in result["turn"].ui_events]


def test_the_second_free_text_try_carries_hint_shown_and_tries_two(make_deps):
    # A second-try correct answer is settled, not won (Jo 4): the streak (0, from
    # _attempt_state) neither rises nor resets, and there is no confetti.
    deps = make_deps(script={"grade": Verdict(correct=True, matched=[1, 2])})
    state = _attempt_state(
        ["q-02-04", "q-01-01"], current_tries=2, message="Erlaubt, ohne Genehmigung, mit Prüfen."
    )
    result = grade_node(deps)(state)
    answer = result["test"].answers[0]
    assert answer.question_id == "q-02-04"
    assert answer.correct is True
    assert answer.hint_shown is True
    assert answer.tries == 2
    assert result["test"].index == 1
    assert result["streak"] == 0
    assert [event.name for event in result["turn"].ui_events] == ["answer_result"]
    assert result["turn"].parts[0].tries == 2
    assert deps.models["strong"].calls == ["grade"]


def test_skipping_a_free_text_question_records_the_rubric_musts_and_advances(make_deps):
    deps = make_deps(script={})
    pool = deps.locale_content("de").questions
    state = _attempt_state(["q-02-04", "q-01-01"])
    state["turn"] = TurnScratch(intent=Intent.skip)
    result = skip_node(deps)(state)
    answer = result["test"].answers[0]
    assert answer.question_id == "q-02-04"
    assert answer.answer == ""
    assert answer.correct is False
    assert answer.missing == [MUST_ALLOWED, MUST_COMPETENCE]
    assert answer.tries == 1
    assert answer.hint_shown is False
    assert result["test"].index == 1
    assert result["streak"] == 0
    assert [event.name for event in result["turn"].ui_events] == ["answer_result"]
    assert result["turn"].parts[0].correct is False
    second = pool["q-01-01"]
    assert result["turn"].draft == (
        f"{t('de', 'next_question_lead', n=2, total=2)}\n\n{second.question}"
    )
    assert deps.models["strong"].calls == []


def test_skipping_a_choice_question_records_no_missing_points(make_deps):
    deps = make_deps(script={})
    state = _attempt_state(["q-01-03", "q-01-01"])
    state["turn"] = TurnScratch(intent=Intent.skip)
    result = skip_node(deps)(state)
    assert result["test"].answers[0].missing == []
    assert result["test"].answers[0].correct is False
    assert result["test"].index == 1


def _start_request_state(message="Ich will direkt den Test machen.", pending=False):
    state = initial_state("clerk")
    state["phase"] = Phase.lesson
    state["step_idx"] = 1
    state["messages"] = [HumanMessage(message)]
    state["turn"] = TurnScratch(intent=Intent.start_test)
    state["pending_start_test"] = pending
    state["pending_prompt"] = t("de", "step_prompt")
    return state


def test_a_test_request_from_a_lesson_asks_first_and_starts_nothing(make_deps):
    deps = make_deps(script={})
    result = start_test_node(deps)(_start_request_state())
    assert result["pending_start_test"] is True
    assert result["turn"].draft == t("de", "test_confirm", chapters=8, total=10, threshold=8)
    assert result["turn"].input_hint == InputHint(kind="yes_no")
    assert "test" not in result
    assert "phase" not in result
    assert "pending_prompt" not in result
    assert deps.models["fast"].calls == []


def test_yes_after_the_question_starts_the_graded_test(make_deps):
    deps = make_deps(script={})
    result = start_test_node(deps)(_start_request_state("yes", pending=True))
    assert result["pending_start_test"] is False
    assert result["phase"] is Phase.test
    assert result["attempts"] == 1
    assert len(result["test"].question_ids) == 10
    assert result["turn"].draft.startswith(t("de", "test_intro", total=10, threshold=8))


def test_no_after_the_question_keeps_the_lesson_step_and_its_weiter_hint(make_deps):
    deps = make_deps(script={})
    result = start_test_node(deps)(_start_request_state("no", pending=True))
    assert result["pending_start_test"] is False
    assert "test" not in result
    assert "phase" not in result
    assert result["turn"].draft == t("de", "test_declined")
    assert result["turn"].closing_line == t("de", "step_prompt")
    assert result["turn"].input_hint == InputHint(kind="confirm", label=t("de", "continue_label"))


def test_an_unclear_reply_to_the_question_keeps_the_lesson_step(make_deps):
    deps = make_deps(script={"prose": ProseChoice(answer="unclear")})
    result = start_test_node(deps)(_start_request_state("Hmm, weiß nicht", pending=True))
    assert deps.models["fast"].calls == ["prose"]
    assert result["pending_start_test"] is False
    assert "test" not in result
    assert result["turn"].draft == t("de", "test_declined")


def test_a_test_request_at_the_course_end_starts_without_asking_again(make_deps):
    deps = make_deps(script={})
    state = _start_request_state("Start")
    state["phase"] = Phase.free
    state["pending_prompt"] = t("de", "recommend_test")
    result = start_test_node(deps)(state)
    assert result["phase"] is Phase.test
    assert len(result["test"].question_ids) == 10


def test_the_first_quit_request_asks_for_confirmation_and_keeps_the_question(make_deps):
    deps = make_deps(script={})
    result = quit_test_node(deps)(_quit_state("Test abbrechen", pending_quit=False))
    assert result["pending_quit"] is True
    assert result["turn"].draft == t("de", "quit_confirm")
    assert result["turn"].input_hint == InputHint(kind="yes_no")
    assert "test" not in result
    assert "pending_prompt" not in result
    assert deps.models["strong"].calls == []


def test_confirming_the_quit_discards_the_test_and_returns_to_the_lesson_step(make_deps):
    deps = make_deps(script={})
    state = _quit_state("yes", pending_quit=True)
    state["streak"] = 4
    result = quit_test_node(deps)(state)
    assert result["test"] is None
    assert result["streak"] == 0
    assert result["pending_quit"] is False
    assert result["phase"] is Phase.lesson
    assert result["turn"].draft == t("de", "quit_to_lesson")
    assert result["turn"].closing_line == t("de", "step_prompt")
    assert result["turn"].input_hint == InputHint(kind="confirm", label=t("de", "continue_label"))
    assert result["pending_prompt"] == t("de", "step_prompt")


def test_confirming_the_quit_with_every_chapter_done_returns_to_free(make_deps, content):
    deps = make_deps(script={})
    state = _quit_state("yes", pending_quit=True)
    state["chapters_done"] = list(content.locales["de"].chapters)
    state["streak"] = 4
    result = quit_test_node(deps)(state)
    assert result["test"] is None
    assert result["streak"] == 0
    assert result["phase"] is Phase.free
    assert result["turn"].draft == t("de", "quit_done")
    assert result["pending_prompt"] == t("de", "recommend_test")


def test_quitting_the_test_restores_the_streak_from_before_it_started(make_deps):
    from app.graph.state import TestState

    deps = make_deps(script={})
    state = _start_request_state("yes", pending=True)
    state["streak"] = 7
    started = start_test_node(deps)(state)
    assert started["streak_before_test"] == 7
    state = {**state, **started, "test": TestState(question_ids=["q-01-01", "q-02-04"])}
    graded = grade_node(deps)({**state, "messages": [HumanMessage("yes")]})
    state = {**state, **graded}
    assert state["streak"] == 8
    result = quit_test_node(deps)(
        {**state, "messages": [HumanMessage("yes")], "pending_quit": True}
    )
    assert result["test"] is None
    assert result["streak"] == 7


def test_confirming_the_quit_during_a_practice_clears_the_practice_attempt(make_deps):
    deps = make_deps(script={})
    state = _practice_state(["q-01-01"], index=0)
    state["messages"] = [HumanMessage("yes")]
    state["pending_quit"] = True
    result = quit_test_node(deps)(state)
    assert result["practice"] is None
    assert result["phase"] is Phase.lesson
    assert result["turn"].draft == t("de", "quit_to_lesson")


def test_declining_the_quit_reasks_the_current_question(make_deps):
    deps = make_deps(script={})
    pool = deps.locale_content("de").questions
    question = pool["q-01-01"]
    result = quit_test_node(deps)(_quit_state("no", pending_quit=True))
    assert "test" not in result
    assert result["pending_quit"] is False
    assert result["turn"].draft == f"{t('de', 'quit_kept')}\n\n{question.question}"
    assert result["turn"].input_hint == hint_for_question(question)
    assert result["turn"].context_question == "q-01-01"
    assert result["pending_prompt"] == question.question


def test_declining_the_quit_after_a_wrong_pick_offers_the_grid_again(make_deps):
    deps = make_deps(script={})
    pool = deps.locale_content("de").questions
    state = _quit_state("no", pending_quit=True)
    state["test"] = state["test"].model_copy(
        update={"index": 0, "current_tries": 2, "prior_matched": []}
    )
    state["test"] = state["test"].model_copy(update={"question_ids": ["q-01-13", "q-01-01"]})
    result = quit_test_node(deps)(state)
    question = pool["q-01-13"]
    # The position is still open: the yes/no buttons come back, not the composer.
    assert result["turn"].draft == f"{t('de', 'quit_kept')}\n\n{question.question}"
    assert result["turn"].input_hint.kind == "yes_no"


def test_declining_the_quit_reasks_the_open_point_of_a_free_text_question(make_deps):
    deps = make_deps(script={})
    state = _quit_state("no", pending_quit=True)
    state["test"] = state["test"].model_copy(update={"index": 1, "prior_matched": [MUST_ALLOWED]})
    result = quit_test_node(deps)(state)
    assert result["turn"].draft == f"{t('de', 'quit_kept')}\n\n{ASK_COMPETENCE}"
    assert result["pending_prompt"] == ASK_COMPETENCE


def test_an_unclear_quit_reply_keeps_the_test_running(make_deps):
    deps = make_deps(script={"prose": ProseChoice(answer="unclear")})
    result = quit_test_node(deps)(_quit_state("Jein.", pending_quit=True))
    assert deps.models["fast"].calls == ["prose"]
    assert "test" not in result
    assert result["pending_quit"] is False
    assert result["turn"].draft.startswith(t("de", "quit_kept"))


def test_a_skip_with_no_attempt_open_says_so_instead_of_raising(make_deps):
    deps = make_deps(script={})
    result = skip_node(deps)(_no_attempt_state("weiter", Intent.skip))
    assert result["turn"].draft == t("de", "no_question_open")
    assert result["turn"].closing_line == t("de", "step_prompt")
    assert result["turn"].input_hint == InputHint(kind="confirm", label=t("de", "continue_label"))
    assert "test" not in result
    assert deps.models["strong"].calls == []


def test_a_quit_reply_with_no_attempt_open_says_so_instead_of_raising(make_deps):
    deps = make_deps(script={})
    state = _no_attempt_state("yes", Intent.quit_test)
    state["pending_quit"] = True
    result = quit_test_node(deps)(state)
    assert result["pending_quit"] is False
    assert result["turn"].draft == t("de", "no_question_open")
    assert result["turn"].closing_line == t("de", "step_prompt")
    assert "test" not in result
    assert deps.models["strong"].calls == []


def test_finishing_a_passed_test_records_the_completion_and_celebrates(make_deps):
    record = []
    deps = make_deps(script={}, record=record)
    flags = [False, True, True, True, True, False, True, True, True, True]
    result = finish_test_node(deps)(_finish_state(flags))
    assert len(record) == 1
    entry = record[0]
    assert entry.user_id == 7
    assert entry.course_version == "0.1.0"
    assert entry.law_version == "test"
    assert entry.locale == "de"
    assert entry.persona_id == "clerk"
    assert entry.passed_at is not None
    assert [event.name for event in result["turn"].ui_events] == ["test_result", "finale"]
    assert result["turn"].ui_events[0].payload == {"score": 8, "total": 10}
    assert result["turn"].draft == t("de", "finale", score=8, total=10)
    parts = [part for part in result["turn"].parts if isinstance(part, FilePart)]
    assert len(parts) == 1
    assert parts[0].title == t("de", "cheatsheet_full_title")
    assert parts[0].filename == "spickzettel-kurs.pdf"
    assert parts[0].url.startswith("/api/files/")
    assert result["phase"] is Phase.done
    assert result["mood"] == "happy"
    assert result["pending_prompt"] == t("de", "done_prompt")
    assert deps.models["strong"].calls == []


def test_a_passed_test_with_certificates_on_attaches_the_certificate(make_deps, settings):
    deps = make_deps(script={}, feature_certificate=True)
    result = finish_test_node(deps)(_finish_state([True] * 8 + [False] * 2))

    parts = [part for part in result["turn"].parts if isinstance(part, FilePart)]
    assert len(parts) == 2
    payload = read_file_token(settings, parts[1].url.removeprefix("/api/files/"))
    assert payload["kind"] == "certificate"
    assert payload["uid"] == 7
    assert payload["score"] == 8
    assert payload["total"] == 10
    assert payload["passed"] is True
    assert payload["locale"] == "de"
    assert payload["cv"] == "0.1.0"
    assert payload["lv"] == "test"
    assert len(payload["passed_on"]) == 10 and payload["passed_on"][4] == "-"


def test_a_passed_test_without_a_signed_in_user_records_no_completion(make_deps):
    record = []
    deps = make_deps(script={}, record=record, feature_certificate=True)
    state = _finish_state([True] * 8 + [False] * 2)
    state["user_id"] = None
    result = finish_test_node(deps)(state)
    assert record == []
    assert result["phase"] is Phase.done
    parts = [part for part in result["turn"].parts if isinstance(part, FilePart)]
    assert len(parts) == 1  # the full cheat only; no certificate without a user


def test_finishing_with_wrong_answers_still_completes_the_course(make_deps):
    record = []
    deps = make_deps(script={}, record=record)
    flags = [False, True, False, True, False, True, False, True, False, True]
    result = finish_test_node(deps)(_finish_state(flags))
    assert len(record) == 1
    assert result["turn"].ui_events[0].payload == {"score": 5, "total": 10}
    assert [event.name for event in result["turn"].ui_events] == ["test_result", "finale"]
    assert result["turn"].draft == t("de", "finale", score=5, total=10)
    assert result["phase"] is Phase.done
    assert result["mood"] is Mood.happy
    assert result["pending_prompt"] == t("de", "done_prompt")


def test_starting_the_test_abandons_a_live_practice_attempt(make_deps):
    from app.graph.state import TestState

    deps = make_deps(script={"grade": Verdict(correct=True, matched=[1])})
    pool = deps.locale_content("de").questions
    state = initial_state("clerk")
    state["phase"] = Phase.lesson
    state["messages"] = [HumanMessage("yes")]
    state["turn"] = TurnScratch(intent=Intent.start_test)
    state["practice"] = TestState(question_ids=["q-01-01", "q-02-04"], index=1, practice=True)
    state["pending_start_test"] = True
    result = start_test_node(deps)(state)
    assert result["practice"] is None
    assert result["pending_start_test"] is False
    assert result["phase"] is Phase.test
    assert result["attempts"] == 1
    expected_ids = draw_questions(pool, random.Random("seed:1"))
    assert result["test"].question_ids == expected_ids
    assert expected_ids[0] == "q-05-03"
    merged = {**state, **result, "messages": [HumanMessage("Erlaubt, und ich prüfe.")]}
    graded = grade_node(deps)(merged)
    assert "practice" not in graded
    assert graded["test"].index == 1
    assert graded["test"].answers[0].question_id == "q-05-03"
    assert graded["test"].answers[0].correct is True
    # The scripted strong and fast roles share one model: the grade call is the whole
    # traffic of the turn.
    assert deps.models["fast"].calls == ["grade"]


def test_the_verdict_payload_names_orange():
    assert verdict_payload(True, False) == {"verdict": "correct", "settled": False}
    assert verdict_payload(None, False) == {"verdict": "partial", "settled": False}
    assert verdict_payload(False, True) == {"verdict": "wrong", "settled": True}
    assert verdict_payload(True, True) == {"verdict": "correct", "settled": True}
    assert verdict_payload(False, False) == {"verdict": "wrong", "settled": False}


def test_a_chip_answer_settles_on_curated_text_with_no_model_call(make_deps):
    # The premade options have predetermined answers: the verdict line and the curated
    # model answer, no grader model, no writer, no critic (D127).
    deps = make_deps(script={})
    for question_id, message in (("q-01-03", "b"), ("q-01-01", "yes")):
        state = _practice_state([question_id], 0, message=message)
        result = grade_node(deps)(state)
        question = deps.question(question_id)
        right = (
            (message == question.correct)
            if question.type == "yes_no"
            else (message.upper() == question.correct)
        )
        line = "Richtig." if right else "Leider nicht."
        assert result["turn"].draft == f"{line}\n\n{question.model_answer}"
        assert result["practice"] is None
    assert deps.models["strong"].calls == []
    assert deps.models["fast"].calls == []


def test_a_wrong_chip_gets_the_wrong_line_and_the_model_answer(make_deps):
    deps = make_deps(script={})
    state = _practice_state(["q-01-03"], 0, message="a")
    result = grade_node(deps)(state)
    question = deps.question("q-01-03")
    assert result["turn"].draft == f"Leider nicht.\n\n{question.model_answer}"
    assert result["mood"] is Mood.disappointed
    assert deps.models["strong"].calls == []


def test_a_skipped_chip_question_answers_on_curated_text_too(make_deps):
    deps = make_deps(script={})
    state = _practice_state(["q-01-03"], 0, message="egal")
    result = skip_node(deps)(state)
    question = deps.question("q-01-03")
    assert result["turn"].draft == f"Leider nicht.\n\n{question.model_answer}"
    assert deps.models["strong"].calls == []


def test_a_partial_practice_answer_is_written_and_asked_on(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, matched=[2], missing=[1]),
            "reply": "Richtig, das Prüfen gehört dazu.\n\nAber darf man es denn überhaupt?",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _practice_state(["q-02-04"], 0, message="Ich pruefe die Ausgabe.")
    state["practice"] = state["practice"].model_copy(
        update={"current_tries": 3, "prior_matched": []}
    )
    result = grade_node(deps)(state)
    turn = result["turn"]
    assert turn.draft.startswith("Richtig, das Prüfen gehört dazu.")
    assert "Outcome: partial." in turn.brief
    assert f"Missing:\n1. {MUST_ALLOWED}" in turn.brief
    assert turn.input_hint.asks is True
    assert result["practice"].current_tries == 3
    assert result["practice"].prior_matched == [MUST_COMPETENCE]
    assert result["mood"] is Mood.happy
    assert result["streak"] == 0
    assert result["pending_prompt"] == ASK_ALLOWED
    events = turn.ui_events
    assert [event.name for event in events] == ["answer_result"]
    assert events[0].payload == {"verdict": "correct", "settled": False}
    assert deps.models["strong"].calls == ["grade", "reply", "critic"]


def test_a_wrong_practice_answer_with_tries_left_still_reports_its_verdict(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, matched=[], missing=[1, 2]),
            "reply": "Noch nicht ganz.\n\nWas sagt die Verordnung zum Entwerfen?",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _practice_state(["q-02-04"], 0, message="Das ist verboten.")
    state["streak"] = 2
    result = grade_node(deps)(state)
    assert result["practice"].current_tries == 2
    assert "Outcome: wrong." in result["turn"].brief
    assert result["mood"] is Mood.disappointed
    assert result["streak"] == 0
    events = result["turn"].ui_events
    assert [event.name for event in events] == ["answer_result"]
    assert events[0].payload == {"verdict": "wrong", "settled": False}


def test_a_non_attempt_counts_no_try_and_asks_again(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, attempt=False, matched=[], missing=[1, 2]),
            "reply": "Ein Betreiber setzt das System ein.\n\nUnd was sagst du deiner Kollegin?",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _practice_state(["q-02-04"], 0, message="Was ist ein Betreiber?")
    result = grade_node(deps)(state)
    turn = result["turn"]
    assert "Outcome: not_an_attempt." in turn.brief
    assert turn.draft.startswith("Ein Betreiber setzt das System ein.")
    assert result["practice"].current_tries == 1
    assert result["practice"].prior_matched == []
    assert result["mood"] is Mood.neutral
    assert not any(e.name == "answer_result" for e in turn.ui_events)
    assert turn.input_hint.asks is True
    assert turn.input_hint.kind == "text"
    assert result["pending_prompt"] == ASK_ALLOWED
    assert deps.models["strong"].calls == ["grade", "reply", "critic"]


def test_a_fifth_wrong_practice_try_hands_the_answer_over_and_closes(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, matched=[], missing=[1, 2]),
            "reply": "So ist es: erlaubt, und der Entwurf wird vor dem Absenden gelesen.",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    state = _practice_state(["q-02-04"], 0, message="Weiß ich nicht.")
    state["practice"] = state["practice"].model_copy(update={"current_tries": 5})
    result = grade_node(deps)(state)
    assert result["practice"] is None
    assert "Outcome: settled." in result["turn"].brief
    assert result["turn"].draft.startswith("So ist es")
    events = result["turn"].ui_events
    assert [event.name for event in events] == ["answer_result"]
    assert events[0].payload == {"verdict": "wrong", "settled": True}
    assert result["mood"] is Mood.disappointed
    assert "Outcome: settled" in deps.models["strong"].prompts[-1]
    assert deps.models["strong"].calls == ["grade", "reply", "critic"]


def test_a_test_retry_whose_budget_ends_on_a_leak_ships_the_count_line(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, matched=[1], missing=[2]),
            "reply": ["leak eins", "leak zwei", "leak drei"],
            "critic": [
                Critique(verdict="retry", faults=["leak"], notes="a", score=2),
                Critique(verdict="retry", faults=["leak"], notes="b", score=2),
                Critique(verdict="retry", faults=["leak"], notes="c", score=2),
            ],
        }
    )
    state = _attempt_state(["q-02-04", "q-01-01"], message="Ist doch erlaubt.")
    result = grade_node(deps)(state)
    count = t("de", "test_count", met=1, total=2)
    assert result["turn"].draft == f"{count}\n\n{ASK_COMPETENCE}"
    assert "leak" not in result["turn"].draft


def test_a_practice_reply_whose_budget_ends_ships_the_best_draft(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, matched=[1], missing=[2]),
            "reply": ["eins", "zwei", "drei"],
            "critic": [
                Critique(verdict="retry", faults=["leak"], notes="a", score=1),
                Critique(verdict="retry", faults=["unhelpful"], notes="b", score=3),
                Critique(verdict="retry", faults=["leak"], notes="c", score=2),
            ],
        }
    )
    state = _practice_state(["q-02-04"], 0, message="Ist doch erlaubt.")
    result = grade_node(deps)(state)
    assert result["turn"].draft == "zwei"


def test_a_test_non_attempt_whose_budget_ends_on_a_leak_ships_the_bare_ask(make_deps):
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, attempt=False, matched=[], missing=[1, 2]),
            "reply": ["leak eins", "leak zwei", "leak drei"],
            "critic": Critique(verdict="retry", faults=["leak"], notes="a", score=2),
        }
    )
    state = _attempt_state(["q-02-04", "q-01-01"], message="Was heißt Betreiber?")
    result = grade_node(deps)(state)
    assert result["turn"].draft == ASK_ALLOWED


def test_a_wrong_pick_in_the_test_keeps_the_grid_open(make_deps):
    deps = make_deps(script={"prose": ProseChoice(answer="A")})
    state = _attempt_state(["q-02-03", "q-01-01"], current_tries=1, message="Ich nehme Option A.")
    result = grade_node(deps)(state)
    assert result["test"] is not None
    # A wrong pick in the test is not coached, it keeps the grid and uses a try (D127, D128).
    assert result["test"].current_tries == 2
    hint = result["turn"].input_hint
    assert hint.kind == "choices"
    assert hint.correct_key is None
