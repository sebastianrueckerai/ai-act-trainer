"""turn log for the spend caps

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-24

"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "turn_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_turn_log_at_user", "turn_log", ["at", "user_id"])


def downgrade() -> None:
    op.drop_table("turn_log")
