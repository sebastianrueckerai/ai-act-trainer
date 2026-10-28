import random
from datetime import UTC, datetime

from app.content.models import Question
from app.files.tokens import certificate_file_part, full_file_part
from app.graph.brief import PRACTICE_TRIES, RECENT_MESSAGES, speaker_lines
from app.graph.deps import CompletionRecord, GraphDeps
from app.graph.draw import TEST_MIX, draw_questions
from app.graph.grade import grade_answer, practice_step_text, read_yes_no
from app.graph.reply import governed_reply
from app.graph.state import (
    GradedAnswer,
    InputHint,
    ModelAnswerCard,
    Mood,
    Phase,
    SessionState,
    TestState,
    UiEvent,
    hint_for_question,
)
from app.graph.tools import citations_from_text, without_inline_citations
from app.graph.working import announce
from app.i18n import t


def _active(state: SessionState) -> tuple[str, TestState] | None:
    """The attempt the student is in, or None when no question is open."""
    for key in ("practice", "test"):
        attempt = state.get(key)
        if attempt is not None:
            return key, attempt
    return None


def _no_attempt(state: SessionState, locale: str) -> dict:
    """The turn for a node that was reached with no question open."""
    turn = state["turn"].model_copy(
        update={
            "draft": t(locale, "no_question_open"),
            "closing_line": state.get("pending_prompt", ""),
            "input_hint": state.get("last_hint", InputHint(kind="text")),
        }
    )
    return {"turn": turn}


def _ask(
    state: SessionState,
    question: Question,
    lead: str = "",
    closing: str = "",
    ask: str = "",
    position_met: bool = False,
) -> dict:
    ask = ask or question.question
    draft = f"{lead}\n\n{ask}" if lead else ask
    turn = state["turn"].model_copy(
        update={
            "draft": draft,
            "input_hint": hint_for_question(question, position_met=position_met),
            "context_question": question.id,
            "closing_line": closing,
        }
    )
    return {"turn": turn, "pending_prompt": ask}


def _back_to_lesson(state: SessionState, locale: str, line: str) -> dict:
    """The turn that hands the student back to the chapter step they were on."""
    closing = t(locale, "step_prompt")
    turn = state["turn"].model_copy(
        update={
            "draft": line,
            "closing_line": closing,
            "input_hint": InputHint(kind="confirm", label=t(locale, "continue_label")),
        }
    )
    return {"phase": Phase.lesson, "turn": turn, "pending_prompt": closing}


def start_test_node(deps: GraphDeps):
    def node(state: SessionState) -> dict:
        locale = state.get("locale", "de")
        pending = state.get("pending_start_test", False)
        confirm = t(
            locale,
            "test_confirm",
            chapters=len(deps.chapters(locale)),
            total=sum(TEST_MIX.values()),
        )
        # The graded test never starts out of a lesson without being asked for. The
        # course-end offer already asks, so a request from there starts it at once.
        if not pending and Phase(state.get("phase", Phase.lesson)) is Phase.lesson:
            turn = state["turn"].model_copy(
                update={"draft": confirm, "input_hint": InputHint(kind="yes_no")}
            )
            return {"pending_start_test": True, "turn": turn}
        said = str(state["messages"][-1].content)
        if pending and read_yes_no(deps, confirm, said) is not True:
            turn = state["turn"].model_copy(
                update={
                    "draft": t(locale, "test_declined"),
                    "closing_line": state.get("pending_prompt", ""),
                    "input_hint": InputHint(kind="confirm", label=t(locale, "continue_label")),
                }
            )
            return {"pending_start_test": False, "turn": turn}
        attempts = state.get("attempts", 0) + 1
        questions = deps.locale_content(locale).questions
        question_ids = draw_questions(
            questions, random.Random(f"{state.get('session_seed', 'seed')}:{attempts}")
        )
        first = questions[question_ids[0]]
        intro = t(locale, "test_intro", total=len(question_ids))
        ask = _ask(state, first, intro)
        started = UiEvent(name="test_started", payload={"total": len(question_ids)})
        return {
            "phase": Phase.test,
            "attempts": attempts,
            "test": TestState(question_ids=question_ids),
            "practice": None,
            "pending_start_test": False,
            "pending_prompt": ask["pending_prompt"],
            "turn": ask["turn"].model_copy(update={"ui_events": [started]}),
            "streak_before_test": state.get("streak", 0),
        }

    return node


def verdict_payload(green: bool | None, settled: bool) -> dict:
    """What the page's verdict flash needs: green met a new required point, orange (None)
    met none but is on the right track, red met none; settled says whether the question
    closed (D118, D119)."""
    verdict = "correct" if green else ("partial" if green is None else "wrong")
    return {"verdict": verdict, "settled": settled}


def _reaction(deps: GraphDeps, state: SessionState, right: bool) -> str:
    """The persona's own line on a clear pick, drawn per turn, or the plain locale line when
    no persona speaks (D130)."""
    persona = deps.persona(state.get("persona_id"))
    kind = "right" if right else "wrong"
    if persona is None:
        return t(state.get("locale", "de"), f"choice_{kind}")
    seed = f"{state.get('session_seed', 'seed')}:{len(state.get('messages', []))}"
    return random.Random(seed).choice(persona.verdicts[kind])


def _picked(
    deps: GraphDeps, state: SessionState, question: Question, key: str, green: bool, ask: str
) -> dict:
    """A pick that leaves the question open answers on curated text: the persona's verdict
    line, then the follow-up after a right pick or the question again after a wrong one in
    the test. No writer, no checker and no rewrite run (D130)."""
    turn = state["turn"].model_copy(
        update={
            "draft": f"{_reaction(deps, state, green)}\n\n{ask}",
            "input_hint": hint_for_question(question, reveal=key == "practice", position_met=green),
            "context_question": question.id,
            "ui_events": state["turn"].ui_events
            + [UiEvent(name="answer_result", payload=verdict_payload(green, False))],
            "brief": "",
            "voiced": True,
        }
    )
    return {"turn": turn, "pending_prompt": ask}


def _advance(
    deps: GraphDeps,
    state: SessionState,
    graded: GradedAnswer,
    key: str,
    attempt: TestState,
    picked: bool = False,
) -> dict:
    locale = state.get("locale", "de")
    questions = deps.locale_content(locale).questions
    question = questions[graded.question_id]
    won = graded.correct and graded.tries == 1
    practice = key == "practice"
    events = [UiEvent(name="answer_result", payload=verdict_payload(graded.correct, True))]
    # A practice question celebrates both tries; the graded test keeps the first-try rule of
    # D70, where a second-try answer is settled, not won.
    if won or (practice and graded.correct):
        events.append(UiEvent(name="confetti", payload={}))
    if practice:
        if question.type == "free_text":
            # No card in the chapter (D89): the writer says the verdict and why, or gives
            # the answer after the last try. The sources go under the bubble.
            kind = "right" if graded.correct else "settled"
            brief, governed = governed_reply(deps, state, kind, question, graded, graded.tries)
            draft = governed.text
            brief_text = brief.text()
        else:
            # A chip's answer settles at once, and its reply is predetermined: the verdict
            # line and the curated model answer, no writer and no reply critic (D125).
            line = t(locale, "choice_right" if graded.correct else "choice_wrong")
            draft = f"{line}\n\n{question.model_answer}"
            brief_text = ""
        turn = state["turn"].model_copy(
            update={
                "draft": without_inline_citations(draft),
                "parts": state["turn"].parts
                + citations_from_text(deps, " ".join(question.citations)),
                "ui_events": state["turn"].ui_events + events,
                "brief": brief_text,
            }
        )
    else:
        card = ModelAnswerCard(
            question=question.question,
            model_answer=question.model_answer,
            explanation=question.explanation,
            citations=citations_from_text(deps, " ".join(question.citations)),
            correct=graded.correct,
            tries=graded.tries,
        )
        turn = state["turn"].model_copy(
            update={
                "parts": state["turn"].parts + [card],
                "ui_events": state["turn"].ui_events + events,
            }
        )
    advanced = attempt.model_copy(
        update={
            "answers": attempt.answers + [graded],
            "index": attempt.index + 1,
            "current_tries": 1,
            "nudges": 0,
        }
    )
    if not graded.correct:
        streak = 0
    elif won:
        streak = state.get("streak", 0) + 1
    else:
        # A second-try correct answer is settled, not won (Jo 4): it keeps the streak,
        # neither raising nor breaking it.
        streak = state.get("streak", 0)
    patch: dict = {
        key: advanced,
        "streak": streak,
        "mood": Mood.happy if graded.correct else Mood.disappointed,
        "turn": turn,
    }
    if practice:
        # The chapter goes on in this very turn; route_after_grade sends it to lesson_step.
        return patch | {"practice": None}
    index = advanced.index
    if index < len(attempt.question_ids):
        # The verdict lives on the answer card's badge; saying it again opened every bubble
        # with "Richtig!" twice.
        lead = t(locale, "next_question_lead", n=index + 1, total=len(attempt.question_ids))
        next_question = questions[attempt.question_ids[index]]
        asked = _ask({**state, "turn": turn}, next_question, lead, lead)
        if picked:
            # A pick's reaction is the persona's own line, not a rewrite (D130).
            line = _reaction(deps, state, graded.correct)
            asked["turn"] = asked["turn"].model_copy(
                update={"draft": f"{line}\n\n{asked['turn'].draft}", "voiced": True}
            )
        return patch | asked
    return patch


def _ask_on(
    deps: GraphDeps,
    state: SessionState,
    question: Question,
    graded: GradedAnswer,
    kind: str,
    attempt: TestState,
    key: str,
    ask: str,
    green: bool | None,
    is_attempt: bool,
    pick_open: bool = True,
) -> dict:
    """The turn that keeps the question open: the reply the critic loop shipped, the colour
    when there was an attempt (green True, orange None, miss False), and the question's own
    input again."""
    locale = state.get("locale", "de")
    brief, governed = governed_reply(
        deps, state, kind, question, graded, attempt.current_tries, attempt.nudges
    )
    draft = governed.text
    if key == "test" and not governed.shipped and "leak" in governed.faults:
        # A hint never reaches the graded test. The count is the correct reply there (D70);
        # a message that was no attempt gets no count, only the question again. A pick
        # never reaches the writer (D130).
        count = (
            t(
                locale,
                "test_count",
                met=len([p for p in question.rubric.must_texts if p in graded.matched])
                if question.rubric
                else 0,
                total=len(question.rubric.must_texts) if question.rubric else 0,
            )
            if graded.attempt
            else ""
        )
        draft = f"{count}\n\n{ask}" if count else ask
    elif (
        key == "practice"
        and not governed.shipped
        and ("leak" in governed.faults or (is_attempt and "question" in governed.faults))
    ):
        # A spent budget never ships a leak, and never a second question beside the ask
        # after an attempt: the page shows the colour, so the ask alone is a whole reply.
        # A question about the law keeps its answer unless that answer leaks.
        draft = ask
    events = list(state["turn"].ui_events)
    if is_attempt:
        events.append(UiEvent(name="answer_result", payload=verdict_payload(green, False)))
    # The reply ends by asking again, so its bubble poses the question.
    turn = state["turn"].model_copy(
        update={
            "draft": without_inline_citations(draft),
            "parts": state["turn"].parts + citations_from_text(deps, draft),
            "input_hint": hint_for_question(
                question, reveal=key == "practice", position_met=not pick_open
            ),
            "context_question": question.id,
            "ui_events": events,
            "brief": brief.text(),
        }
    )
    return {"turn": turn, "pending_prompt": ask, "mood": Mood.neutral}


def grade_node(deps: GraphDeps):
    def node(state: SessionState) -> dict:
        locale = state.get("locale", "de")
        active = _active(state)
        if active is None:
            return _no_attempt(state, locale)
        key, attempt = active
        announce(deps, state, "grading")
        questions = deps.locale_content(locale).questions
        question = questions[attempt.question_ids[attempt.index]]
        answer_text = state["messages"][-1].content
        practice = key == "practice"
        recent = speaker_lines(state["messages"][-RECENT_MESSAGES - 1 : -1])
        rubric = question.rubric
        position = rubric.must[0].point if question.type != "free_text" and rubric else None
        # The grid is open while the pick has not met the position point (D127); once it
        # has, the why points are typed answers.
        pick_open = question.type != "free_text" and (
            position is None or position not in attempt.prior_matched
        )
        typed = question.type == "free_text" or not pick_open
        graded = grade_answer(
            deps,
            question,
            answer_text,
            locale,
            practice_context=practice_step_text(deps, locale, question.id) if practice else None,
            recent=recent,
            typed=typed,
        )
        must = rubric.must_texts if rubric else []
        reason = None
        if pick_open and graded.attempt and graded.correct and graded.more and len(must) > 1:
            # A right pick that also gives a reason ("Ja, weil ..."): the reason is graded
            # against the why points, so it counts as a typed follow-up would (D130).
            reason = grade_answer(
                deps,
                question,
                answer_text,
                locale,
                practice_context=practice_step_text(deps, locale, question.id)
                if practice
                else None,
                recent=recent,
                typed=True,
            )
        gained: list[str] = []
        if rubric is not None:
            # The verdict for the question is the union of its tries, in rubric order. A
            # message that is no attempt earns nothing, whatever point it names in passing.
            met = set(attempt.prior_matched)
            if graded.attempt:
                if pick_open and graded.correct:
                    met.add(position)
                    gained = [position]
                    if reason is not None and reason.attempt:
                        gained += [p for p in must if p in reason.matched and p not in met]
                        met |= set(reason.matched)
                elif typed:
                    gained = [p for p in must if p in graded.matched and p not in met]
                    met |= set(graded.matched)
            points = must + list(rubric.should)
            # A pick's own verdict says the position is right, not that the question is
            # done; only a typed answer may be credited in spirit beyond its points (D87).
            complete = all(p in met for p in must)
            lenient = (graded.correct and typed) or (reason is not None and reason.correct)
            graded = graded.model_copy(
                update={
                    "matched": [p for p in points if p in met],
                    "missing": [p for p in must if p not in met],
                    "correct": graded.attempt and (complete or lenient),
                }
            )
        ask = (rubric.next_ask(graded.matched) if rubric else None) or question.question
        if not graded.attempt:
            asked = _ask_on(
                deps,
                state,
                question,
                graded,
                "not_an_attempt",
                attempt,
                key,
                ask,
                None,
                False,
                pick_open,
            )
            return asked | {key: attempt}
        # A pick settles the practice question, right or wrong; the test keeps a wrong
        # pick open and guides. A typed answer settles the moment the union says correct,
        # or after its last miss, five, in practice (D70, D127, D128).
        green = bool(gained)
        orange = not green and graded.on_track
        last_try = practice and attempt.current_tries >= PRACTICE_TRIES
        if (
            graded.correct
            or (practice and pick_open and not green)
            or (not green and not orange and last_try)
        ):
            settled = graded.model_copy(
                update={
                    "hint_shown": attempt.current_tries > 1,
                    "tries": attempt.current_tries,
                }
            )
            return _advance(deps, state, settled, key, attempt, picked=pick_open)
        # Only a miss uses a try; oranges are counted for the hint ladder.
        if green:
            outcome = "partial"
        elif not practice:
            outcome = "wrong" if pick_open else "test_retry"
        else:
            outcome = "on_track" if orange else "wrong"
        colour = True if green else (None if orange else False)
        if pick_open:
            result = _picked(deps, state, question, key, green, ask)
        else:
            result = _ask_on(
                deps, state, question, graded, outcome, attempt, key, ask, colour, True, False
            )
        result[key] = attempt.model_copy(
            update={
                "current_tries": attempt.current_tries + (0 if green or orange else 1),
                "nudges": 0 if green else attempt.nudges + (1 if orange else 0),
                "prior_matched": graded.matched,
            }
        )
        return result | {
            "streak": 0 if not green and not orange else state.get("streak", 0),
            "mood": Mood.happy if green else (Mood.neutral if orange else Mood.disappointed),
        }

    return node


def skip_node(deps: GraphDeps):
    def node(state: SessionState) -> dict:
        locale = state.get("locale", "de")
        active = _active(state)
        if active is None:
            return _no_attempt(state, locale)
        key, attempt = active
        question = deps.locale_content(locale).questions[attempt.question_ids[attempt.index]]
        missing = (
            [p for p in question.rubric.must_texts if p not in attempt.prior_matched]
            if question.rubric
            else []
        )
        graded = GradedAnswer(
            question_id=question.id,
            answer="",
            correct=False,
            missing=missing,
        )
        return _advance(deps, state, graded, key, attempt)

    return node


def quit_test_node(deps: GraphDeps):
    def node(state: SessionState) -> dict:
        locale = state.get("locale", "de")
        if not state.get("pending_quit"):
            turn = state["turn"].model_copy(
                update={
                    "draft": t(locale, "quit_confirm"),
                    "input_hint": InputHint(kind="yes_no"),
                }
            )
            return {"pending_quit": True, "turn": turn}
        active = _active(state)
        if active is None:
            return {"pending_quit": False} | _no_attempt(state, locale)
        key, attempt = active
        question = deps.locale_content(locale).questions[attempt.question_ids[attempt.index]]
        said = str(state["messages"][-1].content)
        if read_yes_no(deps, t(locale, "quit_confirm"), said) is True:
            # Quitting the test discards its progress, but not a practice streak the
            # student already had before the test started (Jo 18).
            streak = state.get("streak_before_test", 0) if key == "test" else 0
            done = set(state.get("chapters_done", []))
            # A chapter is still open, so the student came here out of the course and
            # goes back to it. Only a student who has finished it lands in free.
            if any(chapter.id not in done for chapter in deps.chapters(locale)):
                return {key: None, "pending_quit": False, "streak": streak} | _back_to_lesson(
                    state, locale, t(locale, "quit_to_lesson")
                )
            turn = state["turn"].model_copy(update={"draft": t(locale, "quit_done")})
            return {
                key: None,
                "pending_quit": False,
                "streak": streak,
                "phase": Phase.free,
                "turn": turn,
                "pending_prompt": t(locale, "recommend_test"),
            }
        # A question with earlier tries is re-asked at its first open point.
        ask = question.question
        if question.rubric and (attempt.prior_matched or attempt.current_tries > 1):
            ask = question.rubric.next_ask(attempt.prior_matched) or ask
        # The grid returns unless the pick already met the position (D127).
        position_met = bool(question.rubric and attempt.prior_matched)
        return {"pending_quit": False} | _ask(
            state, question, t(locale, "quit_kept"), ask=ask, position_met=position_met
        )

    return node


def _record_completion(deps: GraphDeps, state: SessionState) -> None:
    if deps.record_completion is None or state.get("user_id") is None:
        return
    if state.get("practice") is not None:
        return
    deps.record_completion(
        CompletionRecord(
            user_id=state["user_id"],
            course_version=deps.content.manifest.course_version,
            law_version=deps.law_version,
            locale=state.get("locale", "de"),
            persona_id=state.get("persona_id"),
            passed_at=datetime.now(tz=UTC),
        )
    )


def finish_test_node(deps: GraphDeps):
    def node(state: SessionState) -> dict:
        locale = state.get("locale", "de")
        attempt = state["test"]
        score = sum(1 for answer in attempt.answers if answer.correct)
        total = len(attempt.answers)
        result = UiEvent(name="test_result", payload={"score": score, "total": total})
        parts = [full_file_part(deps.settings, locale, deps.content.manifest.course_version)]
        if deps.settings.feature_certificate and state.get("user_id") is not None:
            parts.append(
                certificate_file_part(
                    deps.settings,
                    user_id=state["user_id"],
                    score=score,
                    total=total,
                    passed=True,
                    passed_on=datetime.now(tz=UTC).date().isoformat(),
                    locale=locale,
                    course_version=deps.content.manifest.course_version,
                    law_version=deps.law_version,
                )
            )
        turn = state["turn"].model_copy(
            update={
                "draft": t(locale, "finale", score=score, total=total),
                "ui_events": state["turn"].ui_events + [result, UiEvent(name="finale", payload={})],
                "parts": state["turn"].parts + parts,
            }
        )
        _record_completion(deps, state)
        return {
            "phase": Phase.done,
            "mood": Mood.happy,
            "turn": turn,
            "pending_prompt": t(locale, "done_prompt"),
        }

    return node
