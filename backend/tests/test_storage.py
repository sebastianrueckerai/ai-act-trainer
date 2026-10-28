from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session, sessionmaker

from app.storage.db import make_engine
from app.storage.models import Base, TrainingSession, TurnLog, User
from app.storage.repository import SqlAlchemyRepository


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        yield session


def test_upsert_user_creates_then_updates(db_session: Session):
    repo = SqlAlchemyRepository(db_session)
    user = repo.upsert_user("sub-1", "Anna", "anna@example.org", ["staff"])
    assert user.id is not None
    again = repo.upsert_user("sub-1", "Anna Neu", None, ["staff", "compliance"])
    assert again.id == user.id
    assert again.name == "Anna Neu"
    assert again.email is None
    assert again.groups == ["staff", "compliance"]


def test_upsert_user_returns_existing_when_insert_collides(db_session: Session):
    repo = SqlAlchemyRepository(db_session)
    first = repo.upsert_user("sub-1", "Anna", None, [])
    db_session.commit()
    # Simulate a concurrent creator that won the race: hide the row from the first select.
    original = repo._user_by_subject
    calls = {"n": 0}

    def racing(subject: str):
        calls["n"] += 1
        return None if calls["n"] == 1 else original(subject)

    repo._user_by_subject = racing
    again = repo.upsert_user("sub-1", "Anna Neu", None, ["staff"])
    assert again.id == first.id
    assert again.name == "Anna Neu"
    assert again.groups == ["staff"]


def test_get_or_create_session_returns_active_session(db_session: Session):
    repo = SqlAlchemyRepository(db_session)
    user = repo.upsert_user("sub-1", "Anna", None, [])
    first = repo.get_or_create_session(user.id)
    second = repo.get_or_create_session(user.id)
    assert first.id == second.id
    assert first.status == "active"
    assert first.thread_id
    repo.close_session(first.id, "completed")
    third = repo.get_or_create_session(user.id)
    assert third.id != first.id


def test_record_and_read_latest_completion(db_session: Session):
    repo = SqlAlchemyRepository(db_session)
    user = repo.upsert_user("sub-1", "Anna", None, [])
    assert repo.latest_completion(user.id) is None
    older = datetime(2025, 9, 1, 12, 0, tzinfo=UTC)
    newer = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    repo.record_completion(user.id, "0.1.0", "02024R1689-20260727", "de", "clerk", older)
    repo.record_completion(user.id, "0.1.0", "02024R1689-20260727", "de", "marvin", newer)
    latest = repo.latest_completion(user.id)
    assert latest is not None
    assert latest.persona_id == "marvin"
    assert latest.passed_at == newer
    assert latest.passed_at.tzinfo is not None


def test_naive_datetime_is_rejected(db_session: Session):
    repo = SqlAlchemyRepository(db_session)
    user = repo.upsert_user("sub-1", "Anna", None, [])
    with pytest.raises(StatementError):
        repo.record_completion(user.id, "0.1.0", "law", "de", "clerk", datetime(2026, 9, 1, 12, 0))
    db_session.rollback()


def test_second_active_session_for_same_user_is_rejected_by_the_database(db_session: Session):
    repo = SqlAlchemyRepository(db_session)
    user = repo.upsert_user("sub-1", "Anna", None, [])
    repo.get_or_create_session(user.id)
    db_session.add(TrainingSession(user_id=user.id, thread_id="duplicate", status="active"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_get_or_create_session_returns_existing_when_insert_collides(db_session: Session):
    repo = SqlAlchemyRepository(db_session)
    user = repo.upsert_user("sub-1", "Anna", None, [])
    first = repo.get_or_create_session(user.id)
    db_session.commit()
    # Simulate a concurrent creator that won the race: hide the row from the first select.
    original = repo.active_session
    calls = {"n": 0}

    def racing(user_id: int):
        calls["n"] += 1
        return None if calls["n"] == 1 else original(user_id)

    repo.active_session = racing
    assert repo.get_or_create_session(user.id).id == first.id


def test_savepoint_write_rolls_back_with_its_transaction(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'rollback.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def rows_visible_to_other_connections() -> int:
        with engine.connect() as other:
            return other.scalar(select(func.count()).select_from(User))

    writer = factory()
    with writer.begin_nested():
        writer.add(User(subject="sub-1", name="Anna", email=None, groups=[]))
        writer.flush()
    writer.rollback()
    assert rows_visible_to_other_connections() == 0

    with writer.begin_nested():
        writer.add(User(subject="sub-2", name="Boris", email=None, groups=[]))
        writer.flush()
    writer.commit()
    assert rows_visible_to_other_connections() == 1


NOON = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


def _user(db_session: Session, subject: str, created_at: datetime) -> int:
    user = User(subject=subject, name=subject, email=None, groups=[], created_at=created_at)
    db_session.add(user)
    db_session.flush()
    return user.id


def test_an_idle_guest_is_one_whose_last_turn_or_creation_is_before_the_cut(db_session: Session):
    repo = SqlAlchemyRepository(db_session)
    old_turns = _user(db_session, "guest-old", NOON - timedelta(hours=9))
    db_session.add(TurnLog(user_id=old_turns, at=NOON - timedelta(hours=7)))
    back_since = _user(db_session, "guest-back", NOON - timedelta(hours=9))
    db_session.add(TurnLog(user_id=back_since, at=NOON - timedelta(hours=8)))
    db_session.add(TurnLog(user_id=back_since, at=NOON - timedelta(hours=1)))
    never_spoke = _user(db_session, "guest-silent", NOON - timedelta(hours=7))
    _user(db_session, "guest-new", NOON - timedelta(minutes=5))
    named = _user(db_session, "acct-jo", NOON - timedelta(days=30))
    db_session.add(TurnLog(user_id=named, at=NOON - timedelta(days=29)))
    db_session.commit()

    assert repo.idle_guests(NOON - timedelta(hours=6)) == [old_turns, never_spoke]


def test_an_idle_named_user_is_one_whose_last_turn_or_creation_is_before_the_cut(
    db_session: Session,
):
    repo = SqlAlchemyRepository(db_session)
    old = _user(db_session, "anna", NOON - timedelta(days=40))
    db_session.add(TurnLog(user_id=old, at=NOON - timedelta(days=35)))
    fresh = _user(db_session, "boris", NOON - timedelta(days=40))
    db_session.add(TurnLog(user_id=fresh, at=NOON - timedelta(days=2)))
    _user(db_session, "guest-any", NOON - timedelta(days=90))
    db_session.commit()

    assert repo.idle_named_users(NOON - timedelta(days=30)) == [old]


def test_active_guests_are_the_guests_with_a_turn_since(db_session: Session):
    repo = SqlAlchemyRepository(db_session)
    recent = _user(db_session, "guest-a", NOON)
    db_session.add(TurnLog(user_id=recent, at=NOON - timedelta(minutes=2)))
    db_session.add(TurnLog(user_id=recent, at=NOON - timedelta(minutes=1)))
    stale = _user(db_session, "guest-b", NOON)
    db_session.add(TurnLog(user_id=stale, at=NOON - timedelta(minutes=11)))
    named = _user(db_session, "anna", NOON)
    db_session.add(TurnLog(user_id=named, at=NOON - timedelta(minutes=1)))
    db_session.commit()

    assert repo.active_guest_ids(NOON - timedelta(minutes=10)) == {recent}


def test_deleting_transcript_rows_keeps_the_account_and_its_pass_records(db_session: Session):
    repo = SqlAlchemyRepository(db_session)
    anna = repo.upsert_user("anna", "Anna", None, [])
    session = repo.get_or_create_session(anna.id)
    repo.log_turn(anna.id)
    repo.record_completion(anna.id, "0.1.0", "law", "de", "clerk", NOON)
    db_session.commit()

    thread_id = session.thread_id
    threads = repo.delete_transcript_rows(anna.id)

    assert threads == [thread_id]
    assert db_session.scalars(select(User.subject)).all() == ["anna"]
    assert db_session.scalars(select(TrainingSession.id)).all() == []
    assert db_session.scalars(select(TurnLog.id)).all() == []
    assert repo.latest_completion(anna.id) is not None


def test_deleting_a_users_rows_returns_their_threads_and_leaves_others(db_session: Session):
    repo = SqlAlchemyRepository(db_session)
    guest = repo.upsert_user("guest-a", "Gast", None, ["guest"])
    first = repo.get_or_create_session(guest.id)
    repo.close_session(first.id, "abandoned")
    second = repo.get_or_create_session(guest.id)
    repo.log_turn(guest.id)
    repo.record_completion(guest.id, "0.1.0", "law", "de", "clerk", NOON)
    anna = repo.upsert_user("anna", "Anna", None, [])
    kept = repo.get_or_create_session(anna.id)
    repo.log_turn(anna.id)
    db_session.commit()
    guest_id, threads_before = guest.id, {first.thread_id, second.thread_id}

    threads = repo.delete_user_rows(guest_id)

    assert set(threads) == threads_before and len(threads) == 2
    assert db_session.scalars(select(User.subject)).all() == ["anna"]
    assert db_session.scalars(select(TrainingSession.thread_id)).all() == [kept.thread_id]
    assert db_session.scalars(select(TurnLog.user_id)).all() == [anna.id]
    assert repo.latest_completion(guest_id) is None


def test_accounts_hold_one_live_pool_and_find_by_subject_and_invite_hash(db_session: Session):
    repo = SqlAlchemyRepository(db_session)
    repo.add_account("pool-a", "pool", "Demo-Pool", "sk-pool-a", "pool-a", None, 2, 6)
    jo = repo.add_account("acct-jo", "account", "Jo", "sk-acct-jo", "acct-jo", "ab" * 32, 2, 8)

    assert repo.pool_account().subject == "pool-a"
    assert repo.account_by_subject("acct-jo").id == jo.id
    assert repo.account_by_invite_hash("ab" * 32).id == jo.id
    assert repo.account_by_invite_hash("cd" * 32) is None
    with pytest.raises(IntegrityError):
        repo.add_account("pool-b", "pool", "Demo-Pool", "sk-pool-b", "pool-b", None, 2, 6)
    db_session.rollback()

    assert repo.revoke_account("pool-a").revoked_at is not None
    assert repo.pool_account() is None
    repo.add_account("pool-b", "pool", "Demo-Pool", "sk-pool-b", "pool-b", None, 2, 6)
    assert repo.pool_account().subject == "pool-b"
    assert [a.subject for a in repo.list_accounts()] == ["pool-a", "acct-jo", "pool-b"]
