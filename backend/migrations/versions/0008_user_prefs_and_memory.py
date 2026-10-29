"""user preferences (alerts, quiet hours, memory switch) and Copilot memory

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_prefs",
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("min_severity", sa.String(length=12), nullable=False),
        sa.Column("muted_kinds", sa.JSON(), nullable=False),
        sa.Column("quiet_start", sa.String(length=5), nullable=True),
        sa.Column("quiet_end", sa.String(length=5), nullable=True),
        sa.Column("tz", sa.String(length=64), nullable=False),
        sa.Column("memory_enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "user_memory",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("domain", sa.String(length=24), nullable=False),
        sa.Column("summary", sa.String(length=400), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_memory_user_id"), "user_memory", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("user_memory")
    op.drop_table("user_prefs")
