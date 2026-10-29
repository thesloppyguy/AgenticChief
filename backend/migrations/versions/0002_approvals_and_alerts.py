"""approvals and alerts

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-28 23:36:01.604757

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "alert",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=12), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("entity", sa.String(length=64), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["company.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index(op.f("ix_alert_company_id"), "alert", ["company_id"], unique=False)
    op.create_index(op.f("ix_alert_kind"), "alert", ["kind"], unique=False)

    op.create_table(
        "approval_request",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("risk", sa.String(length=24), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column("args", sa.JSON(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("requested_by", sa.String(length=128), nullable=False),
        sa.Column("via", sa.String(length=16), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_comment", sa.String(length=1000), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["chat_session.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_approval_request_action"), "approval_request", ["action"], unique=False
    )
    op.create_index(
        op.f("ix_approval_request_requested_by"), "approval_request", ["requested_by"], unique=False
    )
    op.create_index(
        op.f("ix_approval_request_status"), "approval_request", ["status"], unique=False
    )

    op.create_table(
        "alert_read",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alert_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["alert.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alert_id", "user_id"),
    )
    op.create_index(op.f("ix_alert_read_alert_id"), "alert_read", ["alert_id"], unique=False)
    op.create_index(op.f("ix_alert_read_user_id"), "alert_read", ["user_id"], unique=False)

    op.create_table(
        "approval_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("approval_id", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("event", sa.String(length=24), nullable=False),
        sa.Column("comment", sa.String(length=1000), nullable=True),
        sa.ForeignKeyConstraint(
            ["approval_id"],
            ["approval_request.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_approval_event_approval_id"), "approval_event", ["approval_id"], unique=False
    )

    op.create_table(
        "outbound_message",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("approval_id", sa.Integer(), nullable=True),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("company_code", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["approval_id"],
            ["approval_request.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_outbound_message_approval_id"), "outbound_message", ["approval_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_outbound_message_approval_id"), table_name="outbound_message")

    op.drop_table("outbound_message")
    op.drop_index(op.f("ix_approval_event_approval_id"), table_name="approval_event")

    op.drop_table("approval_event")
    op.drop_index(op.f("ix_alert_read_user_id"), table_name="alert_read")
    op.drop_index(op.f("ix_alert_read_alert_id"), table_name="alert_read")

    op.drop_table("alert_read")
    op.drop_index(op.f("ix_approval_request_status"), table_name="approval_request")
    op.drop_index(op.f("ix_approval_request_requested_by"), table_name="approval_request")
    op.drop_index(op.f("ix_approval_request_action"), table_name="approval_request")

    op.drop_table("approval_request")
    op.drop_index(op.f("ix_alert_kind"), table_name="alert")
    op.drop_index(op.f("ix_alert_company_id"), table_name="alert")

    op.drop_table("alert")
