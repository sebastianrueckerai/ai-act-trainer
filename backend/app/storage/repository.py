import secrets
from datetime import datetime
from typing import Protocol

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.identity import GUEST_PREFIX
from app.storage.models import Account, Completion, TrainingSession, TurnLog, User, utcnow


class Repository(Protocol):
    def upsert_user(
        self, subject: str, name: str, email: str | None, groups: list[str]
    ) -> User: ...
    def get_or_create_session(self, user_id: int) -> TrainingSession: ...
    def active_session(self, user_id: int) -> TrainingSession | None: ...
    def get_session(self, session_id: int, user_id: int) -> TrainingSession | None: ...
    def close_session(self, session_id: int, status: str) -> None: ...
    def record_completion(
        self,
        user_id: int,
        course_version: str,
        law_version: str,
        locale: str,
        persona_id: str,
        passed_at: datetime,
    ) -> Completion: ...
    def latest_completion(self, user_id: int) -> Completion | None: ...
    def log_turn(self, user_id: int) -> None: ...
    def turns_since(self, since: datetime, user_id: int | None = None) -> int: ...
    def account_by_subject(self, subject: str) -> Account | None: ...
    def account_by_invite_hash(self, invite_hash: str) -> Account | None: ...
    def pool_account(self) -> Account | None: ...
    def add_account(
        self,
        subject: str,
        kind: str,
        name: str,
        litellm_key: str,
        litellm_user_id: str,
        invite_hash: str | None,
        day_usd: float,
        month_usd: float,
    ) -> Account: ...
    def revoke_account(self, subject: str) -> Account | None: ...
    def list_accounts(self) -> list[Account]: ...
    def active_guest_ids(self, since: datetime) -> set[int]: ...
    def idle_guests(self, before: datetime) -> list[int]: ...
    def idle_named_users(self, before: datetime) -> list[int]: ...
    def delete_user_rows(self, user_id: int) -> list[str]: ...
    def delete_transcript_rows(self, user_id: int) -> list[str]: ...


class SqlAlchemyRepository:
    # Mutators commit before returning: no write transaction may span an await,
    # or two same-subject requests deadlock on the users row.

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_user(self, subject: str, name: str, email: str | None, groups: list[str]) -> User:
        user = self._user_by_subject(subject)
        if user is None:
            try:
                with self.session.begin_nested():
                    user = User(subject=subject, name=name, email=email, groups=list(groups))
                    self.session.add(user)
                    self.session.flush()
            except IntegrityError:
                user = self._user_by_subject(subject)
                if user is None:
                    raise
        user.name = name
        user.email = email
        user.groups = list(groups)
        self.session.flush()
        self.session.commit()
        return user

    def _user_by_subject(self, subject: str) -> User | None:
        return self.session.scalar(select(User).where(User.subject == subject))

    def get_or_create_session(self, user_id: int) -> TrainingSession:
        active = self.active_session(user_id)
        if active is not None:
            self.session.commit()
            return active
        try:
            with self.session.begin_nested():
                created = TrainingSession(user_id=user_id, thread_id=secrets.token_urlsafe(24))
                self.session.add(created)
                self.session.flush()
        except IntegrityError:
            active = self.active_session(user_id)
            if active is None:
                raise
            self.session.commit()
            return active
        self.session.commit()
        return created

    def get_session(self, session_id: int, user_id: int) -> TrainingSession | None:
        training_session = self.session.get(TrainingSession, session_id)
        if training_session is None or training_session.user_id != user_id:
            return None
        return training_session

    def active_session(self, user_id: int) -> TrainingSession | None:
        return self.session.scalar(
            select(TrainingSession)
            .where(TrainingSession.user_id == user_id, TrainingSession.status == "active")
            .order_by(TrainingSession.started_at.desc())
        )

    def close_session(self, session_id: int, status: str) -> None:
        training_session = self.session.get(TrainingSession, session_id)
        if training_session is None:
            return
        training_session.status = status
        training_session.closed_at = utcnow()
        self.session.flush()
        self.session.commit()

    def record_completion(
        self,
        user_id: int,
        course_version: str,
        law_version: str,
        locale: str,
        persona_id: str,
        passed_at: datetime,
    ) -> Completion:
        completion = Completion(
            user_id=user_id,
            course_version=course_version,
            law_version=law_version,
            locale=locale,
            persona_id=persona_id,
            passed_at=passed_at,
        )
        self.session.add(completion)
        self.session.flush()
        self.session.commit()
        return completion

    def latest_completion(self, user_id: int) -> Completion | None:
        return self.session.scalar(
            select(Completion)
            .where(Completion.user_id == user_id)
            .order_by(Completion.passed_at.desc())
            .limit(1)
        )

    def log_turn(self, user_id: int) -> None:
        self.session.add(TurnLog(user_id=user_id, at=utcnow()))
        self.session.flush()

    def turns_since(self, since: datetime, user_id: int | None = None) -> int:
        query = select(func.count()).select_from(TurnLog).where(TurnLog.at >= since)
        if user_id is not None:
            query = query.where(TurnLog.user_id == user_id)
        return self.session.scalar(query) or 0

    def account_by_subject(self, subject: str) -> Account | None:
        return self.session.scalar(select(Account).where(Account.subject == subject))

    def account_by_invite_hash(self, invite_hash: str) -> Account | None:
        return self.session.scalar(select(Account).where(Account.invite_hash == invite_hash))

    def pool_account(self) -> Account | None:
        return self.session.scalar(
            select(Account).where(Account.kind == "pool", Account.revoked_at.is_(None))
        )

    def add_account(
        self,
        subject: str,
        kind: str,
        name: str,
        litellm_key: str,
        litellm_user_id: str,
        invite_hash: str | None,
        day_usd: float,
        month_usd: float,
    ) -> Account:
        account = Account(
            subject=subject,
            kind=kind,
            name=name,
            litellm_key=litellm_key,
            litellm_user_id=litellm_user_id,
            invite_hash=invite_hash,
            day_usd=day_usd,
            month_usd=month_usd,
        )
        self.session.add(account)
        self.session.flush()
        self.session.commit()
        return account

    def revoke_account(self, subject: str) -> Account | None:
        account = self.account_by_subject(subject)
        if account is None:
            return None
        account.revoked_at = utcnow()
        self.session.flush()
        self.session.commit()
        return account

    def list_accounts(self) -> list[Account]:
        return list(self.session.scalars(select(Account).order_by(Account.id)))

    def active_guest_ids(self, since: datetime) -> set[int]:
        return set(
            self.session.scalars(
                select(TurnLog.user_id)
                .join(User, User.id == TurnLog.user_id)
                .where(TurnLog.at >= since, User.subject.startswith(GUEST_PREFIX))
                .distinct()
            )
        )

    def _idle_users(self, before: datetime, guests: bool) -> list[int]:
        last_seen = func.coalesce(func.max(TurnLog.at), User.created_at)
        subject = User.subject.startswith(GUEST_PREFIX)
        return list(
            self.session.scalars(
                select(User.id)
                .outerjoin(TurnLog, TurnLog.user_id == User.id)
                .where(subject if guests else ~subject)
                .group_by(User.id, User.created_at)
                .having(last_seen < before)
                .order_by(User.id)
            )
        )

    def idle_guests(self, before: datetime) -> list[int]:
        return self._idle_users(before, guests=True)

    def idle_named_users(self, before: datetime) -> list[int]:
        return self._idle_users(before, guests=False)

    def delete_user_rows(self, user_id: int) -> list[str]:
        threads = list(
            self.session.scalars(
                select(TrainingSession.thread_id).where(TrainingSession.user_id == user_id)
            )
        )
        for table in (TurnLog, Completion, TrainingSession):
            self.session.execute(delete(table).where(table.user_id == user_id))
        self.session.execute(delete(User).where(User.id == user_id))
        self.session.commit()
        return threads

    def delete_transcript_rows(self, user_id: int) -> list[str]:
        """The retention sweep's half of delete_user_rows: the threads and turn rows go,
        the account and its pass records stay."""
        threads = list(
            self.session.scalars(
                select(TrainingSession.thread_id).where(TrainingSession.user_id == user_id)
            )
        )
        for table in (TurnLog, TrainingSession):
            self.session.execute(delete(table).where(table.user_id == user_id))
        self.session.commit()
        return threads
