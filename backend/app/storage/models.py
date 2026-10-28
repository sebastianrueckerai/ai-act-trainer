from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    TypeDecorator,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class UtcDateTime(TypeDecorator[datetime]):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime not allowed; pass an aware UTC datetime")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    groups: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class TrainingSession(Base):
    __tablename__ = "training_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    thread_id: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    started_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    __table_args__ = (
        Index("ix_training_sessions_user_status", "user_id", "status"),
        Index(
            "uq_training_sessions_one_active",
            "user_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )


class Completion(Base):
    __tablename__ = "completions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    passed_at: Mapped[datetime] = mapped_column(UtcDateTime)
    course_version: Mapped[str] = mapped_column(String(32))
    law_version: Mapped[str] = mapped_column(String(64))
    locale: Mapped[str] = mapped_column(String(8))
    persona_id: Mapped[str] = mapped_column(String(64))

    __table_args__ = (Index("ix_completions_user_passed", "user_id", "passed_at"),)


class TurnLog(Base):
    __tablename__ = "turn_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    at: Mapped[datetime] = mapped_column(UtcDateTime)

    __table_args__ = (Index("ix_turn_log_at_user", "at", "user_id"),)


class Account(Base):
    """A caller with its own proxy key: an invited person, or the one pool the guests share."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(String(255), unique=True)
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(255))
    litellm_key: Mapped[str] = mapped_column(String(255))
    litellm_user_id: Mapped[str] = mapped_column(String(255))
    invite_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    day_usd: Mapped[float] = mapped_column(Float)
    month_usd: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    __table_args__ = (
        Index(
            "uq_accounts_one_live_pool",
            "kind",
            unique=True,
            sqlite_where=text("kind = 'pool' AND revoked_at IS NULL"),
            postgresql_where=text("kind = 'pool' AND revoked_at IS NULL"),
        ),
    )


class EmbeddingCache(Base):
    __tablename__ = "embedding_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    corpus_version: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    chunk_id: Mapped[str] = mapped_column(String(128))
    dimensions: Mapped[int] = mapped_column(Integer)
    vector: Mapped[list[float]] = mapped_column(JSON)

    __table_args__ = (
        UniqueConstraint("corpus_version", "model", "chunk_id", name="uq_embedding_chunk"),
    )
