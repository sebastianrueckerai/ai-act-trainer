from app.graph.state import Guard, Intent, Phase, SessionState


def route_after_triage(state: SessionState) -> str:
    turn = state["turn"]
    if turn.guard != Guard.ok:
        return "react"
    if state.get("pending_quit"):
        return "quit_test"
    if state.get("pending_start_test"):
        return "start_test"
    phase, intent = Phase(state["phase"]), turn.intent
    # While a question is open, an answer, a question about the law, a plea for help and
    # chatter are all one writer's turn (D108): they go to grade, whatever the fast triage
    # model labelled them.
    if phase is Phase.test:
        if intent is Intent.skip:
            return "skip"
        if intent is Intent.quit_test:
            return "quit_test"
        if intent in (Intent.continue_, Intent.start_test):
            return "react"
        return "grade"
    practice = state.get("practice")
    if intent is Intent.help and practice is None:
        return "help"
    if phase is Phase.lesson:
        if practice is not None and intent not in (
            Intent.skip,
            Intent.start_test,
            Intent.quit_test,
        ):
            return "grade"
        if intent is Intent.skip:
            # Only a pending practice question can be skipped. Skipping a step is continuing.
            return "skip" if practice else "lesson_step"
        if intent is Intent.start_test:
            return "start_test"
        if intent is Intent.question:
            return "free_question"
        return "lesson_step"
    if phase is Phase.free:
        if intent is Intent.question:
            return "free_question"
        if intent is Intent.start_test:
            return "start_test"
        return "start_test" if intent is Intent.continue_ else "free_question"
    if intent is Intent.start_test:
        return "start_test"
    if intent is Intent.question:
        return "free_question"
    return "react"


def route_after_grade(state: SessionState) -> str:
    test = state.get("test")
    if test is not None and not test.practice and test.index >= len(test.question_ids):
        return "finish_test"
    graded = any(event.name == "answer_result" for event in state["turn"].ui_events)
    lesson = Phase(state.get("phase", Phase.lesson)) is Phase.lesson
    if graded and lesson and state.get("practice") is None:
        # A settled practice question hands straight back to teaching, in the same turn (D89).
        return "lesson_step"
    return "persona"
