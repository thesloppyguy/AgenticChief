"""Pydantic mirrors of the SF-shaped workforce census tables."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Archetype = Literal["strong", "steady", "struggling", "early_stage"]
EmployeeStatus = Literal["active", "separated"]
SkillType = Literal["role_skill", "certification", "language"]
LearningSource = Literal["course", "leadership_program"]
EventType = Literal["hire", "promote", "transfer", "deputation", "resign", "separate"]


class EmployeePerformanceRecord(BaseModel):
    assessment_year: int
    mvg_rating: float | None = None
    cp_rating: float | None = None
    pdr_rating: float | None = None
    feedback_entries_ytd: int = 0
    kra_submitted: bool = False
    mid_term_completed: bool = False


class EmployeeLearningRecord(BaseModel):
    course_name: str
    completed_on: str | None = None
    l1_rating_5: float | None = None
    tni_identified: bool = False
    tni_fulfilled: bool = False
    source: LearningSource = "course"


class EmployeeSkillRecord(BaseModel):
    skill_type: SkillType
    name: str
    proficiency: str = ""
    mapped_to_role: bool = False
    valid_until: str | None = None


class EmployeeDevRecord(BaseModel):
    year: int
    dc_type: str | None = None
    dc_score: float | None = None
    pli_completed: bool = False
    has_idp: bool = False
    nine_box: str | None = None


class EmployeeEventRecord(BaseModel):
    event_type: EventType
    effective_date: str
    reason_code: str = ""
    from_ic: str | None = None
    to_ic: str | None = None
    from_grade: str | None = None
    to_grade: str | None = None
    regrettable: bool = False


class EmployeeRecord(BaseModel):
    ps_number: str
    company_code: str
    full_name: str = ""
    legal_entity: str = ""
    business_unit: str = ""
    department: str = ""
    job_code: str = ""
    job_title: str = ""
    job_function: str = ""
    grade_cadre: str = ""
    band: str = ""
    employment_type: str = "Permanent"
    appointment_type: str = ""
    employee_group: str = ""
    manager_ps_number: str | None = None
    position_id: str = ""
    hire_date: str
    joining_date: str
    separation_date: str | None = None
    status: EmployeeStatus = "active"
    time_in_company_months: int = 0
    time_in_position_months: int = 0
    is_trainee: bool = False
    contract_training_end_date: str | None = None
    top_talent: bool = False
    cpr_band: int = 0
    willing_to_relocate: bool = False
    base_location: str = ""
    archetype: Archetype = "steady"
    performance: list[EmployeePerformanceRecord] = Field(default_factory=list)
    learning: list[EmployeeLearningRecord] = Field(default_factory=list)
    skills: list[EmployeeSkillRecord] = Field(default_factory=list)
    development: list[EmployeeDevRecord] = Field(default_factory=list)
    events: list[EmployeeEventRecord] = Field(default_factory=list)


class WorkforceBatch(BaseModel):
    company_code: str
    archetype: Archetype
    as_of: str  # YYYY-MM-DD
    assessment_year: int
    employees: list[EmployeeRecord]
    # Company-level process flags not owned by a single employee
    ppw_on_time: Literal[0, 1] = 1
    training_calendar: Literal[0, 1, 2] = 2
    # TA / wellness / engagement proxies kept at IC level (other systems or sim knobs)
    offers: int = 0
    joined: int = 0
    avg_days_to_fill: float = 60.0
    positions_closed: int = 0
    hire_cohort: int = 0
    retained_12m: int = 0
    ahc_eligible: int = 0
    ahc_completed: int = 0
    unique_logins: int = 0
