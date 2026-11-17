"""SF-shaped workforce census simulation: generate employees, aggregate to CompanyRaw."""
from __future__ import annotations

from .aggregate import to_company_raw
from .generate import simulate_group, simulate_ic
from .persist import clear_census, load_census_from_db, persist_batch, seed_census
from .schemas import (
    EmployeeDevRecord,
    EmployeeEventRecord,
    EmployeeLearningRecord,
    EmployeePerformanceRecord,
    EmployeeRecord,
    EmployeeSkillRecord,
    WorkforceBatch,
)

__all__ = [
    "EmployeeDevRecord",
    "EmployeeEventRecord",
    "EmployeeLearningRecord",
    "EmployeePerformanceRecord",
    "EmployeeRecord",
    "EmployeeSkillRecord",
    "WorkforceBatch",
    "clear_census",
    "load_census_from_db",
    "persist_batch",
    "seed_census",
    "simulate_group",
    "simulate_ic",
    "to_company_raw",
]
