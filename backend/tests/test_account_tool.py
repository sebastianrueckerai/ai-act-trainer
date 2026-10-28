"""tools/account.py against the fake proxy: the pool, a named account, the listing, revoking."""

import hashlib
import importlib.util
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.storage.db import make_engine, make_session_factory
from app.storage.migrate import run_migrations
from app.storage.repository import SqlAlchemyRepository
from tests.fakes.proxy import FakeProxy

_spec = importlib.util.spec_from_file_location(
    "account_tool", Path(__file__).resolve().parents[2] / "tools" / "account.py"
)
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[SqlAlchemyRepository]:
    url = f"sqlite:///{tmp_path / 'accounts.db'}"
    run_migrations(url)
    with make_session_factory(make_engine(url))() as session:
        yield SqlAlchemyRepository(session)


def test_new_prints_the_invite_once_and_stores_only_its_hash(repo) -> None:
    fake = FakeProxy()

    link = tool.new_account(repo, fake.client(), "https://demo.example/", "Jo Example", 2.0, 8.0)

    prefix = "https://demo.example/?invite="
    assert link.startswith(prefix)
    token = link.removeprefix(prefix)
    assert len(token) == 32
    [account] = repo.list_accounts()
    assert account.subject.startswith("acct-")
    assert (account.kind, account.name, account.day_usd, account.month_usd) == (
        "account",
        "Jo Example",
        2.0,
        8.0,
    )
    assert account.invite_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in {account.subject, account.litellm_key, account.litellm_user_id}
    assert account.litellm_user_id == account.subject
    assert account.litellm_key == f"sk-{account.subject}"
    assert fake.users[account.subject] == {
        "spend": 0.0,
        "max_budget": 8.0,
        "budget_duration": "1mo",
        "budget_reset_at": None,
    }
    key = fake.keys[account.litellm_key]
    assert (key["user_id"], key["max_budget"], key["budget_duration"]) == (
        account.subject,
        2.0,
        "1d",
    )


def test_the_pool_is_made_once_until_it_is_revoked(repo) -> None:
    fake = FakeProxy()
    proxy = fake.client()

    pool = tool.create_pool(repo, proxy, 2.0, 6.0)
    assert (pool.kind, pool.invite_hash, pool.day_usd, pool.month_usd) == ("pool", None, 2.0, 6.0)
    assert repo.pool_account().subject == pool.subject
    with pytest.raises(SystemExit, match="a pool exists"):
        tool.create_pool(repo, proxy, 3.0, 9.0)

    tool.revoke(repo, proxy, pool.subject)
    assert tool.create_pool(repo, proxy, 3.0, 9.0).subject != pool.subject


def test_revoke_deletes_the_proxy_key_and_marks_the_row(repo) -> None:
    fake = FakeProxy()
    proxy = fake.client()
    tool.new_account(repo, proxy, "http://localhost:8000", "Jo", 2.0, 8.0)
    [account] = repo.list_accounts()

    revoked = tool.revoke(repo, proxy, account.subject)

    assert revoked.revoked_at is not None
    assert account.litellm_key not in fake.keys
    assert account.subject in fake.users
    with pytest.raises(SystemExit, match="no account"):
        tool.revoke(repo, proxy, "acct-nobody")


def test_list_shows_budgets_spend_and_revocation(repo) -> None:
    fake = FakeProxy()
    proxy = fake.client()
    pool = tool.create_pool(repo, proxy, 2.0, 6.0)
    tool.new_account(repo, proxy, "http://localhost:8000", "Jo", 1.0, 4.0)
    jo = repo.list_accounts()[1]
    fake.keys[jo.litellm_key]["spend"] = 0.25
    fake.users[jo.subject]["spend"] = 1.5
    fake.users[pool.subject]["spend"] = 3.0
    tool.revoke(repo, proxy, pool.subject)

    assert tool.rows(repo, proxy) == [
        {
            "subject": pool.subject,
            "kind": "pool",
            "name": "Demo-Pool",
            "day_usd": 2.0,
            "month_usd": 6.0,
            "spent_today": None,
            "spent_month": 3.0,
            "revoked": True,
        },
        {
            "subject": jo.subject,
            "kind": "account",
            "name": "Jo",
            "day_usd": 1.0,
            "month_usd": 4.0,
            "spent_today": 0.25,
            "spent_month": 1.5,
            "revoked": False,
        },
    ]
