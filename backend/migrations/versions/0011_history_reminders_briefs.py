"""History notes, reminders, open loops, brief artifacts.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "history_note",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.String(length=400), nullable=False),
        sa.Column("quote", sa.String(length=600), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("session_id", sa.Integer()),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("correction", sa.String(length=400)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_history_note_user_id", "history_note", ["user_id"])
    op.create_index("ix_history_note_due_at", "history_note", ["due_at"])
    op.create_index("ix_history_note_expires_at", "history_note", ["expires_at"])

    op.create_table(
        "history_settings",
        sa.Column("user_id", sa.String(length=128), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "reminder",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("text", sa.String(length=400), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", sa.Integer()),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_reminder_user_id", "reminder", ["user_id"])
    op.create_index("ix_reminder_due_at", "reminder", ["due_at"])

    op.create_table(
        "open_loop",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=400), nullable=False),
        sa.Column("quote", sa.String(length=600), nullable=False, server_default=""),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("scope_key", sa.String(length=160), nullable=False),
        sa.Column("session_id", sa.Integer()),
        sa.Column("last_nudged_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_open_loop_user_id", "open_loop", ["user_id"])
    op.create_index("ix_open_loop_due_at", "open_loop", ["due_at"])
    op.create_index("ix_open_loop_scope_key", "open_loop", ["scope_key"])

    op.create_table(
        "brief_artifact",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("user_id", sa.String(length=128)),
        sa.Column("period_date", sa.String(length=10), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_brief_artifact_kind", "brief_artifact", ["kind"])
    op.create_index("ix_brief_artifact_user_id", "brief_artifact", ["user_id"])
    op.create_index("ix_brief_artifact_period_date", "brief_artifact", ["period_date"])


def downgrade() -> None:
    op.drop_table("brief_artifact")
    op.drop_table("open_loop")
    op.drop_table("reminder")
    op.drop_table("history_settings")
    op.drop_table("history_note")
