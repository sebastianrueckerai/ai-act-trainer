from langchain_core.messages import HumanMessage

from app.graph.state import (
    ChapterDonePart,
    ChapterStartPart,
    Choice,
    FilePart,
    InputHint,
    Phase,
    TurnScratch,
    UiEvent,
    hint_for_question,
    initial_state,
)
from app.graph.teach import lesson_step_node
from app.i18n import t


def _lesson_state(step_idx: int = 0) -> dict:
    state = initial_state("clerk")
    state["phase"] = Phase.lesson
    state["step_idx"] = step_idx
    state["messages"] = [HumanMessage("weiter")]
    return state


def test_the_first_step_opens_the_course_in_medias_res(make_deps):
    deps = make_deps(script={})
    chapters = deps.chapters("de")
    chapter, step = chapters[0], chapters[0].steps[0]
    assert step.example is None
    result = lesson_step_node(deps)(_lesson_state())
    assert result["turn"].draft == step.text
    assert chapter.intro not in result["turn"].draft
    assert [part.ref for part in result["turn"].parts] == ["Art. 3(1)", "Art. 3(4)"]
    # The concept lands first and the case waits behind the check-in (D96).
    assert result["turn"].closing_line == t("de", "clear_so_far")
    assert result["turn"].input_hint == InputHint(
        kind="confirm", label=t("de", "clear_yes"), asks=False
    )
    assert result["pending_case"] == step.question
    assert result["pending_prompt"] == t("de", "clear_so_far")
    assert result["step_idx"] == 1
    assert deps.models["strong"].calls == []


def test_the_case_follows_the_check_in(make_deps):
    deps = make_deps(script={})
    step = deps.chapters("de")[0].steps[0]
    question = deps.question(step.question)
    state = _lesson_state(step_idx=1)
    state["pending_case"] = step.question

    result = lesson_step_node(deps)(state)

    assert result["turn"].draft == question.question
    assert result["turn"].input_hint == hint_for_question(question, reveal=True)
    assert result["turn"].context_question == question.id
    assert result["turn"].closing_line == ""
    assert result["pending_case"] is None
    assert result["practice"].question_ids == [question.id]
    assert result["practice"].practice is True
    assert result["pending_prompt"] == question.question
    assert "step_idx" not in result
    assert deps.models["strong"].calls == []


def test_a_step_with_a_question_teaches_first_and_holds_the_case(make_deps):
    deps = make_deps(script={})
    chapter = deps.chapters("de")[0]
    step = chapter.steps[1]
    result = lesson_step_node(deps)(_lesson_state(step_idx=1))
    assert result["turn"].draft == "\n\n".join([step.text, step.example])
    assert result["turn"].input_hint.kind == "confirm"
    assert result["turn"].closing_line == t("de", "clear_so_far")
    assert [part.ref for part in result["turn"].parts] == ["Art. 4(1)", "Q&A 14"]
    assert result["pending_case"] == step.question
    assert result["step_idx"] == 2
    assert deps.models["strong"].calls == []


def test_a_step_without_a_question_ends_on_the_weiter_hint(make_deps, content):
    # Every curated step carries its neighbouring case (D76). The branch for a step that
    # carries none still has to hand over the Weiter hint, so this strips one.
    deps = make_deps(script={})
    patched = content.model_copy(deep=True)
    chapter = patched.locales["de"].chapters["02-was-du-hineingeben-darfst"]
    chapter.steps[0] = chapter.steps[0].model_copy(update={"question": None})
    deps.content = patched
    step = chapter.steps[0]
    state = _lesson_state()
    state["chapter_idx"] = 1
    result = lesson_step_node(deps)(state)
    assert result["turn"].draft == "\n\n".join([step.text, step.example])
    assert result["turn"].closing_line == ""
    assert result["turn"].input_hint == InputHint(kind="confirm", label=t("de", "continue_label"))
    assert result["pending_prompt"] == t("de", "step_prompt")
    assert "practice" not in result
    assert result["step_idx"] == 1
    assert deps.models["strong"].calls == []


def test_a_continue_during_an_active_practice_reasks_the_current_question(make_deps):
    from app.graph.state import TestState

    deps = make_deps(script={})
    state = _lesson_state(step_idx=6)
    state["practice"] = TestState(question_ids=["q-02-04"], practice=True)
    result = lesson_step_node(deps)(state)
    open_question = deps.question("q-02-04")
    assert result["turn"].draft == open_question.question
    assert result["turn"].input_hint == InputHint(kind="text", asks=True)
    assert result["turn"].context_question == "q-02-04"
    assert result["pending_prompt"] == open_question.question
    assert "practice" not in result
    assert deps.models["strong"].calls == []


def _settled_state(chapter_idx: int, step_idx: int) -> dict:
    """A chapter's last case just settled right: the verdict and its confetti ride along."""
    state = _lesson_state(step_idx=step_idx)
    state["chapter_idx"] = chapter_idx
    state["turn"] = TurnScratch(
        draft="Richtig.\n\nSo ist es.",
        ui_events=[
            UiEvent(name="answer_result", payload={"verdict": "correct", "settled": True}),
            UiEvent(name="confetti"),
        ],
    )
    return state


def test_a_chapter_end_is_a_curated_turn_of_its_own_and_the_next_chapter_waits(make_deps):
    deps = make_deps(script={})
    chapters = deps.chapters("de")
    result = lesson_step_node(deps)(_settled_state(0, 6))
    turn = result["turn"]
    # The settle, the clerk's chapter line for seed "seed:1", the chapter's may line.
    assert turn.draft == "\n\n".join(
        ["Richtig.\n\nSo ist es.", "Damit ist Kapitel 1 erledigt. Ordnungsgemäß.", chapters[0].may]
    )
    assert chapters[0].may.startswith("Das darfst du: entwerfen, übersetzen")
    assert turn.voiced is True
    assert turn.closing_line == ""
    file_part, done_part = turn.parts
    assert isinstance(file_part, FilePart)
    assert file_part.title == "Spickzettel: Was du mit KI am Arbeitsplatz darfst"
    assert done_part == ChapterDonePart(
        chapter_id="01-warum-es-dich-betrifft",
        index=1,
        total=8,
        title="Was du mit KI am Arbeitsplatz darfst",
    )
    assert turn.input_hint == InputHint(kind="confirm", label="Weiter zu Kapitel 2")
    # One click, one celebration: the chapter end drops the answer's confetti.
    assert [event.name for event in turn.ui_events] == [
        "answer_result",
        "chapter_complete",
        "badge",
    ]
    assert turn.ui_events[1].payload == {"chapter": "01-warum-es-dich-betrifft"}
    assert result["chapters_done"] == ["01-warum-es-dich-betrifft"]
    assert result["pending_prompt"] == ""
    # No next step: the chapter stays where it is until the click.
    assert not {"chapter_idx", "step_idx", "pending_case", "phase"} & set(result)
    assert deps.models["strong"].calls == []


def test_the_click_after_a_chapter_end_opens_the_next_chapter_on_its_level_card(make_deps):
    deps = make_deps(script={})
    chapters = deps.chapters("de")
    state = _lesson_state(step_idx=6)
    state["chapters_done"] = ["01-warum-es-dich-betrifft"]
    result = lesson_step_node(deps)(state)
    step = chapters[1].steps[0]
    assert result["chapter_idx"] == 1
    assert result["step_idx"] == 1
    assert result["turn"].parts[0] == ChapterStartPart(
        title="Was du hineingeben darfst", intro=chapters[1].intro
    )
    assert result["turn"].draft == "\n\n".join([step.text, step.example])
    assert result["turn"].input_hint == InputHint(kind="confirm", label="Ja, weiter")
    assert result["pending_case"] == step.question
    assert result["turn"].ui_events == []
    assert "chapters_done" not in result


def test_the_last_chapter_end_offers_the_test_on_the_course_line(make_deps):
    deps = make_deps(script={})
    chapters = deps.chapters("de")
    last = chapters[7]
    result = lesson_step_node(deps)(_settled_state(7, len(last.steps)))
    turn = result["turn"]
    assert turn.draft == "\n\n".join(
        [
            "Richtig.\n\nSo ist es.",
            "Alle Kapitel sind bearbeitet. Es fehlt noch der Test.",
            last.may,
        ]
    )
    assert turn.parts[1] == ChapterDonePart(chapter_id=last.id, index=8, total=8, title=last.title)
    assert turn.input_hint == InputHint(kind="confirm", label="Zum Test")
    assert result["chapters_done"] == [last.id]
    assert result["phase"] is Phase.free
    assert deps.models["strong"].calls == []


def test_hint_for_question_covers_yes_no_multiple_choice_and_free_text(make_deps):
    deps = make_deps(script={})
    assert hint_for_question(deps.question("q-01-01")) == InputHint(kind="yes_no", asks=True)
    assert hint_for_question(deps.question("q-01-03")) == InputHint(
        kind="choices",
        asks=True,
        choices=[
            Choice(
                key="A",
                label=(
                    "Du lässt dir eine interne Besprechungsnotiz von einem Chatassistenten "
                    "zusammenfassen."
                ),
            ),
            Choice(
                key="B",
                label="Auf unserer Website beantwortet ein KI-Chatfenster die Fragen von Kunden.",
            ),
            Choice(
                key="C",
                label=(
                    "Du lässt eine Produktbeschreibung ins Englische übersetzen und schickst "
                    "sie an einen Kunden."
                ),
            ),
            Choice(
                key="D",
                label=(
                    "Du sammelst mit einem Chatassistenten Ideen für den Namen eines neuen "
                    "Produkts."
                ),
            ),
        ],
    )
    assert hint_for_question(deps.question("q-02-04")) == InputHint(kind="text", asks=True)


def test_chapter_completion_attaches_cheat_sheet_file_part(make_deps):
    from app.graph.state import FilePart

    deps = make_deps(script={})
    state = _lesson_state(step_idx=6)
    result = lesson_step_node(deps)(state)

    file_parts = [p for p in result["turn"].parts if isinstance(p, FilePart)]
    assert len(file_parts) == 1
    assert file_parts[0].url.startswith("/api/files/")
    assert file_parts[0].title == "Spickzettel: Was du mit KI am Arbeitsplatz darfst"
    assert file_parts[0].filename == "spickzettel-01-warum-es-dich-betrifft.pdf"
