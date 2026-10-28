import asyncio
import sqlite3

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.graph.checkpointer import _postgres_conn_string, open_checkpointer
from app.graph.critic import Critique
from app.graph.deps import CompletionRecord
from app.graph.grade import ProseChoice, Verdict
from app.graph.graph import build_graph
from app.graph.routing import route_after_triage
from app.graph.state import (
    ChapterStartPart,
    InputHint,
    ModelAnswerCard,
    Mood,
    Phase,
    SessionState,
    TurnScratch,
    initial_state,
)
from app.graph.triage import Triage
from app.i18n import t
from app.settings import Settings
from tests.graph.test_draw_start import FROZEN_SEED_1

CHAPTER = "01-warum-es-dich-betrifft"
COACH_LEAKY = "Sag ihr: Das ist erlaubte Nutzung ohne Genehmigung, nur KI-Kompetenz. Klar?"
COACH_CLEAN = "Frag sie: was verlangt die Verordnung, wenn eine Nutzung erlaubt ist?"
RETRY_REPLY = "Noch nicht ganz: 1 von 2 Punkten. Noch einmal, worauf kommt es an?"
PRACTICE_REPLY = "Genau, das darfst du. Den Entwurf liest du vorher noch einmal."
SHIP = Critique(verdict="ship", score=5)


def _ok(intent: str = "continue") -> Triage:
    return Triage(guard="ok", intent=intent)


def _base(**over) -> SessionState:
    state = initial_state("clerk")
    state.update(over)
    return state


def _lesson() -> SessionState:
    return _base(phase=Phase.lesson, step_idx=1)


def _practice() -> SessionState:
    from app.graph.state import TestState

    return _base(
        phase=Phase.lesson,
        step_idx=6,
        practice=TestState(question_ids=["q-02-04"], practice=True),
    )


def _free() -> SessionState:
    return _base(phase=Phase.free, chapters_done=[CHAPTER])


def _test() -> SessionState:
    from app.graph.state import TestState

    return _base(
        phase=Phase.test,
        attempts=1,
        test=TestState(question_ids=["q-02-04", "q-01-01"]),
        pending_prompt="Frage 1 von 2",
    )


def _say(graph, state: SessionState, message: str, thread: str = "t"):
    return graph.invoke(
        dict(state) | {"messages": [HumanMessage(message)]},
        {"configurable": {"thread_id": thread}},
    )


def _last_text(result) -> str:
    message = result["messages"][-1]
    assert isinstance(message, AIMessage)
    return str(message.content)


def test_every_phase_and_intent_reaches_its_node(make_deps, make_graph):
    cases = [
        (
            "a lesson continue walks the next step",
            _lesson(),
            "weiter",
            _ok(),
            {},
            ["triage", "persona", "voice_critic"],
        ),
        (
            "a lesson question reaches the answer agent",
            _lesson(),
            "Was ist Art. 3?",
            _ok("question"),
            {"free_question": "Art. 3(1) definiert das KI-System."},
            ["triage", "free_question", "critic", "persona", "voice_critic"],
        ),
        (
            # The answer settles the chapter's last case: the chapter end is curated.
            "a practice answer is graded in the lesson",
            _practice(),
            "Erlaubt, mit Prüfen.",
            _ok("answer"),
            {"grade": Verdict(correct=True), "reply": PRACTICE_REPLY},
            ["triage", "grade", "reply", "critic"],
        ),
        (
            "a free continue starts the test",
            _free(),
            "start",
            _ok("start_test"),
            {},
            ["triage", "persona", "voice_critic"],
        ),
        (
            "a test question is written and gated",
            _test(),
            "Wie soll ich antworten?",
            _ok("question"),
            {
                "grade": Verdict(correct=False, attempt=False, missing=[1, 2]),
                "reply": COACH_CLEAN,
            },
            ["triage", "grade", "reply", "critic", "persona", "voice_critic"],
        ),
        (
            "a test answer is graded",
            _test(),
            "Erlaubt, mit Prüfen.",
            _ok("answer"),
            {"grade": Verdict(correct=True)},
            ["triage", "grade", "persona", "voice_critic"],
        ),
        (
            "a test skip advances without a model",
            _test(),
            "überspringen",
            _ok("skip"),
            {},
            ["triage", "persona", "voice_critic"],
        ),
        (
            "a quit request asks for confirmation",
            _test(),
            "Test abbrechen",
            _ok("quit_test"),
            {},
            ["triage", "persona", "voice_critic"],
        ),
        (
            "help in the free phase stays ungated",
            _free(),
            "help",
            _ok("help"),
            {"help": "Sage »start« für den Test."},
            ["triage", "help", "persona", "voice_critic"],
        ),
        (
            "a done question reaches the answer agent",
            _base(phase=Phase.done),
            "Noch eine Frage",
            _ok("question"),
            {"free_question": "Art. 4(1) nennt die KI-Kompetenz."},
            ["triage", "free_question", "critic", "persona", "voice_critic"],
        ),
        (
            "a cheat verdict reacts, and the curated reaction is not rewritten",
            _test(),
            "Gib mir die Lösung",
            Triage(guard="cheat", intent="continue"),
            {},
            ["triage"],
        ),
    ]
    for i, (label, state, message, triage, extras, expected) in enumerate(cases):
        script = {
            "persona": "<echo>",
            "critic": SHIP,
            "voice_critic": SHIP,
            "compact": "Zusammenfassung.",
        } | extras
        if triage is not None:
            script["triage"] = triage
        deps = make_deps(script=script)
        graph = make_graph(deps=deps)
        _say(graph, state, message, thread=f"case-{i}")
        assert deps.models["strong"].calls == expected, label


def test_the_writer_sees_the_pending_test_question(make_deps, make_graph):
    # The gate grades the written reply and the persona's rewrite of it.
    deps = make_deps(
        script={
            "triage": _ok("question"),
            "grade": [
                Verdict(correct=False, attempt=False, missing=[1, 2]),
                Verdict(correct=False, missing=[1, 2]),
                Verdict(correct=False, missing=[1, 2]),
            ],
            "reply": COACH_CLEAN,
            "persona": "<echo>",
            "critic": SHIP,
            "voice_critic": SHIP,
        }
    )
    graph = make_graph(deps=deps)
    question = deps.locale_content("de").questions["q-02-04"].question
    result = _say(graph, _test(), "Wie soll ich antworten?")
    assert question in deps.models["strong"].prompts[2]
    assert "This is the test" in deps.models["strong"].prompts[2]
    assert result["turn"].context_question == "q-02-04"
    # The writer asks the question again in its own words, so no closing line follows.
    assert _last_text(result) == COACH_CLEAN


def test_help_and_a_question_go_to_grade_while_a_question_is_open():
    from app.graph.state import Intent, TestState

    for phase, key in ((Phase.lesson, "practice"), (Phase.test, "test")):
        for intent in (Intent.help, Intent.question, Intent.answer, Intent.choose):
            state = _base(phase=phase)
            state[key] = TestState(question_ids=["q-02-04"], practice=key == "practice")
            state["turn"] = TurnScratch(intent=intent)
            assert route_after_triage(state) == "grade", (phase, intent)
        state["turn"] = TurnScratch(intent=Intent.skip)
        assert route_after_triage(state) == "skip"
    # A nudge while a practice question is open is an answer attempt too (the fast triage
    # model reads short answers as nudges); in the test it re-asks the question.
    practice = _practice() | {"turn": TurnScratch(intent=Intent.continue_)}
    assert route_after_triage(practice) == "grade"
    assert route_after_triage(_test() | {"turn": TurnScratch(intent=Intent.continue_)}) == "react"


def test_start_test_draws_the_frozen_order(make_deps, make_graph):
    deps = make_deps(
        script={
            "triage": _ok("start_test"),
            "persona": "<echo>",
            "critic": SHIP,
            "voice_critic": SHIP,
        }
    )
    graph = make_graph(deps=deps)
    result = _say(graph, _free(), "start")
    assert result["phase"] is Phase.test
    assert result["attempts"] == 1
    assert result["test"].question_ids == FROZEN_SEED_1
    first = deps.locale_content("de").questions[FROZEN_SEED_1[0]]
    assert result["pending_prompt"] == first.question


def test_a_test_request_in_a_lesson_asks_before_the_graded_test_starts(make_deps, make_graph):
    deps = make_deps(
        script={
            "triage": [_ok("start_test"), _ok("answer")],
            "persona": "<echo>",
            "critic": SHIP,
            "voice_critic": SHIP,
        }
    )
    graph = make_graph(deps=deps)
    config = {"configurable": {"thread_id": "ask-yes"}}
    state = dict(_lesson()) | {"pending_prompt": t("de", "step_prompt")}
    asked = graph.invoke(state | {"messages": [HumanMessage("direkt den test?")]}, config)
    assert asked["pending_start_test"] is True
    assert asked["test"] is None
    assert asked["phase"] is Phase.lesson
    assert _last_text(asked) == t("de", "test_confirm", chapters=8, total=10, threshold=8)
    assert asked["last_hint"].kind == "yes_no"
    started = graph.invoke({"messages": [HumanMessage("yes")]}, config)
    assert started["pending_start_test"] is False
    assert started["phase"] is Phase.test
    assert started["test"].question_ids == FROZEN_SEED_1


def test_a_declined_test_question_puts_the_student_back_in_the_chapter(make_deps, make_graph):
    deps = make_deps(
        script={
            "triage": [_ok("start_test"), _ok("continue")],
            "persona": "<echo>",
            "critic": SHIP,
            "voice_critic": SHIP,
        }
    )
    graph = make_graph(deps=deps)
    config = {"configurable": {"thread_id": "ask-no"}}
    state = dict(_lesson()) | {"pending_prompt": t("de", "step_prompt")}
    graph.invoke(state | {"messages": [HumanMessage("kann ich den test machen?")]}, config)
    declined = graph.invoke({"messages": [HumanMessage("no")]}, config)
    assert declined["pending_start_test"] is False
    assert declined["test"] is None
    assert declined["phase"] is Phase.lesson
    assert declined["step_idx"] == 1
    assert _last_text(declined) == f"{t('de', 'test_declined')}\n\n{t('de', 'step_prompt')}"
    assert declined["last_hint"].kind == "confirm"
    assert declined["last_hint"].label == t("de", "continue_label")


def test_the_pending_test_question_survives_a_reload_of_the_graph(make_deps, make_graph):
    deps = make_deps(
        script={
            "triage": [_ok("start_test"), _ok("answer")],
            "persona": "<echo>",
            "critic": SHIP,
            "voice_critic": SHIP,
        }
    )
    checkpointer = InMemorySaver()
    config = {"configurable": {"thread_id": "ask-reload"}}
    state = dict(_lesson()) | {"pending_prompt": t("de", "step_prompt")}
    asked = build_graph(deps, checkpointer).invoke(
        state | {"messages": [HumanMessage("direkt zum test")]}, config
    )
    assert asked["pending_start_test"] is True
    fresh = build_graph(deps, checkpointer)
    assert fresh.get_state(config).values["pending_start_test"] is True
    started = fresh.invoke({"messages": [HumanMessage("yes")]}, config)
    assert started["phase"] is Phase.test
    assert started["pending_start_test"] is False


def test_a_rejected_reply_is_written_again_before_the_persona_speaks(make_deps, make_graph):
    deps = make_deps(
        script={
            "triage": _ok("question"),
            "grade": Verdict(correct=False, attempt=False, missing=[1, 2]),
            "reply": [COACH_LEAKY, COACH_CLEAN],
            "critic": [
                Critique(verdict="retry", faults=["leak"], notes="Nenn den Punkt nicht.", score=2),
                SHIP,
            ],
            "voice_critic": SHIP,
            "persona": "<echo>",
        }
    )
    graph = make_graph(deps=deps)
    result = _say(graph, _test(), "Wie soll ich antworten?")
    assert deps.models["strong"].calls == [
        "triage",
        "grade",
        "reply",
        "critic",
        "reply",
        "critic",
        "persona",
        "voice_critic",
    ]
    assert _last_text(result) == COACH_CLEAN
    assert COACH_LEAKY not in _last_text(result)
    assert f"--- YOUR LAST DRAFT\n{COACH_LEAKY}" in deps.models["strong"].prompts[4]
    assert COACH_CLEAN in deps.models["strong"].prompts[-1]
    assert COACH_LEAKY not in deps.models["strong"].prompts[-1]


def test_a_skip_and_a_quit_flow_change_the_attempt_not_the_model(make_deps, make_graph):
    deps = make_deps(
        script={
            "triage": [_ok("skip"), _ok("quit_test"), _ok("answer")],
            # "Ja, abbrechen" is typed, so the fast model reads it.
            "prose": ProseChoice(answer="yes"),
            "persona": "<echo>",
            "critic": SHIP,
            "voice_critic": SHIP,
        }
    )
    graph = make_graph(deps=deps)
    config = {"configurable": {"thread_id": "quit"}}
    result = graph.invoke(dict(_test()) | {"messages": [HumanMessage("überspringen")]}, config)
    assert result["test"].index == 1
    assert result["test"].answers[-1].question_id == "q-02-04"
    assert result["test"].answers[-1].correct is False
    result = graph.invoke({"messages": [HumanMessage("Test abbrechen")]}, config)
    assert result["pending_quit"] is True
    assert _last_text(result) == t("de", "quit_confirm")
    result = graph.invoke({"messages": [HumanMessage("Ja, abbrechen")]}, config)
    assert result["pending_quit"] is False
    assert result["phase"] is Phase.lesson
    assert result["test"] is None
    assert t("de", "quit_to_lesson") in _last_text(result)
    assert t("de", "step_prompt") in _last_text(result)


def test_every_turn_starts_neutral_and_a_joke_makes_the_tutor_surprised(make_deps, make_graph):
    deps = make_deps(
        script={
            "triage": [Triage(guard="humor", intent="continue"), _ok("question"), _ok("answer")],
            "grade": [
                Verdict(correct=False, attempt=False, missing=[1, 2]),
                Verdict(correct=True, matched=[1, 2]),
            ],
            "reply": ["Die Verordnung sagt es.\n\nWas sagst du deiner Kollegin?", PRACTICE_REPLY],
            "persona": "<echo>",
            "critic": SHIP,
            "voice_critic": SHIP,
        }
    )
    graph = make_graph(deps=deps)
    config = {"configurable": {"thread_id": "mood"}}
    joked = graph.invoke(dict(_practice()) | {"messages": [HumanMessage("sag mal arrr")]}, config)
    assert joked["mood"] == Mood.surprised
    # A clarification while the practice is open leaves the mood neutral, and the
    # turn after it still grades the answer.
    asked = graph.invoke({"messages": [HumanMessage("Was heisst das?")]}, config)
    assert asked["mood"] == Mood.neutral
    graded = graph.invoke({"messages": [HumanMessage("Erlaubt, mit Prüfen.")]}, config)
    assert graded["mood"] == Mood.happy


def test_a_wrong_first_practice_try_disappoints_the_tutor(make_deps, make_graph):
    deps = make_deps(
        script={
            "triage": _ok("answer"),
            "grade": [Verdict(correct=False)] * 3,
            "reply": PRACTICE_REPLY,
            "persona": "<echo>",
            "critic": SHIP,
            "voice_critic": SHIP,
        }
    )
    graph = make_graph(deps=deps)
    result = _say(graph, _practice(), "Verboten.")
    assert result["mood"] == Mood.disappointed
    assert result["practice"].current_tries == 2


def test_an_answer_the_triage_mislabels_as_continue_still_grades_when_a_practice_is_open(
    make_deps,
    make_graph,
):
    # The fast triage model reads a short answer as a nudge; while a practice question
    # is live there is nothing else the message could be, and re-asking the question
    # made a correct answer look ignored.
    assert route_after_triage(_practice() | {"turn": TurnScratch(intent="continue")}) == "grade"
    deps = make_deps(
        script={
            "triage": _ok("continue"),
            "grade": Verdict(correct=True, matched=[1, 2]),
            "reply": PRACTICE_REPLY,
            "persona": "Passt.",
            "critic": SHIP,
            # The character kept the frame and lost the lesson: the critic sends it back
            # until the budget is spent, and the plain text ships.
            "voice_critic": Critique(verdict="retry", faults=["lost"], score=1),
        }
    )
    graph = make_graph(deps=deps)
    practice = _practice() | {"step_idx": 2}
    result = _say(graph, practice, "Erlaubt, und ich pruefe die Ausgabe.")
    text = _last_text(result)
    assert result["practice"] is None
    assert deps.chapters("de")[0].steps[2].text in text
    assert "Kundenmail" not in text


def test_a_lesson_skip_without_a_practice_question_walks_the_next_step(make_deps, make_graph):
    assert route_after_triage(_base(phase=Phase.lesson, turn=TurnScratch(intent="skip"))) == (
        "lesson_step"
    )
    deps = make_deps(
        script={"triage": _ok("skip"), "persona": "<echo>", "critic": SHIP, "voice_critic": SHIP}
    )
    graph = make_graph(deps=deps)
    step = deps.chapters("de")[0].steps[1]
    result = _say(graph, _lesson(), "weiter")
    assert result["step_idx"] == 2
    assert step.text in _last_text(result)
    assert t("de", "step_prompt") not in _last_text(result)
    # Walking the next step holds that step's own case, it does not skip one.
    assert result["pending_case"] == step.question
    assert result["pending_prompt"] == t("de", "clear_so_far")


def test_a_lesson_quit_intent_lands_on_the_lesson_step_never_on_quit_test(make_deps, make_graph):
    assert (
        route_after_triage(_base(phase=Phase.lesson, turn=TurnScratch(intent="quit_test")))
        == "lesson_step"
    )
    practice = _practice()
    assert route_after_triage(practice | {"turn": TurnScratch(intent="quit_test")}) == "lesson_step"
    deps = make_deps(
        script={
            "triage": _ok("quit_test"),
            "persona": "<echo>",
            "critic": SHIP,
            "voice_critic": SHIP,
        }
    )
    graph = make_graph(deps=deps)
    question = deps.locale_content("de").questions["q-02-04"].question
    result = _say(graph, _practice(), "Test abbrechen")
    assert result["phase"] is Phase.lesson
    assert result["pending_quit"] is False
    assert result["practice"] is not None
    assert result["pending_prompt"] == question


def test_an_exhausted_test_cannot_be_quit(make_deps, make_graph):
    deps = make_deps(
        script={
            "triage": [_ok("skip"), _ok("skip"), _ok("quit_test")],
            "free_question": "Einen Test gibt es hier nicht mehr abzubrechen.",
            "persona": "<echo>",
            "critic": SHIP,
            "voice_critic": SHIP,
        }
    )
    graph = make_graph(deps=deps)
    config = {"configurable": {"thread_id": "exhausted"}}
    result = graph.invoke(dict(_test()) | {"messages": [HumanMessage("überspringen")]}, config)
    assert result["test"].index == 1
    result = graph.invoke({"messages": [HumanMessage("überspringen")]}, config)
    assert result["test"].index == 2
    # A finished test cannot be failed any more: it completes (D128).
    assert result["phase"] is Phase.done

    result = graph.invoke({"messages": [HumanMessage("Test abbrechen")]}, config)
    assert result["phase"] is Phase.done
    assert result["pending_quit"] is False


FREE_TEXT_ANSWER = "Das entscheidet der Einsatz, und die Ausgabe prüfe ich vor dem Absenden."


def _answer_to(question) -> str:
    """An answer the graders read without a model call for the two closed types."""
    if question.type == "yes_no":
        return "yes" if question.correct == "yes" else "no"
    if question.type == "multiple_choice":
        return question.correct
    return FREE_TEXT_ANSWER


def _has_a_typed_why(question) -> bool:
    """A closed question whose rubric holds why points past the pick (D127)."""
    return (
        question.type != "free_text"
        and question.rubric is not None
        and (len(question.rubric.must) > 1)
    )


def _lesson_walk(chapters, questions) -> list[tuple[str, Triage | None]]:
    """The greeting, then per step the check-in, the pick or typed answer, and the typed
    why when the pick left one open. A click needs no intent check (D130): its triage is
    None.

    A step teaches and asks whether it landed (D96); the student says yes and gets the case
    (D76); the answer to it carries the next step's teaching in the same turn (D89). A
    chapter's last answer closes the chapter in a turn of its own, and a "weiter" opens the
    next one.
    """
    turns: list[tuple[str, Triage | None]] = [("Hallo, ich bin bereit.", _ok())]
    for index, chapter in enumerate(chapters):
        if index > 0:
            turns.append(("weiter", _ok()))
        for step in chapter.steps:
            question = questions[step.question]
            turns.append(("Ja, weiter", _ok()))
            clicked = question.type != "free_text"
            turns.append((_answer_to(question), None if clicked else _ok("answer")))
            if _has_a_typed_why(question):
                turns.append((FREE_TEXT_ANSWER, _ok("answer")))
    return turns


def test_one_scripted_journey_from_the_first_lesson_to_a_recorded_completion(
    make_deps, make_graph, content
):
    records: list[CompletionRecord] = []
    de = content.locales["de"]
    chapters = [de.chapters[key] for key in sorted(de.chapters)]
    questions = de.questions
    lesson = _lesson_walk(chapters, questions)
    # Eight chapters, 35 steps; a chained question adds its typed why (D127).
    assert [len(chapter.steps) for chapter in chapters] == [6, 5, 4, 4, 4, 4, 4, 4]
    assert len(lesson) == 87

    # The test, in the order of the frozen draw. The sixth question is skipped, and a
    # chained question (q-06-02) answers its typed why after the pick.
    drawn = [questions[qid] for qid in FROZEN_SEED_1]
    test_answers = [_answer_to(question) for question in drawn]
    test_answers.insert(3, FREE_TEXT_ANSWER)
    assert drawn[5].type == "free_text"
    assert _has_a_typed_why(drawn[2])

    lesson_free_text = sum(
        1
        for chapter in chapters
        for step in chapter.steps
        if questions[step.question].type == "free_text"
    )
    chained = sum(
        1
        for chapter in chapters
        for step in chapter.steps
        if _has_a_typed_why(questions[step.question])
    )
    assert lesson_free_text == 7
    assert chained == 9
    # One verdict per typed answer: the lesson's free-text answers and typed whys, then
    # the test's written answers: six free-text (the sixth question is skipped) and
    # q-06-02's typed why.
    grade = [Verdict(correct=True)] * (lesson_free_text + chained + 7)
    expected_grade_calls = len(grade)
    messages = [message for message, _ in lesson] + ["start"] + test_answers
    script = {
        # The three clicks of the test (q-06-02, q-04-02, q-02-03) take no intent check.
        "triage": [triage for _, triage in lesson if triage is not None]
        + [_ok("start_test")]
        + ([_ok("answer")] * 4 + [_ok("skip")] + [_ok("answer")] * 3),
        "grade": grade,
        # One written reply per lesson answer: the pick, the why and the typed case.
        "reply": PRACTICE_REPLY,
        "persona": "<echo>",
        "critic": SHIP,
        "voice_critic": SHIP,
        "compact": "Zusammenfassung.",
    }
    assert len(script["triage"]) == 68
    assert len(messages) == 99
    deps = make_deps(script=script, record=records)
    graph = make_graph(deps=deps)
    config = {"configurable": {"thread_id": "t1"}}
    results = [
        graph.invoke(
            initial_state("clerk", user_id=7) | {"messages": [HumanMessage(messages[0])]}, config
        )
    ]
    for message in messages[1:]:
        results.append(graph.invoke({"messages": [HumanMessage(message)]}, config))

    assert len(records) == 1
    record = records[0]
    assert record.user_id == 7
    assert record.course_version == "0.1.0"
    assert record.law_version == "test"
    assert record.locale == "de"
    assert record.persona_id == "clerk"

    final = results[-1]
    assert final["phase"] is Phase.done
    assert final["test"].index == 10
    assert sum(1 for answer in final["test"].answers if answer.correct) == 9
    assert t("de", "finale", score=9, total=10) in _last_text(final)

    after_the_first_step = results[0]
    assert after_the_first_step.get("practice") is None
    assert after_the_first_step["pending_case"] == "q-01-11"
    assert after_the_first_step["turn"].input_hint.kind == "confirm"
    assert after_the_first_step["step_idx"] == 1

    after_the_check_in = results[1]
    assert after_the_check_in["practice"].question_ids == ["q-01-11"]
    assert after_the_check_in["turn"].input_hint.asks is True

    after_the_answered_step = results[2]
    assert after_the_answered_step["pending_case"] == "q-01-05"
    assert after_the_answered_step["step_idx"] == 2
    assert after_the_answered_step["turn"].input_hint.kind == "confirm"
    # A chip's answer settles on the curated verdict and model answer, with no model call
    # (D127).
    assert "Richtig.\n\n" + questions["q-01-11"].model_answer in _last_text(after_the_answered_step)
    assert chapters[0].steps[1].text in _last_text(after_the_answered_step)

    # Chapter one's last answer is the typed why of q-01-13: it closes the chapter in a
    # turn of its own, and chapter two waits behind the button.
    after_chapter_one = results[14]
    assert after_chapter_one["phase"] is Phase.lesson
    assert after_chapter_one["chapter_idx"] == 0
    assert after_chapter_one["chapters_done"] == [CHAPTER]
    assert after_chapter_one["pending_case"] is None
    assert after_chapter_one["turn"].input_hint == InputHint(
        kind="confirm", label="Weiter zu Kapitel 2"
    )
    assert _last_text(after_chapter_one).endswith(chapters[0].may)
    opening_two = results[15]
    assert opening_two["chapter_idx"] == 1
    assert opening_two["step_idx"] == 1
    assert opening_two["pending_case"] == "q-02-01"
    assert opening_two["turn"].parts[0] == ChapterStartPart(
        title=chapters[1].title, intro=chapters[1].intro
    )

    after_chapter_two = results[27]
    assert after_chapter_two["chapter_idx"] == 1
    assert after_chapter_two["chapters_done"] == [CHAPTER, "02-was-du-hineingeben-darfst"]
    assert after_chapter_two["turn"].input_hint.label == "Weiter zu Kapitel 3"
    assert _last_text(after_chapter_two).endswith(chapters[1].may)

    after_the_last_chapter = results[86]
    assert after_the_last_chapter["phase"] is Phase.free
    assert after_the_last_chapter["chapters_done"] == [chapter.id for chapter in chapters]
    assert after_the_last_chapter["turn"].input_hint.label == "Zum Test"
    assert _last_text(after_the_last_chapter).endswith(chapters[7].may)
    after_start = results[87]
    assert after_start["phase"] is Phase.test
    assert after_start["test"].question_ids == FROZEN_SEED_1
    after_the_skip = results[94]
    assert after_the_skip["test"].index == 6
    card = after_the_skip["turn"].parts[0]
    assert isinstance(card, ModelAnswerCard)
    assert card.correct is False

    calls = deps.models["strong"].calls
    # 28 lesson clicks and 3 test clicks take no intent check (D130).
    assert calls.count("triage") == len(messages) - 31 == 68
    # A case turn carries only the protected question, which never reaches the rewrite
    # (D96), and a curated pick reply is the persona's own line (D130): the 9 lesson
    # follow-ups and the 3 picked test turns. The 8 chapter ends are curated too.
    assert calls.count("persona") == len(messages) - 35 - 9 - 3 - 8 == 44
    # The writer runs only for the free-text lesson answers: every pick and every closed
    # settle answers on curated text (D125, D130), and the test writes nothing.
    assert calls.count("reply") == lesson_free_text == 7
    assert calls.count("grade") == expected_grade_calls == 23
    assert calls.count("critic") == lesson_free_text
    assert "free_question" not in calls


def test_a_help_reask_keeps_the_structured_hint_of_the_pending_question(
    make_deps, make_graph, content
):
    from app.graph.state import TestState, hint_for_question

    question = content.locales["de"].questions["q-01-03"]
    expected = hint_for_question(question)
    state = _base(
        phase=Phase.test,
        attempts=1,
        test=TestState(question_ids=["q-01-03"]),
        pending_prompt=question.question,
        last_hint=expected,
    )
    # A plea for help on a choice question is no attempt: the prose model resolves it to
    # none.
    deps = make_deps(
        script={
            "triage": _ok("help"),
            "prose": [ProseChoice(answer="none")] * 3,
            "reply": "Ich zeige dir keine Lösung. Welcher Buchstabe passt?",
            "persona": "<echo>",
            "critic": SHIP,
            "voice_critic": SHIP,
        }
    )
    graph = make_graph(deps=deps)
    result = _say(graph, state, "help", thread="hint-help")
    assert expected.kind == "choices" and len(expected.choices) == 4
    assert result["turn"].input_hint.kind == "choices"
    assert result["turn"].input_hint.choices == expected.choices
    assert result["turn"].input_hint.asks is True
    assert result["last_hint"].choices == expected.choices
    assert deps.models["strong"].calls == [
        "triage",
        "prose",
        "reply",
        "critic",
        "persona",
        "voice_critic",
    ]


def test_a_fresh_graph_over_the_same_checkpointer_resumes_the_thread(make_deps, make_graph):
    checkpointer = InMemorySaver()
    deps = make_deps(
        script={
            "triage": [_ok(), _ok(), _ok("answer"), _ok()],
            "reply": PRACTICE_REPLY,
            "persona": "<echo>",
            "critic": SHIP,
            "voice_critic": SHIP,
        }
    )
    config = {"configurable": {"thread_id": "t1"}}
    graph = make_graph(deps=deps, checkpointer=checkpointer)
    result = graph.invoke(initial_state("clerk") | {"messages": [HumanMessage("Hallo")]}, config)
    assert result["step_idx"] == 1
    assert result["pending_case"] == "q-01-11"

    graph2 = make_graph(deps=deps, checkpointer=checkpointer)
    asked = graph2.invoke({"messages": [HumanMessage("Ja, weiter")]}, config)
    assert asked["practice"].question_ids == ["q-01-11"]
    answered = graph2.invoke({"messages": [HumanMessage("B")]}, config)
    assert answered["step_idx"] == 2
    assert answered["pending_case"] == "q-01-05"
    # A Weiter on the check-in opens the case the step just taught.
    result2 = graph2.invoke({"messages": [HumanMessage("weiter")]}, config)
    assert result2["persona_id"] == "clerk"
    assert result2["phase"] is Phase.lesson
    assert result2["step_idx"] == 2
    assert result2["practice"].question_ids == ["q-01-05"]


def test_a_chapter_crossing_survives_a_reload_over_the_same_checkpointer(make_deps, make_graph):
    checkpointer = InMemorySaver()
    deps = make_deps(
        script={
            "triage": [_ok("answer"), _ok()],
            "grade": [Verdict(correct=True)],
            "reply": PRACTICE_REPLY,
            "persona": "<echo>",
            "critic": SHIP,
            "voice_critic": SHIP,
        }
    )
    config = {"configurable": {"thread_id": "t1"}}
    graph = make_graph(deps=deps, checkpointer=checkpointer)
    result = graph.invoke(
        dict(_practice()) | {"messages": [HumanMessage("Erlaubt, mit Prüfen.")]}, config
    )
    assert result["chapters_done"] == [CHAPTER]
    assert result["chapter_idx"] == 0

    # The chapter end waits behind its button across a reload, and the nod crosses over.
    reloaded = make_graph(deps=deps, checkpointer=checkpointer)
    values = reloaded.get_state(config).values
    assert values["chapters_done"] == [CHAPTER]
    assert values["chapter_idx"] == 0
    assert values["last_hint"] == InputHint(kind="confirm", label="Weiter zu Kapitel 2")
    assert values["messages"][-1].additional_kwargs["parts"][-1]["kind"] == "chapter_done"
    crossed = reloaded.invoke({"messages": [HumanMessage("weiter")]}, config)
    assert crossed["phase"] is Phase.lesson
    assert crossed["chapter_idx"] == 1
    assert crossed["step_idx"] == 1
    assert crossed["pending_case"] == "q-02-01"
    assert crossed["messages"][-1].additional_kwargs["parts"][0]["kind"] == "chapter_start"


def test_the_sqlite_checkpointer_persists_a_turn(tmp_path, make_deps):
    settings = Settings(
        _env_file=None,
        env="development",
        database_url=f"sqlite:///{tmp_path / 'checkpoint.db'}",
    )

    async def run() -> None:
        async with open_checkpointer(settings) as checkpointer:
            deps = make_deps(
                script={"triage": _ok(), "persona": "<echo>", "critic": SHIP, "voice_critic": SHIP}
            )
            graph = build_graph(deps, checkpointer)
            await graph.ainvoke(
                initial_state("clerk") | {"messages": [HumanMessage("Hallo")]},
                {"configurable": {"thread_id": "sqlite"}},
            )

    asyncio.run(run())
    with sqlite3.connect(tmp_path / "checkpoint.db") as connection:
        rows = connection.execute("SELECT count(*) FROM checkpoints").fetchone()[0]
    assert rows >= 1


def test_the_postgres_url_loses_its_sqlalchemy_dialect():
    # Compose ships postgresql+psycopg://; AsyncPostgresSaver hands the string to
    # psycopg, which rejects the dialect suffix.
    assert (
        _postgres_conn_string("postgresql+psycopg://user:pw@host/db")
        == "postgresql://user:pw@host/db"
    )
    assert (
        _postgres_conn_string("postgresql+psycopg://trainer:pw@postgres:5432/trainer")
        == "postgresql://trainer:pw@postgres:5432/trainer"
    )


def test_a_no_to_the_check_in_asks_what_did_not_land_and_keeps_the_case_back(make_deps, make_graph):
    from app.graph.state import InputHint

    confirm = InputHint(kind="confirm", label="Ja, weiter")
    state = _lesson() | {
        "pending_case": "q-01-01",
        "pending_prompt": "Klar soweit?",
        "last_hint": confirm,
    }
    deps = make_deps(script={"triage": _ok("help"), "persona": "<echo>", "voice_critic": SHIP})
    result = _say(make_graph(deps=deps), state, "nee")
    assert deps.models["strong"].calls == ["triage", "persona", "voice_critic"]
    assert _last_text(result) == t("de", "clear_not_yet")
    assert result["pending_case"] == "q-01-01"
    assert result["practice"] is None
    assert result["step_idx"] == 1
    assert result["last_hint"] == InputHint(kind="confirm", label=t("de", "continue_label"))


def _chained_practice() -> SessionState:
    from app.graph.state import TestState

    return _base(
        phase=Phase.lesson,
        step_idx=4,
        practice=TestState(question_ids=["q-01-13"], practice=True),
    )


ASK_SIGN_WHY = "Das Marketing fragt, wer den Hinweis jetzt dazuschreiben muss. Was sagst du?"


def test_a_clicked_right_pick_that_opens_its_follow_up_calls_no_model(make_deps, make_graph):
    # The click is the answer and the reply is curated: no intent check, no writer, no
    # checker and no persona rewrite stand between the click and the follow-up (D130).
    deps = make_deps(script={})
    graph = make_graph(deps=deps)
    result = _say(graph, _chained_practice(), "yes", thread="fast-click")
    assert deps.models["strong"].calls == []
    text = _last_text(result)
    lines = deps.persona("clerk").verdicts["right"]
    assert any(text == f"{line}\n\n{ASK_SIGN_WHY}" for line in lines), text
    assert result["messages"][-1].additional_kwargs["hint"]["kind"] == "text"


def test_a_typed_bare_yes_costs_the_intent_check_and_one_reading(make_deps, make_graph):
    deps = make_deps(
        script={
            "triage": _ok("answer"),
            "prose": ProseChoice(answer="yes"),
        }
    )
    graph = make_graph(deps=deps)
    result = _say(graph, _chained_practice(), "Glaub schon!", thread="fast-typed")
    assert deps.models["strong"].calls == ["triage", "prose"]
    assert _last_text(result).endswith(ASK_SIGN_WHY)
