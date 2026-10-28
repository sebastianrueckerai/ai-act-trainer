"""accounts with their own proxy key, and the guests' pool

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-11

"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subject", sa.String(255), nullable=False, unique=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("litellm_key", sa.String(255), nullable=False),
        sa.Column("litellm_user_id", sa.String(255), nullable=False),
        sa.Column("invite_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("day_usd", sa.Float(), nullable=False),
        sa.Column("month_usd", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_accounts_one_live_pool",
        "accounts",
        ["kind"],
        unique=True,
        sqlite_where=sa.text("kind = 'pool' AND revoked_at IS NULL"),
        postgresql_where=sa.text("kind = 'pool' AND revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_accounts_one_live_pool", table_name="accounts")
    op.drop_table("accounts")
