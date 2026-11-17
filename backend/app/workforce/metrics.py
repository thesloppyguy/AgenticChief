"""Open metric surface over the SF-shaped employee census.

Not limited to the fixed 23 scorecard KPIs — Copilot / CXO tools can query these
dimensions and invent further formulas without schema changes.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Employee,
    EmployeeDevelopment,
    EmployeeEvent,
    EmployeeLearning,
    EmployeePerformance,
    EmployeeSkill,
)

# Field dictionary for AI / skills — keep in sync with models.
CENSUS_FIELD_DICTIONARY: dict[str, str] = {
    "employee.company_code": "Independent Company code (LTF, LTMR, LTR, LTTS, LTIM)",
    "employee.status": "active | separated",
    "employee.grade_cadre": "Grade / cadre (E1–M4A)",
    "employee.band": "Band letter derived from grade",
    "employee.cpr_band": "CPR scale 1–10; 7+ treated as top-talent band",
    "employee.top_talent": "Flagged top talent",
    "employee.is_trainee": "Trainee / campus hire",
    "employee.time_in_company_months": "Tenure in months",
    "employee.time_in_position_months": "Time in current position (months)",
    "employee.manager_ps_number": "Immediate supervisor PS number",
    "employee.job_function": "Job function / department family",
    "employee.willing_to_relocate": "Geographic mobility willingness",
    "employee_performance.kra_submitted": "KRA submitted this assessment year",
    "employee_performance.mid_term_completed": "Mid-term review completed",
    "employee_performance.feedback_entries_ytd": "Continuous feedback entries YTD",
    "employee_learning.tni_identified / tni_fulfilled": "Training needs identification / fulfilment",
    "employee_learning.l1_rating_5": "Level-1 training feedback (1–5)",
    "employee_skill.mapped_to_role": "Skill mapped to role proficiency",
    "employee_development.pli_completed / has_idp / nine_box": "PLI, IDP, succession nine-box",
    "employee_event.event_type": "hire | promote | transfer | deputation | resign | separate",
    "employee_event.regrettable": "Regrettable exit flag",
    "employee_event.reason_code": "Exit / movement reason (compensation, role, …)",
}


def _tenure_band(months: int) -> str:
    if months < 12:
        return "0-1y"
    if months < 36:
        return "1-3y"
    if months < 60:
        return "3-5y"
    return "5y+"


def _pct(n: float, d: float) -> float | None:
    if d <= 0:
        return None
    return round(100.0 * n / d, 2)


def compute_metrics(db: Session, company_code: str | None = None) -> dict[str, Any]:
    """Compute inventable CXO metrics from persisted census rows."""
    q = select(Employee)
    if company_code:
        q = q.where(Employee.company_code == company_code.upper())
    employees = list(db.scalars(q))
    if not employees:
        return {
            "available": False,
            "company_code": company_code,
            "field_dictionary": CENSUS_FIELD_DICTIONARY,
            "metrics": {},
            "note": "No employee census loaded. Seed via seed_lnt or generate_employee_census.",
        }

    ids = [e.id for e in employees]
    perfs = list(
        db.scalars(select(EmployeePerformance).where(EmployeePerformance.employee_id.in_(ids)))
    )
    learns = list(
        db.scalars(select(EmployeeLearning).where(EmployeeLearning.employee_id.in_(ids)))
    )
    skills = list(db.scalars(select(EmployeeSkill).where(EmployeeSkill.employee_id.in_(ids))))
    devs = list(
        db.scalars(select(EmployeeDevelopment).where(EmployeeDevelopment.employee_id.in_(ids)))
    )
    events = list(db.scalars(select(EmployeeEvent).where(EmployeeEvent.employee_id.in_(ids))))

    pmap: dict[int, list] = defaultdict(list)
    for p in perfs:
        pmap[p.employee_id].append(p)
    lmap: dict[int, list] = defaultdict(list)
    for lr in learns:
        lmap[lr.employee_id].append(lr)
    smap: dict[int, list] = defaultdict(list)
    for sk in skills:
        smap[sk.employee_id].append(sk)
    dmap: dict[int, list] = defaultdict(list)
    for d in devs:
        dmap[d.employee_id].append(d)
    emap: dict[int, list] = defaultdict(list)
    for ev in events:
        emap[ev.employee_id].append(ev)

    active = [e for e in employees if e.status == "active"]
    leavers = [e for e in employees if e.status == "separated"]
    active_n = len(active)
    total_n = len(employees)

    # Retention / attrition
    attrition_pct = _pct(len(leavers), active_n + len(leavers))
    by_grade_attr: dict[str, dict] = {}
    for e in employees:
        g = e.grade_cadre or "unknown"
        bucket = by_grade_attr.setdefault(g, {"active": 0, "separated": 0})
        bucket[e.status if e.status in ("active", "separated") else "active"] += 1
    attrition_by_grade = {
        g: {
            **v,
            "attrition_pct": _pct(v["separated"], v["active"] + v["separated"]),
        }
        for g, v in sorted(by_grade_attr.items())
    }
    by_tenure: dict[str, dict] = defaultdict(lambda: {"active": 0, "separated": 0})
    for e in employees:
        b = _tenure_band(e.time_in_company_months)
        by_tenure[b][e.status if e.status in ("active", "separated") else "active"] += 1
    attrition_by_tenure = {
        k: {**v, "attrition_pct": _pct(v["separated"], v["active"] + v["separated"])}
        for k, v in sorted(by_tenure.items())
    }
    exit_reasons: dict[str, int] = defaultdict(int)
    regrettable = 0
    for e in leavers:
        for ev in emap[e.id]:
            if ev.event_type == "resign":
                exit_reasons[ev.reason_code or "other"] += 1
                if ev.regrettable:
                    regrettable += 1
                break

    # Manager health
    spans: dict[str, int] = defaultdict(int)
    for e in active:
        if e.manager_ps_number:
            spans[e.manager_ps_number] += 1
    team_attrition: dict[str, dict] = defaultdict(lambda: {"active": 0, "separated": 0})
    for e in employees:
        if not e.manager_ps_number:
            continue
        team_attrition[e.manager_ps_number][
            e.status if e.status in ("active", "separated") else "active"
        ] += 1
    feedback_vals = [
        p.feedback_entries_ytd for e in active for p in pmap[e.id]
    ]
    avg_feedback = round(sum(feedback_vals) / len(feedback_vals), 2) if feedback_vals else None

    # Stagnation
    stagnant_pos = sum(1 for e in active if e.time_in_position_months >= 36)
    stagnant_grade = sum(1 for e in active if e.time_in_company_months >= 48 and e.time_in_position_months >= 36)

    # Mobility
    transfers = sum(1 for ev in events if ev.event_type == "transfer")
    deputations = sum(1 for ev in events if ev.event_type == "deputation")
    promotions = sum(1 for ev in events if ev.event_type == "promote")

    # Skills / learning
    mapped = sum(
        1
        for e in active
        if any(s.mapped_to_role and s.skill_type == "role_skill" for s in smap[e.id])
    )
    certs = sum(
        1 for e in active for s in smap[e.id] if s.skill_type == "certification"
    )
    courses_done = sum(1 for lr in learns if lr.completed_on)
    tni_id = sum(1 for lr in learns if lr.tni_identified)
    tni_ok = sum(1 for lr in learns if lr.tni_fulfilled)

    # Talent / trainee / nine-box
    top = sum(1 for e in active if e.top_talent or e.cpr_band >= 7)
    trainees = [e for e in active if e.is_trainee]
    idp = sum(1 for e in active for d in dmap[e.id] if d.has_idp)
    pli_done = sum(1 for e in active for d in dmap[e.id] if d.pli_completed)
    nine: dict[str, int] = defaultdict(int)
    for e in active:
        for d in dmap[e.id]:
            if d.nine_box:
                nine[d.nine_box] += 1

    by_function_skills: dict[str, dict] = defaultdict(
        lambda: {"active": 0, "skills_mapped": 0}
    )
    for e in active:
        fn = e.job_function or "unknown"
        by_function_skills[fn]["active"] += 1
        if any(s.mapped_to_role and s.skill_type == "role_skill" for s in smap[e.id]):
            by_function_skills[fn]["skills_mapped"] += 1

    metrics = {
        "headcount_active": active_n,
        "headcount_total_incl_leavers": total_n,
        "attrition": {
            "leavers": len(leavers),
            "attrition_pct": attrition_pct,
            "regrettable_exits": regrettable,
            "by_grade": attrition_by_grade,
            "by_tenure_band": attrition_by_tenure,
            "exit_reasons": dict(sorted(exit_reasons.items(), key=lambda x: -x[1])),
        },
        "manager_health": {
            "managers_with_reports": len(spans),
            "avg_span": round(sum(spans.values()) / len(spans), 2) if spans else None,
            "max_span": max(spans.values()) if spans else None,
            "avg_feedback_entries_ytd": avg_feedback,
            "teams_with_leavers": sum(
                1 for v in team_attrition.values() if v["separated"] > 0
            ),
        },
        "stagnation": {
            "time_in_position_ge_36m": stagnant_pos,
            "time_in_position_ge_36m_pct": _pct(stagnant_pos, active_n),
            "long_tenure_and_stagnant_role": stagnant_grade,
        },
        "mobility": {
            "transfers": transfers,
            "deputations": deputations,
            "promotions": promotions,
            "transfer_rate_pct": _pct(transfers, active_n),
            "promotion_rate_pct": _pct(promotions, active_n),
            "willing_to_relocate_pct": _pct(
                sum(1 for e in active if e.willing_to_relocate), active_n
            ),
        },
        "skills_learning": {
            "role_skill_coverage_pct": _pct(mapped, active_n),
            "certifications_held": certs,
            "courses_completed": courses_done,
            "courses_per_active": round(courses_done / active_n, 2) if active_n else None,
            "tni_fulfilment_pct": _pct(tni_ok, tni_id) if tni_id else None,
            "by_job_function": {
                k: {
                    **v,
                    "coverage_pct": _pct(v["skills_mapped"], v["active"]),
                }
                for k, v in sorted(by_function_skills.items())
            },
        },
        "talent": {
            "top_talent_or_cpr7_pct": _pct(top, active_n),
            "idp_count": idp,
            "pli_completed": pli_done,
            "nine_box_distribution": dict(sorted(nine.items())),
            "trainees_active": len(trainees),
            "trainee_pct": _pct(len(trainees), active_n),
        },
    }

    return {
        "available": True,
        "company_code": company_code.upper() if company_code else None,
        "scope": company_code.upper() if company_code else "group",
        "field_dictionary": CENSUS_FIELD_DICTIONARY,
        "metrics": metrics,
        "inventable_examples": [
            "regrettable attrition among CPR 7+ by resignation reason",
            "manager span vs team attrition correlation",
            "cadre stagnation (time-in-position ≥ 36m) by job function",
            "skill coverage gap by job_function vs learning velocity",
            "trainee conversion / remaining under 36 months",
            "promotion rate among nine-box 3A/3B vs rest",
            "mobility willingness vs actual transfer/deputation rate",
        ],
        "note": (
            "Census-backed open metrics. Scorecard 23 KPIs remain in the KPI engine; "
            "use these fields to invent additional CXO insights."
        ),
    }
