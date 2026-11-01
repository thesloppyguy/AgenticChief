"""People, departments, and goals for L&T Group CHRO org model.

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "person",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("company_code", sa.String(length=32)),
        sa.Column("is_principal", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("authority_scope", sa.JSON()),
        sa.Column("department_slugs", sa.JSON()),
        sa.Column("preferred_channel", sa.String(length=24), nullable=False, server_default="any"),
        sa.Column("response_sla_hours", sa.Integer()),
    )
    op.create_index("ix_person_company_code", "person", ["company_code"])

    op.create_table(
        "department",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=48), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("company_code", sa.String(length=32)),
        sa.Column("specialist_key", sa.String(length=32)),
        sa.Column("head_person_id", sa.Integer(), sa.ForeignKey("person.id")),
        sa.Column("authority_level", sa.String(length=24), nullable=False, server_default="propose_only"),
        sa.Column("charter", sa.JSON()),
        sa.Column("headcount", sa.Integer()),
        sa.UniqueConstraint("company_code", "slug", name="uq_department_company_slug"),
    )
    op.create_index("ix_department_company_code", "department", ["company_code"])

    op.create_table(
        "goal",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("department.id"), nullable=False),
        sa.Column("period_type", sa.String(length=16), nullable=False, server_default="quarter"),
        sa.Column("period_value", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("key_result", sa.String(length=400), nullable=False),
        sa.Column("target", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("current", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="on_track"),
        sa.Column("pillar_key", sa.String(length=48)),
    )
    op.create_index("ix_goal_department_id", "goal", ["department_id"])


def downgrade() -> None:
    op.drop_table("goal")
    op.drop_table("department")
    op.drop_table("person")
