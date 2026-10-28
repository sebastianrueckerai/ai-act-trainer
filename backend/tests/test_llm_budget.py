import json
from datetime import UTC, datetime

import httpx
import openai
import pytest

from app.llm.budget import BudgetState, caller_state, is_budget_error
from tests.fakes.proxy import ADMIN_KEY, FakeProxy

RESET_DAY = "2026-10-12T00:00:00"
RESET_MONTH = "2026-11-01T00:00:00+00:00"


def _budget_error(message: str, error_type: str | None) -> openai.BadRequestError:
    request = httpx.Request("POST", "http://proxy:4000/v1/chat/completions")
    body = {"message": message, "type": error_type, "param": None, "code": "400"}
    response = httpx.Response(400, request=request, json={"error": body})
    return openai.BadRequestError(message, response=response, body=body)


def test_the_client_talks_to_the_proxy_root_with_the_admin_key():
    fake = FakeProxy()
    proxy = fake.client()

    proxy.new_user("acct-jo", 8.0)
    key = proxy.generate_key("acct-jo", 2.0, key_alias="acct-jo")
    proxy.delete_key(key)

    assert [(r.method, str(r.url)) for r in fake.requests] == [
        ("POST", "http://proxy:4000/user/new"),
        ("POST", "http://proxy:4000/key/generate"),
        ("POST", "http://proxy:4000/key/delete"),
    ]
    assert all(r.headers["authorization"] == f"Bearer {ADMIN_KEY}" for r in fake.requests)
    assert json.loads(fake.requests[0].content) == {
        "user_id": "acct-jo",
        "max_budget": 8.0,
        "budget_duration": "1mo",
        "auto_create_key": False,
    }
    assert json.loads(fake.requests[1].content) == {
        "user_id": "acct-jo",
        "max_budget": 2.0,
        "budget_duration": "1d",
        "key_alias": "acct-jo",
    }
    assert key == "sk-acct-jo"
    assert json.loads(fake.requests[2].content) == {"keys": ["sk-acct-jo"]}
    assert fake.keys == {}


def test_the_two_reads_carry_spend_budget_and_reset_time_in_utc():
    fake = FakeProxy()
    key = fake.add("acct-jo", day=2.0, month=8.0)
    fake.keys[key].update(spend=0.5, budget_reset_at=RESET_DAY)
    fake.users["acct-jo"].update(spend=3.25, budget_reset_at=RESET_MONTH)
    proxy = fake.client()

    day = proxy.key_info(key)
    month = proxy.user_info("acct-jo")

    assert (day.spend, day.max_budget) == (0.5, 2.0)
    # The proxy prints a reset time without an offset; it means UTC.
    assert day.budget_reset_at == datetime(2026, 10, 12, tzinfo=UTC)
    assert (month.spend, month.max_budget) == (3.25, 8.0)
    assert month.budget_reset_at == datetime(2026, 11, 1, tzinfo=UTC)
    assert str(fake.requests[0].url) == "http://proxy:4000/key/info?key=sk-acct-jo"
    assert str(fake.requests[1].url) == "http://proxy:4000/user/info?user_id=acct-jo"


def test_a_read_is_cached_for_thirty_seconds_per_key():
    fake = FakeProxy()
    key = fake.add("acct-jo", day=2.0, month=8.0)
    now = [100.0]
    proxy = fake.client(clock=lambda: now[0])

    proxy.key_info(key)
    fake.keys[key]["spend"] = 1.0
    now[0] = 129.9
    assert proxy.key_info(key).spend == 0.0
    now[0] = 130.0
    assert proxy.key_info(key).spend == 1.0
    assert len(fake.requests) == 2

    fake.keys[key]["spend"] = 1.5
    assert proxy.key_info(key, fresh=True).spend == 1.5
    assert len(fake.requests) == 3


def test_a_missing_key_raises():
    with pytest.raises(httpx.HTTPStatusError):
        FakeProxy().client().key_info("sk-gone")


def test_a_key_with_less_than_a_turn_left_is_spent():
    # The proxy refuses the call whose estimate would cross the line, so 1.995 of 2.0 is
    # the end of the day; 1.98 still has room for one more turn.
    fake = FakeProxy()
    key = fake.add("acct-jo", day=2.0, month=8.0)
    proxy = fake.client()

    fake.keys[key].update(spend=1.98, budget_reset_at=RESET_DAY)
    assert caller_state(proxy, key, "acct-jo", guest=False, fresh=True) == BudgetState()

    fake.keys[key].update(spend=1.995, budget_reset_at=RESET_DAY)
    assert caller_state(proxy, key, "acct-jo", guest=False, fresh=True).scope == "day"


def test_the_state_names_the_month_before_the_day_and_the_pool_for_a_guest():
    fake = FakeProxy()
    key = fake.add("pool-x", day=2.0, month=6.0)
    proxy = fake.client()

    assert caller_state(proxy, key, "pool-x", guest=True) == BudgetState()

    fake.keys[key].update(spend=2.0, budget_reset_at=RESET_DAY)
    assert caller_state(proxy, key, "pool-x", guest=True, fresh=True) == BudgetState(
        state="exhausted", scope="pool_day", resets_at=datetime(2026, 10, 12, tzinfo=UTC)
    )
    assert caller_state(proxy, key, "pool-x", guest=False, fresh=True).scope == "day"

    fake.users["pool-x"].update(spend=6.5, budget_reset_at=RESET_MONTH)
    assert caller_state(proxy, key, "pool-x", guest=True, fresh=True) == BudgetState(
        state="exhausted", scope="pool_month", resets_at=datetime(2026, 11, 1, tzinfo=UTC)
    )
    assert caller_state(proxy, key, "pool-x", guest=False, fresh=True).scope == "month"


def test_a_budget_error_is_known_by_its_marker_or_its_type_through_the_chain():
    by_message = _budget_error("ExceededBudget: User=acct-jo over budget.", None)
    by_token = _budget_error("ExceededTokenBudget: Current spend for token: 2.1", None)
    by_type = _budget_error("Budget has been exceeded! Current cost: 5.2", "budget_exceeded")
    assert is_budget_error(by_message)
    assert is_budget_error(by_token)
    assert is_budget_error(by_type)

    try:
        try:
            raise by_message
        except openai.BadRequestError as inner:
            raise RuntimeError("the node failed") from inner
    except RuntimeError as outer:
        assert is_budget_error(outer)

    assert not is_budget_error(_budget_error("tool_choice names no tool", "invalid_request"))
    assert not is_budget_error(RuntimeError("ExceededBudget"))
