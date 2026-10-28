"""level 0 tables

Revision ID: 0001
Revises:
Create Date: 2026-09-15

"""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subject", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("groups", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "training_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("thread_id", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_training_sessions_user_status", "training_sessions", ["user_id", "status"])
    op.create_index(
        "uq_training_sessions_one_active",
        "training_sessions",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "completions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("passed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("course_version", sa.String(32), nullable=False),
        sa.Column("law_version", sa.String(64), nullable=False),
        sa.Column("locale", sa.String(8), nullable=False),
        sa.Column("persona_id", sa.String(64), nullable=False),
    )
    op.create_index("ix_completions_user_passed", "completions", ["user_id", "passed_at"])
    op.create_table(
        "embedding_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("corpus_version", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("chunk_id", sa.String(128), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("vector", sa.JSON(), nullable=False),
        sa.UniqueConstraint("corpus_version", "model", "chunk_id", name="uq_embedding_chunk"),
    )


def downgrade() -> None:
    op.drop_table("embedding_cache")
    op.drop_index("ix_completions_user_passed", table_name="completions")
    op.drop_table("completions")
    op.drop_index("uq_training_sessions_one_active", table_name="training_sessions")
    op.drop_index("ix_training_sessions_user_status", table_name="training_sessions")
    op.drop_table("training_sessions")
    op.drop_table("users")
