"""ICHRATTRITION local store: attrition_employee + attrition_sync_run.

Revision ID: 0017
Revises: 0016
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Align census employee.ps_number index with model (unique=True, index=True).
    op.drop_index("ix_employee_ps_number", table_name="employee")
    op.create_index("ix_employee_ps_number", "employee", ["ps_number"], unique=True)

    op.create_table(
        "attrition_employee",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.String(length=32), nullable=False),
        sa.Column("company_code", sa.String(length=32), nullable=False),
        sa.Column("ic_description", sa.String(length=200), nullable=False),
        sa.Column("legal_entity", sa.String(length=200), nullable=False),
        sa.Column("country", sa.String(length=64), nullable=False),
        sa.Column("sbg", sa.String(length=120), nullable=False),
        sa.Column("business_unit", sa.String(length=200), nullable=False),
        sa.Column("department", sa.String(length=300), nullable=False),
        sa.Column("department_code", sa.String(length=64), nullable=False),
        sa.Column("base_location", sa.String(length=120), nullable=False),
        sa.Column("pay_grade", sa.String(length=32), nullable=False),
        sa.Column("grade", sa.String(length=32), nullable=False),
        sa.Column("band", sa.String(length=32), nullable=False),
        sa.Column("appointment_type", sa.String(length=48), nullable=False),
        sa.Column("employee_group", sa.String(length=64), nullable=False),
        sa.Column("employment_type", sa.String(length=48), nullable=True),
        sa.Column("hire_date", sa.String(length=10), nullable=True),
        sa.Column("joining_date", sa.String(length=10), nullable=True),
        sa.Column("trainee_experience", sa.String(length=32), nullable=True),
        sa.Column("contract_training_end_date", sa.String(length=10), nullable=True),
        sa.Column("separation_date", sa.String(length=10), nullable=True),
        sa.Column("payroll_end_date", sa.String(length=10), nullable=True),
        sa.Column("notice_period", sa.String(length=32), nullable=True),
        sa.Column("notice_period_policy", sa.String(length=64), nullable=True),
        sa.Column("resignation_date", sa.String(length=10), nullable=True),
        sa.Column("last_working_date", sa.String(length=10), nullable=True),
        sa.Column("request_relieving_date", sa.String(length=10), nullable=True),
        sa.Column("doj_resignation_port", sa.String(length=10), nullable=True),
        sa.Column("resignation_reason", sa.String(length=200), nullable=True),
        sa.Column("manager_user_id", sa.String(length=32), nullable=True),
        sa.Column("manager_name", sa.String(length=120), nullable=True),
        sa.Column("job_family", sa.String(length=120), nullable=True),
        sa.Column("job_subfamily", sa.String(length=64), nullable=True),
        sa.Column("job_subfamily_desc", sa.String(length=200), nullable=True),
        sa.Column("job_function", sa.String(length=200), nullable=True),
        sa.Column("ok_to_rehire", sa.Boolean(), nullable=True),
        sa.Column("exit_interview_required", sa.Boolean(), nullable=True),
        sa.Column("date_of_joining_exit_port", sa.String(length=10), nullable=True),
        sa.Column("date_of_separation_exit_port", sa.String(length=10), nullable=True),
        sa.Column("exit_designation", sa.String(length=120), nullable=True),
        sa.Column("exit_tenure", sa.String(length=64), nullable=True),
        sa.Column("exit_trigger_hr", sa.String(length=500), nullable=True),
        sa.Column("exit_trigger_employee", sa.String(length=500), nullable=True),
        sa.Column("exit_flag_compensation", sa.Boolean(), nullable=True),
        sa.Column("exit_flag_brand", sa.Boolean(), nullable=True),
        sa.Column("exit_flag_role", sa.Boolean(), nullable=True),
        sa.Column("exit_flag_culture", sa.Boolean(), nullable=True),
        sa.Column("exit_recommend_friends", sa.String(length=64), nullable=True),
        sa.Column("exit_would_rejoin", sa.String(length=64), nullable=True),
        sa.Column("current_cadre", sa.String(length=32), nullable=True),
        sa.Column("mvg_rating", sa.Float(), nullable=True),
        sa.Column("cp_rating", sa.Float(), nullable=True),
        sa.Column("pdr_rating", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("is_trainee", sa.Boolean(), nullable=False),
        sa.Column("time_in_company_months", sa.Integer(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_attrition_employee_employee_id",
        "attrition_employee",
        ["employee_id"],
        unique=True,
    )
    op.create_index("ix_attrition_employee_company_code", "attrition_employee", ["company_code"])
    op.create_index("ix_attrition_employee_manager_user_id", "attrition_employee", ["manager_user_id"])
    op.create_index(
        "ix_attrition_employee_company_status",
        "attrition_employee",
        ["company_code", "status"],
    )

    op.create_table(
        "attrition_sync_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("ics_requested", sa.JSON(), nullable=True),
        sa.Column("ics_ok", sa.JSON(), nullable=True),
        sa.Column("ics_failed", sa.JSON(), nullable=True),
        sa.Column("rows_upserted", sa.Integer(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=True),
        sa.Column("triggered_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("attrition_sync_run")
    op.drop_index("ix_attrition_employee_company_status", table_name="attrition_employee")
    op.drop_index("ix_attrition_employee_manager_user_id", table_name="attrition_employee")
    op.drop_index("ix_attrition_employee_company_code", table_name="attrition_employee")
    op.drop_index("ix_attrition_employee_employee_id", table_name="attrition_employee")
    op.drop_table("attrition_employee")
    op.drop_index("ix_employee_ps_number", table_name="employee")
    op.create_index("ix_employee_ps_number", "employee", ["ps_number"], unique=False)
