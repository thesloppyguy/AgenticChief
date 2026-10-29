"""workflows and immutable snapshots

Revision ID: 0003
Revises: 0002
"""

import hashlib
import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _hash(payload) -> str:
    """Frozen copy of the canonical hash used by the app, so this migration never changes meaning."""
    obj = json.loads(payload) if isinstance(payload, str) else payload
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def upgrade() -> None:
    op.create_table(
        "workflow_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workflow", sa.String(length=48), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("requested_by", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(length=200), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workflow_run_status"), "workflow_run", ["status"], unique=False)
    op.create_index(op.f("ix_workflow_run_workflow"), "workflow_run", ["workflow"], unique=False)

    op.create_table(
        "workflow_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("step", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("message", sa.String(length=300), nullable=False),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_run.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workflow_event_run_id"), "workflow_event", ["run_id"], unique=False)

    with op.batch_alter_table("report_snapshot") as batch:  # batch: SQLite cannot ALTER constraints
        batch.add_column(sa.Column("kind", sa.String(length=24), server_default="scorecard", nullable=False))
        batch.add_column(sa.Column("content_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("run_id", sa.Integer(), nullable=True))
        batch.create_unique_constraint("uq_report_snapshot_run_id", ["run_id"])
        batch.create_foreign_key("fk_report_snapshot_run_id", "workflow_run", ["run_id"], ["id"])

    # Existing snapshots become verifiable too. Needs a live connection, so offline (--sql) output skips it.
    if context.is_offline_mode():
        return
    conn = op.get_bind()
    for snap_id, payload in conn.execute(sa.text("SELECT id, payload FROM report_snapshot")).fetchall():
        conn.execute(sa.text("UPDATE report_snapshot SET content_hash = :h WHERE id = :i"),
                     {"h": _hash(payload), "i": snap_id})


def downgrade() -> None:
    with op.batch_alter_table("report_snapshot") as batch:
        batch.drop_constraint("fk_report_snapshot_run_id", type_="foreignkey")
        batch.drop_constraint("uq_report_snapshot_run_id", type_="unique")
        batch.drop_column("run_id")
        batch.drop_column("content_hash")
        batch.drop_column("kind")
    op.drop_index(op.f("ix_workflow_event_run_id"), table_name="workflow_event")
    op.drop_table("workflow_event")
    op.drop_index(op.f("ix_workflow_run_workflow"), table_name="workflow_run")
    op.drop_index(op.f("ix_workflow_run_status"), table_name="workflow_run")
    op.drop_table("workflow_run")
