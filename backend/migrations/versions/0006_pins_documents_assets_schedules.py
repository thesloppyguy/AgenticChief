"""pins, documents (with full-text search), skills/agents, job schedules

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    ts = lambda name, nullable=False, now=True: sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.func.now() if now else None, nullable=nullable)
    op.create_table(
        "pin", sa.Column("id", sa.Integer(), nullable=False), sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False), sa.Column("ref", sa.String(300), nullable=False),
        sa.Column("label", sa.String(200), nullable=False), ts("created_at"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("user_id", "kind", "ref", name="uq_pin"))
    op.create_index(op.f("ix_pin_user_id"), "pin", ["user_id"], unique=False)

    op.create_table(
        "document", sa.Column("id", sa.Integer(), nullable=False), sa.Column("title", sa.String(200), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False), sa.Column("domain", sa.String(24), nullable=False),
        sa.Column("builtin", sa.Boolean(), nullable=False), sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False), sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.String(128), nullable=False), ts("created_at"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("content_hash"))
    op.create_table(
        "document_chunk", sa.Column("id", sa.Integer(), nullable=False), sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("ord", sa.Integer(), nullable=False), sa.Column("text", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"]), sa.PrimaryKeyConstraint("id"))
    op.create_index(op.f("ix_document_chunk_document_id"), "document_chunk", ["document_id"], unique=False)
    # SQLite full-text index (BM25-ranked). A virtual table: the ORM does not model it.
    op.execute("CREATE VIRTUAL TABLE chunk_fts USING fts5(text, chunk_id UNINDEXED, document_id UNINDEXED)")

    op.create_table(
        "asset", sa.Column("id", sa.Integer(), nullable=False), sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("key", sa.String(64), nullable=False), sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("validated_version", sa.Integer(), nullable=True), sa.Column("published_version", sa.Integer(), nullable=True),
        sa.Column("deprecated", sa.Boolean(), nullable=False), sa.Column("builtin", sa.Boolean(), nullable=False),
        sa.Column("lifecycle", sa.String(16), nullable=False), sa.Column("validation", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False), ts("created_at"), ts("updated_at"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("kind", "key", name="uq_asset_key"))
    op.create_index(op.f("ix_asset_kind"), "asset", ["kind"], unique=False)
    op.create_index(op.f("ix_asset_lifecycle"), "asset", ["lifecycle"], unique=False)
    op.create_table(
        "asset_version", sa.Column("id", sa.Integer(), nullable=False), sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False), sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("validated", sa.Boolean(), nullable=False), sa.Column("eval_passed", sa.Boolean(), nullable=True),
        sa.Column("eval_results", sa.JSON(), nullable=True), sa.Column("created_by", sa.String(128), nullable=False),
        ts("created_at"), sa.ForeignKeyConstraint(["asset_id"], ["asset.id"]), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", "version", name="uq_asset_version"))
    op.create_index(op.f("ix_asset_version_asset_id"), "asset_version", ["asset_id"], unique=False)

    op.create_table(
        "job_schedule", sa.Column("id", sa.Integer(), nullable=False), sa.Column("job", sa.String(32), nullable=False),
        sa.Column("name", sa.String(120), nullable=False), sa.Column("cadence", sa.JSON(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=True), sa.Column("enabled", sa.Boolean(), nullable=False), ts("next_run_at", now=False),
        ts("last_run_at", nullable=True, now=False), sa.Column("last_status", sa.String(16), nullable=True),
        sa.Column("last_detail", sa.String(200), nullable=True), ts("claimed_at", nullable=True, now=False),
        sa.Column("created_by", sa.String(128), nullable=False), sa.PrimaryKeyConstraint("id"))
    op.create_index(op.f("ix_job_schedule_next_run_at"), "job_schedule", ["next_run_at"], unique=False)


def downgrade() -> None:
    op.drop_table("job_schedule")
    op.drop_table("asset_version")
    op.drop_table("asset")
    op.execute("DROP TABLE chunk_fts")
    op.drop_table("document_chunk")
    op.drop_table("document")
    op.drop_table("pin")
