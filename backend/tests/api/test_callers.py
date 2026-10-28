"""Who spends whose money: guests on the pool, invited accounts on their own key, the
gates in front of a turn, and the notice state the session and the stream carry."""

import asyncio
import json
import re
from collections.abc import Iterator, Mapping
from datetime import timedelta

import httpx
import openai
import pytest
from sqlalchemy import select, update

from app.auth.invite import invite_hash
from app.llm.models import caller_key
from app.main import clean_guests, purge_transcripts
from app.storage.models import TrainingSession, TurnLog, User, utcnow
from app.storage.repository import SqlAlchemyRepository
from tests.api.conftest import SHIP
from tests.fakes.proxy import FakeProxy

RESET = "2026-10-12T00:00:00+00:00"
RESET_MONTH = "2026-11-01T00:00:00+00:00"
OK = {"state": "ok", "scope": None, "resets_at": None}


def _budget_error() -> openai.BadRequestError:
    message = "ExceededBudget: User=acct-jo over budget. Spend=8.01, Budget=8.0"
    request = httpx.Request("POST", "http://proxy:4000/v1/chat/completions")
    body = {"message": message, "type": None, "param": None, "code": "400"}
    response = httpx.Response(400, request=request, json={"error": body})
    return openai.BadRequestError(message, response=response, body=body)


BUDGET_SCRIPT = {
    "triage": _budget_error(),
    "persona": "<echo>",
    "critic": SHIP,
    "voice_critic": SHIP,
}


class KeyRecorder(Mapping):
    """The scripted model for both roles, noting the caller key each lookup ran under:
    the moment the real per-key mapping picks its model."""

    def __init__(self, model) -> None:
        self.model = model
        self.keys: list[str | None] = []

    def __getitem__(self, role):
        self.keys.append(caller_key.get())
        return self.model

    def __iter__(self) -> Iterator[str]:
        return iter(("strong", "fast"))

    def __len__(self) -> int:
        return 2


def _limit(scope: str, resets_at: str | None = None) -> dict:
    budget = {"state": "exhausted", "scope": scope, "resets_at": resets_at}
    return {"event": "error", "code": "limit", "message": "chat.limit", "budget": budget}


def _events(client, url: str, body: dict | None = None) -> list[dict]:
    with client.stream("POST", url, json=body) as response:
        assert response.status_code == 200
        lines = list(response.iter_lines())
    return [json.loads(line[6:]) for line in lines if line.startswith("data: ")]


def _turn(client, session_id: int) -> list[dict]:
    return _events(client, f"/api/chat/{session_id}/turns", {"text": "weiter"})


def _session(client) -> dict:
    response = client.post("/api/session", json={"persona_id": "clerk"})
    assert response.status_code == 200
    return response.json()


def _with_repo(client, act):
    with client.app.state.session_factory() as db:
        result = act(SqlAlchemyRepository(db))
        db.commit()
        return result


def _account(client, fake: FakeProxy, name: str = "Jo") -> tuple[str, str]:
    """A named account as tools/account.py leaves it, and its invite token."""
    subject, token = f"acct-{name.lower()}", f"token-of-{name.lower()}"
    key = fake.add(subject, day=2.0, month=8.0)
    _with_repo(
        client,
        lambda repo: repo.add_account(
            subject, "account", name, key, subject, invite_hash(token), 2.0, 8.0
        ),
    )
    return subject, token


def _pool(client, fake: FakeProxy) -> str:
    key = fake.add("pool-demo", day=2.0, month=6.0)
    _with_repo(
        client,
        lambda repo: repo.add_account(
            "pool-demo", "pool", "Demo-Pool", key, "pool-demo", None, 2.0, 6.0
        ),
    )
    return key


def _sign_in(client, token: str) -> None:
    assert client.post("/api/auth/invite/login", json={"token": token}).status_code == 200


def _guest(client) -> str:
    assert client.post("/api/auth/guest").status_code == 200
    return client.get("/api/me").json()["principal"]["subject"]


def test_purge_transcripts_drops_an_idle_named_users_threads_and_keeps_the_pass_record(
    budget_client, fake_proxy
):
    app = budget_client.app
    _pool(budget_client, fake_proxy)
    subject, token = _account(budget_client, fake_proxy)
    _sign_in(budget_client, token)

    session_id = _session(budget_client)["id"]
    assert _turn(budget_client, session_id)[-1]["event"] == "message"
    with app.state.session_factory() as db:
        uid = db.scalar(select(User.id).where(User.subject == subject))
        SqlAlchemyRepository(db).record_completion(uid, "0.1.0", "law", "de", "clerk", utcnow())
        db.commit()

    forty_days_ago = utcnow() - timedelta(days=40)
    with app.state.session_factory() as db:
        uid = db.scalar(select(User.id).where(User.subject == subject))
        db.execute(update(User).where(User.id == uid).values(created_at=forty_days_ago))
        db.execute(update(TurnLog).where(TurnLog.user_id == uid).values(at=forty_days_ago))
        db.commit()
        thread = db.scalar(select(TrainingSession.thread_id).where(TrainingSession.user_id == uid))

    assert asyncio.run(purge_transcripts(app)) == 1

    with app.state.session_factory() as db:
        assert db.scalars(select(User.subject)).all() == [subject]
        assert db.scalars(select(TrainingSession.id)).all() == []
        assert db.scalars(select(TurnLog.id)).all() == []
        assert SqlAlchemyRepository(db).latest_completion(uid) is not None
    values = asyncio.run(app.state.graph.aget_state({"configurable": {"thread_id": thread}})).values
    assert values == {}


def test_options_on_the_dev_backend(client) -> None:
    assert client.get("/api/auth/options").json() == {"backend": "dev", "guest": False}


def test_options_on_the_public_demo(budget_client) -> None:
    assert budget_client.get("/api/auth/options").json() == {"backend": "invite", "guest": True}


def test_the_guest_door_is_closed_without_the_flag(client) -> None:
    assert client.post("/api/auth/guest").status_code == 404


def test_a_guest_signs_in_as_a_fresh_principal_each_time(budget_client) -> None:
    first = _guest(budget_client)
    principal = budget_client.get("/api/me").json()["principal"]

    assert re.fullmatch(r"guest-[A-Za-z0-9_-]{22}", first)
    assert principal == {
        "subject": first,
        "name": "Gast",
        "email": None,
        "groups": ["guest"],
        "roles": ["student"],
    }
    assert _guest(budget_client) != first


def test_an_invite_signs_in_as_its_account_until_it_is_revoked(budget_client, fake_proxy) -> None:
    subject, token = _account(budget_client, fake_proxy)

    unknown = budget_client.post("/api/auth/invite/login", json={"token": "not-a-token"})
    assert unknown.status_code == 401
    _sign_in(budget_client, token)
    assert budget_client.get("/api/me").json()["principal"] == {
        "subject": "acct-jo",
        "name": "Jo",
        "email": None,
        "groups": ["account"],
        "roles": ["student"],
    }

    _with_repo(budget_client, lambda repo: repo.revoke_account(subject))
    budget_client.post("/api/auth/logout")
    revoked = budget_client.post("/api/auth/invite/login", json={"token": token})
    assert revoked.status_code == 401
    assert budget_client.get("/api/auth/dev/users").status_code == 404


def test_the_callers_key_reaches_every_model_lookup(budget_client, fake_proxy) -> None:
    _, token = _account(budget_client, fake_proxy)
    _pool(budget_client, fake_proxy)
    deps = budget_client.app.state.deps
    recorder = KeyRecorder(deps.models["fast"])
    deps.models = recorder

    _sign_in(budget_client, token)
    assert _turn(budget_client, _session(budget_client)["id"])[-1]["event"] == "message"
    assert recorder.keys and set(recorder.keys) == {"sk-acct-jo"}

    recorder.keys.clear()
    _guest(budget_client)
    assert _turn(budget_client, _session(budget_client)["id"])[-1]["event"] == "message"
    assert recorder.keys and set(recorder.keys) == {"sk-pool-demo"}


def test_a_caller_without_a_live_key_is_refused_before_any_model(budget_client, fake_proxy):
    model = budget_client.app.state.deps.models["fast"]

    _guest(budget_client)
    session = _session(budget_client)
    assert session["budget"] == {"state": "exhausted", "scope": "global", "resets_at": None}
    assert _turn(budget_client, session["id"]) == [_limit("global")]

    subject, token = _account(budget_client, fake_proxy)
    _sign_in(budget_client, token)
    session_id = _session(budget_client)["id"]
    _with_repo(budget_client, lambda repo: repo.revoke_account(subject))
    assert _turn(budget_client, session_id) == [_limit("global")]
    assert model.prompts == []


def test_the_session_carries_an_exhausted_day_with_its_reset_time(budget_client, fake_proxy):
    _, token = _account(budget_client, fake_proxy)
    fake_proxy.keys["sk-acct-jo"].update(spend=2.0, budget_reset_at=RESET)

    _sign_in(budget_client, token)
    exhausted = {"state": "exhausted", "scope": "day", "resets_at": "2026-10-12T00:00:00Z"}
    assert _session(budget_client)["budget"] == exhausted
    assert budget_client.get("/api/session").json()["budget"] == exhausted


def test_a_guest_session_shows_the_pools_month_and_a_fresh_account_ok(budget_client, fake_proxy):
    _pool(budget_client, fake_proxy)
    fake_proxy.users["pool-demo"].update(spend=6.0, budget_reset_at=RESET_MONTH)
    _, token = _account(budget_client, fake_proxy)

    _guest(budget_client)
    assert _session(budget_client)["budget"] == {
        "state": "exhausted",
        "scope": "pool_month",
        "resets_at": "2026-11-01T00:00:00Z",
    }
    _sign_in(budget_client, token)
    assert _session(budget_client)["budget"] == OK


def test_with_budgets_off_the_session_is_ok(scripted_client) -> None:
    scripted_client.post("/api/auth/dev/login", json={"subject": "anna"})
    assert _session(scripted_client)["budget"] == OK


def test_the_eleventh_guest_waits_for_a_seat_and_an_account_never_does(budget_client, fake_proxy):
    _pool(budget_client, fake_proxy)
    _, token = _account(budget_client, fake_proxy)

    def seat_ten(repo) -> list[int]:
        ids = [repo.upsert_user(f"guest-seat{n}", "Gast", None, ["guest"]).id for n in range(10)]
        for uid in ids:
            repo.log_turn(uid)
        return ids

    seated = _with_repo(budget_client, seat_ten)
    _guest(budget_client)
    guest_cookie = budget_client.cookies["trainer_session"]
    guest_session = _session(budget_client)["id"]
    assert _turn(budget_client, guest_session) == [_limit("seats")]

    _sign_in(budget_client, token)
    assert _turn(budget_client, _session(budget_client)["id"])[-1]["event"] == "message"

    # Ten minutes without a turn frees every seat.
    eleven_minutes_ago = utcnow() - timedelta(minutes=11)
    with budget_client.app.state.session_factory() as db:
        db.execute(update(TurnLog).where(TurnLog.user_id.in_(seated)).values(at=eleven_minutes_ago))
        db.commit()
    budget_client.cookies.set("trainer_session", guest_cookie)
    assert _turn(budget_client, guest_session)[-1]["event"] == "message"


def test_a_guest_has_the_lower_turn_count(budget_client, fake_proxy) -> None:
    budget_client.app.state.settings.turn_limit_guest_day = 1
    budget_client.app.state.settings.turn_limit_user_day = 50
    _pool(budget_client, fake_proxy)
    _, token = _account(budget_client, fake_proxy)

    _guest(budget_client)
    guest_session = _session(budget_client)["id"]
    assert _turn(budget_client, guest_session)[-1]["event"] == "message"
    assert _turn(budget_client, guest_session) == [_limit("global")]

    _sign_in(budget_client, token)
    account_session = _session(budget_client)["id"]
    for _ in range(2):
        assert _turn(budget_client, account_session)[-1]["event"] == "message"


@pytest.mark.parametrize("budget_client", [BUDGET_SCRIPT], indirect=True)
def test_a_budget_refusal_mid_turn_ends_the_stream_as_the_callers_day(budget_client, fake_proxy):
    _, token = _account(budget_client, fake_proxy)
    _sign_in(budget_client, token)
    session = _session(budget_client)
    assert session["budget"] == OK
    # Within the read cache's thirty seconds: the refusal reads the proxy afresh.
    fake_proxy.keys["sk-acct-jo"].update(spend=2.01, budget_reset_at=RESET)

    events = _turn(budget_client, session["id"])

    assert events[-1] == _limit("day", "2026-10-12T00:00:00Z")
    assert all(event["event"] != "message" for event in events)


@pytest.mark.parametrize("budget_client", [BUDGET_SCRIPT], indirect=True)
def test_a_budget_refusal_the_callers_spend_does_not_explain_is_the_proxy_wide_cap(
    budget_client, fake_proxy
):
    _, token = _account(budget_client, fake_proxy)
    _sign_in(budget_client, token)

    events = _turn(budget_client, _session(budget_client)["id"])

    assert events[-1] == _limit("global")


def test_clean_guests_deletes_an_idle_guest_and_keeps_a_fresh_one(budget_client, fake_proxy):
    app = budget_client.app
    _pool(budget_client, fake_proxy)

    idle = _guest(budget_client)
    idle_session = _session(budget_client)["id"]
    assert _turn(budget_client, idle_session)[-1]["event"] == "message"
    fresh = _guest(budget_client)
    fresh_session = _session(budget_client)["id"]

    seven_hours_ago = utcnow() - timedelta(hours=7)
    with app.state.session_factory() as db:
        idle_id = db.scalar(select(User.id).where(User.subject == idle))
        db.execute(update(User).where(User.id == idle_id).values(created_at=seven_hours_ago))
        db.execute(update(TurnLog).where(TurnLog.user_id == idle_id).values(at=seven_hours_ago))
        db.commit()
        threads = dict(db.execute(select(TrainingSession.id, TrainingSession.thread_id)).all())

    assert asyncio.run(clean_guests(app)) == 1

    with app.state.session_factory() as db:
        assert db.scalars(select(User.subject)).all() == [fresh]
        assert db.scalars(select(TrainingSession.id)).all() == [fresh_session]
        assert db.scalars(select(TurnLog.user_id).where(TurnLog.user_id == idle_id)).all() == []

    def values(session_id: int) -> dict:
        config = {"configurable": {"thread_id": threads[session_id]}}
        return asyncio.run(app.state.graph.aget_state(config)).values

    assert values(idle_session) == {}
    assert values(fresh_session) != {}
