"""user-defined watches, private alert audiences, and audit indexes for the activity timeline

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "watch",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("condition", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("schedule_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.ForeignKeyConstraint(["schedule_id"], ["job_schedule.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_watch_user_id"), "watch", ["user_id"], unique=False)
    op.create_index(op.f("ix_watch_company_id"), "watch", ["company_id"], unique=False)
    op.create_index(op.f("ix_watch_schedule_id"), "watch", ["schedule_id"], unique=False)

    # A private alert: only its audience sees it. NULL keeps every existing alert group-visible.
    op.add_column("alert", sa.Column("audience_user_id", sa.String(length=128), nullable=True))
    op.create_index(op.f("ix_alert_audience_user_id"), "alert", ["audience_user_id"], unique=False)

    # The activity timeline orders by `at` and filters by `actor`.
    op.create_index(op.f("ix_audit_event_at"), "audit_event", ["at"], unique=False)
    op.create_index(op.f("ix_audit_event_actor"), "audit_event", ["actor"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_event_actor"), table_name="audit_event")
    op.drop_index(op.f("ix_audit_event_at"), table_name="audit_event")
    op.drop_index(op.f("ix_alert_audience_user_id"), table_name="alert")
    op.drop_column("alert", "audience_user_id")
    op.drop_index(op.f("ix_watch_schedule_id"), table_name="watch")
    op.drop_index(op.f("ix_watch_company_id"), table_name="watch")
    op.drop_index(op.f("ix_watch_user_id"), table_name="watch")
    op.drop_table("watch")
