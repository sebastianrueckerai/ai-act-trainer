import time

from structlog.testing import capture_logs

from app.graph.critic import Critique
from app.graph.govern import RETRIES, Governed, deadline, govern
from app.graph.state import TurnScratch


def _judge(*verdicts: Critique):
    queue = list(verdicts)
    seen: list[str] = []

    def judge(draft: str) -> Critique:
        seen.append(draft)
        return queue.pop(0)

    judge.seen = seen
    return judge


def _produce():
    calls: list[tuple[str | None, str | None]] = []

    def produce(previous: str | None, notes: str | None) -> str:
        calls.append((previous, notes))
        return f"draft {len(calls)}"

    produce.calls = calls
    return produce


def _far() -> float:
    return time.monotonic() + 60


def test_a_shipped_first_draft_costs_one_call_each_and_no_budget_log():
    produce, judge = _produce(), _judge(Critique(verdict="ship", score=5))
    with capture_logs() as logs:
        result = govern("reply", produce, judge, _far())
    assert result == Governed(text="draft 1", shipped=True, faults=[])
    assert produce.calls == [(None, None)]
    assert judge.seen == ["draft 1"]
    assert [entry["event"] for entry in logs] == []


def test_a_retry_carries_the_rejected_draft_and_the_notes():
    produce = _produce()
    judge = _judge(
        Critique(verdict="retry", faults=["leak"], notes="Nenn den Punkt nicht.", score=2),
        Critique(verdict="ship", score=4),
    )
    result = govern("reply", produce, judge, _far())
    assert result.text == "draft 2" and result.shipped
    assert produce.calls == [(None, None), ("draft 1", "Nenn den Punkt nicht.")]


def test_two_retries_are_the_last_and_the_best_scored_draft_ships():
    produce = _produce()
    judge = _judge(
        Critique(verdict="retry", faults=["leak"], notes="a", score=2),
        Critique(verdict="retry", faults=["repeat"], notes="b", score=4),
        Critique(verdict="retry", faults=["leak", "question"], notes="c", score=3),
    )
    with capture_logs() as logs:
        result = govern("reply", produce, judge, _far())
    assert RETRIES == 2
    assert len(produce.calls) == 3
    assert result == Governed(text="draft 2", shipped=False, faults=["repeat"])
    budget = [entry for entry in logs if entry["event"] == "critic_budget"]
    assert budget == [
        {
            "event": "critic_budget",
            "log_level": "info",
            "stage": "reply",
            "faults": ["repeat"],
            "score": 4,
            "drafts": 3,
            "error": "",
        }
    ]


def test_a_later_draft_wins_a_tie():
    produce = _produce()
    judge = _judge(
        Critique(verdict="retry", faults=["leak"], score=3),
        Critique(verdict="retry", faults=["repeat"], score=3),
        Critique(verdict="retry", faults=["unhelpful"], score=3),
    )
    assert govern("reply", produce, judge, _far()).text == "draft 3"


def test_a_spent_deadline_stops_the_retries():
    produce = _produce()
    judge = _judge(Critique(verdict="retry", faults=["leak"], notes="x", score=1))
    result = govern("voice", produce, judge, time.monotonic() - 1)
    assert result == Governed(text="draft 1", shipped=False, faults=["leak"])
    assert len(produce.calls) == 1


def test_the_deadline_is_the_turn_start_plus_the_budget(settings):
    turn = TurnScratch()
    state = {"turn": turn}
    assert deadline(state, settings.model_copy(update={"turn_budget_seconds": 7})) == (
        turn.started_at + 7
    )


def test_the_budget_is_a_setting(settings):
    assert settings.turn_budget_seconds == 20


def test_a_retry_that_raises_ships_the_best_draft_and_logs_it():
    calls: list[int] = []

    def produce(previous: str | None, notes: str | None) -> str:
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("proxy down")
        return f"draft {len(calls)}"

    judge = _judge(Critique(verdict="retry", faults=["leak"], notes="x", score=3))
    with capture_logs() as logs:
        result = govern("reply", produce, judge, _far())
    assert result == Governed(text="draft 1", shipped=False, faults=["leak"])
    assert len(calls) == 2
    budget = [entry for entry in logs if entry["event"] == "critic_budget"]
    assert len(budget) == 1
    assert budget[0]["error"] == "RuntimeError: proxy down"


def test_a_first_draft_that_raises_still_raises():
    import pytest

    def produce(previous: str | None, notes: str | None) -> str:
        raise RuntimeError("proxy down")

    with pytest.raises(RuntimeError):
        govern("reply", produce, _judge(), _far())


def test_the_loop_names_each_step_as_it_starts():
    steps: list[str] = []
    verdicts = iter(
        [
            Critique(verdict="retry", faults=["unhelpful"], notes="n", score=2),
            Critique(verdict="ship", score=5),
        ]
    )
    result = govern(
        "reply",
        lambda previous, notes: "draft",
        lambda draft: next(verdicts),
        time.monotonic() + 60,
        steps.append,
    )
    assert result.shipped
    assert steps == ["writing", "checking", "rewriting", "checking"]
