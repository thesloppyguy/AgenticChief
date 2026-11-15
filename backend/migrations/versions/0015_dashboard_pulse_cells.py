"""Personal pulse KPI cells on Home layout.

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dashboard_layout",
        sa.Column("pulse_cells", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "dashboard_layout",
        sa.Column("pulse_hidden", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("dashboard_layout", "pulse_hidden")
    op.drop_column("dashboard_layout", "pulse_cells")
