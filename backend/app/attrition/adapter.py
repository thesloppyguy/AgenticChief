"""Map AttritionEmployee → Employee census rows for workforce metrics."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AttritionEmployee, Employee


def upsert_employee_from_attrition(db: Session, row: AttritionEmployee) -> Employee:
    """Keep the SF-shaped Employee table in sync so compute_metrics can read live data."""
    emp = db.scalar(select(Employee).where(Employee.ps_number == row.employee_id))
    if emp is None:
        emp = Employee(
            ps_number=row.employee_id,
            hire_date=row.hire_date or "",
            joining_date=row.joining_date or "",
        )
        db.add(emp)

    emp.company_code = row.company_code
    emp.legal_entity = row.legal_entity or ""
    emp.business_unit = row.business_unit or ""
    emp.department = row.department or ""
    emp.job_code = row.job_subfamily or ""
    emp.job_title = row.exit_designation or row.job_function or ""
    emp.job_function = row.job_function or row.job_family or ""
    emp.grade_cadre = row.grade or row.pay_grade or ""
    emp.band = row.band or ""
    emp.employment_type = row.employment_type or row.employee_group or "Permanent"
    emp.appointment_type = row.appointment_type or ""
    emp.employee_group = row.employee_group or ""
    emp.manager_ps_number = row.manager_user_id
    emp.hire_date = row.hire_date or row.joining_date or emp.hire_date or ""
    emp.joining_date = row.joining_date or row.hire_date or emp.joining_date or ""
    emp.separation_date = row.separation_date or row.last_working_date
    emp.status = row.status or ("separated" if emp.separation_date else "active")
    emp.time_in_company_months = row.time_in_company_months or 0
    emp.is_trainee = bool(row.is_trainee)
    emp.contract_training_end_date = row.contract_training_end_date
    emp.base_location = row.base_location or ""
    emp.archetype = "steady"
    return emp
