"""SF-shaped workforce census tables for employee simulation.

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "employee",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ps_number", sa.String(length=32), nullable=False),
        sa.Column("company_code", sa.String(length=32), nullable=False),
        sa.Column("legal_entity", sa.String(length=120), nullable=False),
        sa.Column("business_unit", sa.String(length=120), nullable=False),
        sa.Column("department", sa.String(length=120), nullable=False),
        sa.Column("job_code", sa.String(length=48), nullable=False),
        sa.Column("job_title", sa.String(length=120), nullable=False),
        sa.Column("job_function", sa.String(length=120), nullable=False),
        sa.Column("grade_cadre", sa.String(length=32), nullable=False),
        sa.Column("band", sa.String(length=32), nullable=False),
        sa.Column("employment_type", sa.String(length=48), nullable=False),
        sa.Column("appointment_type", sa.String(length=48), nullable=False),
        sa.Column("employee_group", sa.String(length=48), nullable=False),
        sa.Column("manager_ps_number", sa.String(length=32), nullable=True),
        sa.Column("position_id", sa.String(length=48), nullable=False),
        sa.Column("hire_date", sa.String(length=10), nullable=False),
        sa.Column("joining_date", sa.String(length=10), nullable=False),
        sa.Column("separation_date", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("time_in_company_months", sa.Integer(), nullable=False),
        sa.Column("time_in_position_months", sa.Integer(), nullable=False),
        sa.Column("is_trainee", sa.Boolean(), nullable=False),
        sa.Column("contract_training_end_date", sa.String(length=10), nullable=True),
        sa.Column("top_talent", sa.Boolean(), nullable=False),
        sa.Column("cpr_band", sa.Integer(), nullable=False),
        sa.Column("willing_to_relocate", sa.Boolean(), nullable=False),
        sa.Column("base_location", sa.String(length=120), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("archetype", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ps_number"),
    )
    op.create_index("ix_employee_ps_number", "employee", ["ps_number"])
    op.create_index("ix_employee_company_code", "employee", ["company_code"])
    op.create_index("ix_employee_manager_ps_number", "employee", ["manager_ps_number"])
    op.create_index("ix_employee_company_status", "employee", ["company_code", "status"])

    op.create_table(
        "employee_performance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("assessment_year", sa.Integer(), nullable=False),
        sa.Column("mvg_rating", sa.Float(), nullable=True),
        sa.Column("cp_rating", sa.Float(), nullable=True),
        sa.Column("pdr_rating", sa.Float(), nullable=True),
        sa.Column("feedback_entries_ytd", sa.Integer(), nullable=False),
        sa.Column("kra_submitted", sa.Boolean(), nullable=False),
        sa.Column("mid_term_completed", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employee.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", "assessment_year", name="uq_emp_perf_year"),
    )
    op.create_index("ix_employee_performance_employee_id", "employee_performance", ["employee_id"])

    op.create_table(
        "employee_learning",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("course_name", sa.String(length=200), nullable=False),
        sa.Column("completed_on", sa.String(length=10), nullable=True),
        sa.Column("l1_rating_5", sa.Float(), nullable=True),
        sa.Column("tni_identified", sa.Boolean(), nullable=False),
        sa.Column("tni_fulfilled", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employee.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_employee_learning_employee_id", "employee_learning", ["employee_id"])

    op.create_table(
        "employee_skill",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("skill_type", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("proficiency", sa.String(length=48), nullable=False),
        sa.Column("mapped_to_role", sa.Boolean(), nullable=False),
        sa.Column("valid_until", sa.String(length=10), nullable=True),
        sa.ForeignKeyConstraint(["employee_id"], ["employee.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_employee_skill_employee_id", "employee_skill", ["employee_id"])

    op.create_table(
        "employee_development",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("dc_type", sa.String(length=48), nullable=True),
        sa.Column("dc_score", sa.Float(), nullable=True),
        sa.Column("pli_completed", sa.Boolean(), nullable=False),
        sa.Column("has_idp", sa.Boolean(), nullable=False),
        sa.Column("nine_box", sa.String(length=24), nullable=True),
        sa.ForeignKeyConstraint(["employee_id"], ["employee.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", "year", name="uq_emp_dev_year"),
    )
    op.create_index("ix_employee_development_employee_id", "employee_development", ["employee_id"])

    op.create_table(
        "employee_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("effective_date", sa.String(length=10), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("from_ic", sa.String(length=32), nullable=True),
        sa.Column("to_ic", sa.String(length=32), nullable=True),
        sa.Column("from_grade", sa.String(length=32), nullable=True),
        sa.Column("to_grade", sa.String(length=32), nullable=True),
        sa.Column("regrettable", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employee.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_employee_event_employee_id", "employee_event", ["employee_id"])
    op.create_index("ix_employee_event_emp_date", "employee_event", ["employee_id", "effective_date"])


def downgrade() -> None:
    op.drop_table("employee_event")
    op.drop_table("employee_development")
    op.drop_table("employee_skill")
    op.drop_table("employee_learning")
    op.drop_table("employee_performance")
    op.drop_table("employee")
