import random

from app.content.models import Chapter, Question
from app.files.tokens import chapter_file_part
from app.graph.deps import GraphDeps
from app.graph.state import (
    ChapterDonePart,
    ChapterStartPart,
    CitationPart,
    InputHint,
    Phase,
    SessionState,
    TestState,
    UiEvent,
    hint_for_question,
)
from app.graph.tools import citations_from_text
from app.i18n import t


def lesson_step_node(deps: GraphDeps):
    def node(state: SessionState) -> dict:
        return _lesson_step_patch(deps, state)

    return node


def _lesson_step_patch(deps: GraphDeps, state: SessionState) -> dict:
    locale = state.get("locale", "de")
    practice = state.get("practice")
    if practice is not None:
        question = deps.question(practice.question_ids[practice.index])
        return _ask_question(state, question)
    pending_case = state.get("pending_case")
    if pending_case is not None:
        return _open_case(deps, state, deps.question(pending_case))
    chapters = deps.chapters(locale)
    chapter_idx = state.get("chapter_idx", 0)
    chapter = chapters[chapter_idx]
    step_idx = state.get("step_idx", 0)
    if step_idx >= len(chapter.steps):
        if chapter.id in state.get("chapters_done", []):
            return _start_chapter(deps, state, chapter_idx + 1)
        return complete_chapter(deps, state)
    step = chapter.steps[step_idx]
    material, parts = _step_material(deps, chapter, step_idx)
    # The turn may already carry the verdict on the question the previous step asked; the
    # lesson goes on inside it rather than behind a button (D89).
    draft = _appended(state["turn"].draft, material)
    if step.question is not None:
        # D96: the concept first, and the case only once the student says the concept
        # landed. A chunk of teaching with a question bolted on is a page, not a turn.
        turn = state["turn"].model_copy(
            update={
                "draft": draft,
                "parts": state["turn"].parts + parts,
                "closing_line": t(locale, "clear_so_far"),
                "input_hint": InputHint(kind="confirm", label=t(locale, "clear_yes")),
            }
        )
        return {
            "turn": turn,
            "step_idx": step_idx + 1,
            "pending_case": step.question,
            "pending_prompt": t(locale, "clear_so_far"),
        }
    turn = state["turn"].model_copy(
        update={
            "draft": draft,
            "parts": state["turn"].parts + parts,
            # The Weiter button sits right under the step, so the step does not spell it out.
            # The prompt still returns after a detour.
            "closing_line": "",
            "input_hint": InputHint(kind="confirm", label=t(locale, "continue_label")),
        }
    )
    return {"turn": turn, "step_idx": step_idx + 1, "pending_prompt": t(locale, "step_prompt")}


def _open_case(deps: GraphDeps, state: SessionState, question: Question) -> dict:
    """The case the step just taught decides, once the student confirmed the concept (D96)."""
    turn = state["turn"].model_copy(
        update={
            "draft": _appended(state["turn"].draft, question.question),
            "closing_line": "",
            "input_hint": hint_for_question(question, reveal=True),
            "context_question": question.id,
        }
    )
    return {
        "turn": turn,
        "pending_case": None,
        "pending_prompt": question.question,
        "practice": TestState(question_ids=[question.id], practice=True),
    }


def _appended(carried: str, material: str) -> str:
    return f"{carried}\n\n{material}" if carried else material


def _step_material(
    deps: GraphDeps, chapter: Chapter, step_idx: int
) -> tuple[str, list[CitationPart]]:
    step = chapter.steps[step_idx]
    blocks = [step.text]
    if step.example:
        blocks.append(step.example)
    return "\n\n".join(blocks), citations_from_text(deps, " ".join(step.citations))


def _ask_question(state: SessionState, question: Question) -> dict:
    """The open question again, for a student who clicked Weiter instead of answering."""
    turn = state["turn"].model_copy(
        update={
            "draft": question.question,
            "input_hint": hint_for_question(question, reveal=True),
            "context_question": question.id,
        }
    )
    return {"turn": turn, "pending_prompt": question.question}


def complete_chapter(deps: GraphDeps, state: SessionState) -> dict:
    """The chapter end is a turn of its own, on curated lines, and the next chapter waits
    behind the button. After the last chapter the button starts the test."""
    locale = state.get("locale", "de")
    chapters = deps.chapters(locale)
    chapter_idx = state.get("chapter_idx", 0)
    chapter = chapters[chapter_idx]
    last = chapter_idx + 1 == len(chapters)
    events = [
        UiEvent(name="chapter_complete", payload={"chapter": chapter.id}),
        UiEvent(name="badge", payload={}),
    ]
    file_part = chapter_file_part(
        deps.settings,
        locale,
        deps.content.manifest.course_version,
        chapter.id,
        chapter.title,
    )
    done_part = ChapterDonePart(
        chapter_id=chapter.id, index=chapter_idx + 1, total=len(chapters), title=chapter.title
    )
    lines = [state["turn"].draft, _milestone(deps, state, chapter_idx + 1, last), chapter.may]
    label = (
        t(locale, "start_test_label")
        if last
        else t(locale, "continue_chapter_label", n=chapter_idx + 2)
    )
    turn = state["turn"].model_copy(
        update={
            "draft": "\n\n".join(line for line in lines if line),
            "closing_line": "",
            # One click, one celebration: the chapter end replaces the answer's confetti.
            "ui_events": [e for e in state["turn"].ui_events if e.name != "confetti"] + events,
            "parts": state["turn"].parts + [file_part, done_part],
            "input_hint": InputHint(kind="confirm", label=label),
            "voiced": True,
        }
    )
    patch = {
        "turn": turn,
        "chapters_done": state.get("chapters_done", []) + [chapter.id],
        "pending_prompt": "",
    }
    if last:
        # A finished course is the free phase, where the button's nod starts the test at once.
        patch["phase"] = Phase.free
    return patch


def _milestone(deps: GraphDeps, state: SessionState, number: int, last: bool) -> str:
    """The character's own line on the finished chapter, drawn per turn like a verdict line,
    or on the finished course."""
    persona = deps.persona(state.get("persona_id"))
    if persona is None:
        return ""
    if last:
        return persona.milestones["course"][0]
    seed = f"{state.get('session_seed', 'seed')}:{len(state.get('messages', []))}"
    line = random.Random(seed).choice(persona.milestones["chapter"])
    return line.replace("{n}", str(number))


def _start_chapter(deps: GraphDeps, state: SessionState, chapter_idx: int) -> dict:
    """The click after a chapter end: the next chapter's title and intro, then its first step."""
    chapter = deps.chapters(state.get("locale", "de"))[chapter_idx]
    start = ChapterStartPart(title=chapter.title, intro=chapter.intro)
    turn = state["turn"].model_copy(update={"parts": [start, *state["turn"].parts]})
    patch = _lesson_step_patch(
        deps, {**state, "turn": turn, "chapter_idx": chapter_idx, "step_idx": 0}
    )
    return patch | {"chapter_idx": chapter_idx}
