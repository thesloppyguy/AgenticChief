"""capability registry

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "connection",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=48), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("type", sa.String(length=12), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("health_status", sa.String(length=12), nullable=False),
        sa.Column("health_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_detail", sa.String(length=200), nullable=True),
        sa.Column("last_discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "capability",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("output_schema", sa.JSON(), nullable=True),
        sa.Column("implementation", sa.JSON(), nullable=False),
        sa.Column("risk", sa.String(length=24), nullable=False),
        sa.Column("risk_override", sa.String(length=24), nullable=True),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("validated_version", sa.Integer(), nullable=True),
        sa.Column("published_version", sa.Integer(), nullable=True),
        sa.Column("removed", sa.Boolean(), nullable=False),
        sa.Column("deprecated", sa.Boolean(), nullable=False),
        sa.Column("lifecycle", sa.String(length=24), nullable=False),
        sa.Column("schema_hash", sa.String(length=64), nullable=False),
        sa.Column("validation", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["connection.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index(op.f("ix_capability_connection_id"), "capability", ["connection_id"], unique=False)
    op.create_index(op.f("ix_capability_lifecycle"), "capability", ["lifecycle"], unique=False)
    op.create_table(
        "capability_version",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("capability_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("output_schema", sa.JSON(), nullable=True),
        sa.Column("implementation", sa.JSON(), nullable=False),
        sa.Column("risk", sa.String(length=24), nullable=False),
        sa.Column("schema_hash", sa.String(length=64), nullable=False),
        sa.Column("validated", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["capability_id"], ["capability.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("capability_id", "version", name="uq_capability_version"),
    )
    op.create_index(op.f("ix_capability_version_capability_id"), "capability_version", ["capability_id"], unique=False)
    op.create_table(
        "kpi_mapping",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kpi_key", sa.String(length=64), nullable=False),
        sa.Column("capability_id", sa.Integer(), nullable=False),
        sa.Column("field_map", sa.JSON(), nullable=False),
        sa.Column("arg_template", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("approved_by", sa.String(length=128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["capability_id"], ["capability.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kpi_key", "capability_id", name="uq_kpi_mapping"),
    )
    op.create_index(op.f("ix_kpi_mapping_capability_id"), "kpi_mapping", ["capability_id"], unique=False)
    op.create_index(op.f("ix_kpi_mapping_kpi_key"), "kpi_mapping", ["kpi_key"], unique=False)
    op.create_index(op.f("ix_kpi_mapping_status"), "kpi_mapping", ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("kpi_mapping")
    op.drop_table("capability_version")
    op.drop_table("capability")
    op.drop_table("connection")
