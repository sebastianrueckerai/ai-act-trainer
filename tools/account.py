"""Create, list and revoke the callers that spend their own proxy budget.

Runs where the app's settings are: inside the trainer container, or on the host from the
repo root with `uv run --project backend python tools/account.py ...`:

    docker compose exec trainer python tools/account.py pool --day 2 --month 6
    docker compose exec trainer python tools/account.py new --name "Jo" [--day 2] [--month 8]
    docker compose exec trainer python tools/account.py list
    docker compose exec trainer python tools/account.py revoke acct-...

`pool` creates the one budget every guest shares. `new` creates a named account and prints
its invite link once: the link is the password, and only its hash is stored. `revoke`
deletes the account's proxy key, which ends the link and the budget at once.
"""

import argparse
import secrets
import sys

import httpx

from app.auth.invite import invite_hash
from app.llm.budget import ProxyClient
from app.settings import get_settings
from app.storage.db import make_engine, make_session_factory
from app.storage.migrate import run_migrations
from app.storage.models import Account
from app.storage.repository import Repository, SqlAlchemyRepository


def _create(
    repo: Repository,
    proxy: ProxyClient,
    subject: str,
    kind: str,
    name: str,
    token_hash: str | None,
    day: float,
    month: float,
) -> Account:
    proxy.new_user(subject, month)
    key = proxy.generate_key(subject, day, key_alias=subject)
    return repo.add_account(subject, kind, name, key, subject, token_hash, day, month)


def create_pool(repo: Repository, proxy: ProxyClient, day: float, month: float) -> Account:
    live = repo.pool_account()
    if live is not None:
        raise SystemExit(f"a pool exists: {live.subject}. Revoke it first.")
    subject = f"pool-{secrets.token_urlsafe(6)}"
    return _create(repo, proxy, subject, "pool", "Demo-Pool", None, day, month)


def new_account(
    repo: Repository, proxy: ProxyClient, public_url: str, name: str, day: float, month: float
) -> str:
    """The invite link, the only time the token is ever seen."""
    token = secrets.token_urlsafe(24)
    subject = f"acct-{secrets.token_urlsafe(16)}"
    _create(repo, proxy, subject, "account", name, invite_hash(token), day, month)
    return f"{public_url.rstrip('/')}/?invite={token}"


def _spent(read) -> float | None:
    try:
        return read().spend
    except httpx.HTTPError:
        return None


def rows(repo: Repository, proxy: ProxyClient) -> list[dict]:
    return [
        {
            "subject": account.subject,
            "kind": account.kind,
            "name": account.name,
            "day_usd": account.day_usd,
            "month_usd": account.month_usd,
            # A revoked key is gone from the proxy, and its spend with it.
            "spent_today": _spent(lambda a=account: proxy.key_info(a.litellm_key, fresh=True)),
            "spent_month": _spent(lambda a=account: proxy.user_info(a.litellm_user_id, fresh=True)),
            "revoked": account.revoked_at is not None,
        }
        for account in repo.list_accounts()
    ]


def revoke(repo: Repository, proxy: ProxyClient, subject: str) -> Account:
    account = repo.account_by_subject(subject)
    if account is None:
        raise SystemExit(f"no account {subject}")
    if account.revoked_at is None:
        proxy.delete_key(account.litellm_key)
        account = repo.revoke_account(subject)
    return account


def _usd(value: float | None) -> str:
    return "-" if value is None else f"{value:.4f}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    pool = commands.add_parser("pool", help="create the budget every guest shares")
    pool.add_argument("--day", type=float, default=2.0)
    pool.add_argument("--month", type=float, default=6.0)
    new = commands.add_parser("new", help="create a named account and print its invite link")
    new.add_argument("--name", required=True)
    new.add_argument("--day", type=float, default=2.0)
    new.add_argument("--month", type=float, default=8.0)
    commands.add_parser("list", help="every account with its budget and spend")
    gone = commands.add_parser("revoke", help="delete an account's key, which ends its link")
    gone.add_argument("subject")
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.litellm_admin_key:
        raise SystemExit("LITELLM_ADMIN_KEY is empty: budgets are off, there is nothing to manage")
    if settings.run_migrations:
        run_migrations(settings.database_url)
    proxy = ProxyClient(settings.llm_base_url, settings.litellm_admin_key)
    with make_session_factory(make_engine(settings.database_url))() as session:
        repo = SqlAlchemyRepository(session)
        if args.command == "pool":
            account = create_pool(repo, proxy, args.day, args.month)
            print(f"pool {account.subject}: {args.day} USD a day, {args.month} USD a month")
        elif args.command == "new":
            print(new_account(repo, proxy, settings.public_url, args.name, args.day, args.month))
        elif args.command == "list":
            for row in rows(repo, proxy):
                print(
                    "\t".join(
                        [
                            row["subject"],
                            row["kind"],
                            row["name"],
                            f"day {_usd(row['spent_today'])}/{row['day_usd']}",
                            f"month {_usd(row['spent_month'])}/{row['month_usd']}",
                            "revoked" if row["revoked"] else "live",
                        ]
                    )
                )
        else:
            print(f"revoked {revoke(repo, proxy, args.subject).subject}")
    proxy.close()


if __name__ == "__main__":
    main(sys.argv[1:])
