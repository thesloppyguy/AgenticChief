"""mock source systems: AI-generated company data

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mock_company_data",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_code", sa.String(length=32), nullable=False),
        sa.Column("archetype", sa.String(length=16), nullable=False),
        sa.Column("origin", sa.String(length=12), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_code"),
    )


def downgrade() -> None:
    op.drop_table("mock_company_data")
