"""Drop capability registry tables; remove skill/agent asset rows (OE port).

Workflow definitions remain in asset/asset_version with kind='workflow'.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("kpi_mapping")
    op.drop_table("capability_version")
    op.drop_table("capability")
    op.drop_table("connection")
    # Skills and agents are now Markdown/code-registered; keep workflow assets only.
    op.execute("DELETE FROM asset_version WHERE asset_id IN (SELECT id FROM asset WHERE kind != 'workflow')")
    op.execute("DELETE FROM asset WHERE kind != 'workflow'")


def downgrade() -> None:
    op.create_table(
        "connection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=48), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("type", sa.String(length=12), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("health_status", sa.String(length=12), nullable=False),
        sa.Column("health_checked_at", sa.DateTime(timezone=True)),
        sa.Column("health_detail", sa.String(length=200)),
        sa.Column("last_discovered_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Capability tables are not fully reconstructed on downgrade; recreate empty shells if needed.
