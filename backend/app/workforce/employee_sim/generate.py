"""Deterministic SF-shaped workforce census generator (demo scale)."""
from __future__ import annotations

import hashlib
import random
from calendar import monthrange
from datetime import date, timedelta

from .schemas import (
    Archetype,
    EmployeeDevRecord,
    EmployeeEventRecord,
    EmployeeLearningRecord,
    EmployeePerformanceRecord,
    EmployeeRecord,
    EmployeeSkillRecord,
    WorkforceBatch,
)

# Demo headcount band per IC (plan: ~80–150).
_DEFAULT_N = (90, 140)

_QUALITY = {"strong": 0.92, "steady": 0.82, "struggling": 0.64, "early_stage": 0.55}

_DEPARTMENTS = [
    ("Engineering", "ENG"),
    ("Operations", "OPS"),
    ("Finance", "FIN"),
    ("HR", "HR"),
    ("Sales", "SAL"),
    ("Projects", "PRJ"),
    ("Digital", "DIG"),
    ("Quality", "QA"),
]

_GRADES = [
    ("E1", "Junior", 3),
    ("E2", "Associate", 4),
    ("E3", "Senior", 5),
    ("M1", "Manager", 6),
    ("M2", "Sr Manager", 7),
    ("M3C", "General Manager", 8),
    ("M4A", "Director", 9),
]

_LOCATIONS = ["Mumbai", "Chennai", "Bengaluru", "Hyderabad", "Pune", "Delhi NCR", "Vadodara"]
_FIRST = ["Asha", "Rahul", "Priya", "Vikram", "Neha", "Arjun", "Meera", "Karan", "Ananya", "Rohan",
          "Sneha", "Aditya", "Isha", "Nikhil", "Divya", "Sanjay", "Pooja", "Amit", "Kavya", "Dev"]
_LAST = ["Sharma", "Patel", "Nair", "Iyer", "Reddy", "Khan", "Gupta", "Singh", "Das", "Mehta",
         "Joshi", "Pillai", "Banerjee", "Chopra", "Desai"]

_COURSES = [
    "Safety Induction", "Project Controls 101", "Leadership Essentials", "Data Literacy",
    "Customer Excellence", "Agile Delivery", "Financial Acumen", "Inclusive Leadership",
]
_ROLE_SKILLS = [
    "Python", "Project Management", "Stakeholder Mgmt", "Domain Engineering",
    "Analytics", "People Leadership", "Risk Management", "Design Thinking",
]
_LANGS = ["English", "Hindi", "Tamil", "Marathi", "Telugu", "Kannada"]
_NINE_BOX = ["1A", "1B", "2A", "2B", "3A", "3B", "3C"]
_EXIT_REASONS = ["compensation", "role", "brand", "work_culture", "career_growth", "relocation", "other"]


def _rng(*parts: str) -> random.Random:
    digest = hashlib.sha256("|".join(parts).encode()).digest()[:8]
    return random.Random(int.from_bytes(digest, "big"))


def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, monthrange(y, m)[1])
    return date(y, m, day)


def _iso(d: date) -> str:
    return d.isoformat()


def _pick_n(r: random.Random, lo: int, hi: int) -> int:
    return int(r.randint(lo, hi))


def simulate_ic(
    company_code: str,
    archetype: Archetype | None = None,
    n: int | None = None,
    *,
    as_of: date | None = None,
    seed: str | None = None,
) -> WorkforceBatch:
    """Generate a demo census for one IC. Stable given (company_code, seed)."""
    as_of = as_of or date(2026, 11, 1)
    year = as_of.year if as_of.month >= 4 else as_of.year - 1
    assessment_year = year  # FY label ≈ calendar year of assessment cycle start
    r = _rng("census", company_code, seed or "v1", as_of.isoformat())
    arch: Archetype = archetype or r.choice(["strong", "steady", "steady", "struggling", "early_stage"])
    q = _QUALITY[arch]
    size = n if n is not None else _pick_n(r, *_DEFAULT_N)

    # Active + recent leavers so attrition/mobility metrics have signal.
    n_active = size
    n_leavers = max(3, int(size * r.uniform(0.06, 0.14) * (1.35 - q)))
    total = n_active + n_leavers

    # Manager pool: ~1 manager per 6–9 people.
    n_managers = max(3, n_active // r.randint(6, 9))
    manager_ps: list[str] = []
    employees: list[EmployeeRecord] = []

    def ps_for(i: int) -> str:
        return f"{company_code}{100000 + i}"

    # Pre-assign managers from the first n_managers active people.
    for i in range(n_managers):
        manager_ps.append(ps_for(i))

    for i in range(total):
        is_leaver = i >= n_active
        ps = ps_for(i)
        dept_name, dept_code = _DEPARTMENTS[i % len(_DEPARTMENTS)]
        grade, title_suffix, cpr_floor = _GRADES[
            min(len(_GRADES) - 1, int(r.betavariate(2.2, 3.5) * len(_GRADES)))
        ]
        # Prefer higher grades for early manager slots.
        if i < n_managers:
            grade, title_suffix, cpr_floor = _GRADES[r.randint(3, len(_GRADES) - 1)]

        tenure_m = int(max(1, r.lognormvariate(3.4, 0.7)))
        tenure_m = min(tenure_m, 240)
        pos_m = int(max(1, min(tenure_m, r.gauss(tenure_m * 0.55, 8))))
        hire = _add_months(as_of, -tenure_m)
        joining = hire + timedelta(days=r.randint(0, 14))

        is_trainee = (not is_leaver) and r.random() < (0.14 if arch == "early_stage" else 0.10)
        top_talent = (not is_leaver) and (r.random() < (0.12 * q + 0.03))
        cpr = cpr_floor + (r.randint(0, 2) if top_talent else r.randint(-1, 1))
        cpr = max(1, min(10, cpr))
        if top_talent:
            cpr = max(cpr, 7)

        mgr = None
        if i >= n_managers and not is_leaver:
            mgr = manager_ps[i % len(manager_ps)]
        elif i >= n_managers and is_leaver:
            mgr = manager_ps[i % len(manager_ps)]

        separation = None
        status = "active"
        if is_leaver:
            status = "separated"
            sep_ago = r.randint(1, 11)
            separation = _iso(_add_months(as_of, -sep_ago))

        contract_end = None
        if is_trainee:
            contract_end = _iso(_add_months(joining, 36))

        emp = EmployeeRecord(
            ps_number=ps,
            company_code=company_code,
            full_name=f"{r.choice(_FIRST)} {r.choice(_LAST)}",
            legal_entity=f"{company_code} Legal Entity",
            business_unit=f"{company_code}-{dept_code}",
            department=dept_name,
            job_code=f"{dept_code}-{grade}",
            job_title=f"{title_suffix} {dept_name}",
            job_function=dept_name,
            grade_cadre=grade,
            band=grade[0],
            employment_type="Trainee" if is_trainee else r.choice(["Permanent", "Permanent", "Contract"]),
            appointment_type="Campus" if is_trainee else "Lateral",
            employee_group="Trainee" if is_trainee else "Staff",
            manager_ps_number=mgr,
            position_id=f"POS-{company_code}-{i + 1:04d}",
            hire_date=_iso(hire),
            joining_date=_iso(joining),
            separation_date=separation,
            status=status,  # type: ignore[arg-type]
            time_in_company_months=tenure_m if not is_leaver else max(1, tenure_m - 6),
            time_in_position_months=pos_m,
            is_trainee=is_trainee,
            contract_training_end_date=contract_end,
            top_talent=top_talent,
            cpr_band=cpr,
            willing_to_relocate=r.random() < 0.35,
            base_location=r.choice(_LOCATIONS),
            archetype=arch,
        )

        # Performance (eligible = active non-trainee, or most actives).
        eligible = status == "active" and not is_trainee
        kra = eligible and r.random() < q
        mid = eligible and r.random() < max(0.35, q - 0.08)
        feedback = 0
        if eligible:
            feedback = max(0, int(round(r.gauss(2.4 * q + 0.2, 0.9))))
        emp.performance.append(
            EmployeePerformanceRecord(
                assessment_year=assessment_year,
                mvg_rating=round(min(5.0, max(1.0, r.gauss(3.0 + 1.2 * q, 0.45))), 2) if eligible else None,
                cp_rating=round(min(5.0, max(1.0, r.gauss(3.1 + q, 0.4))), 2) if eligible else None,
                pdr_rating=round(min(5.0, max(1.0, r.gauss(3.0 + q, 0.5))), 2) if eligible and r.random() < 0.4 else None,
                feedback_entries_ytd=feedback,
                kra_submitted=kra,
                mid_term_completed=mid,
            )
        )

        # Learning / TNI
        tni_id = eligible and r.random() < (0.75 + 0.2 * q)
        tni_ok = tni_id and r.random() < max(0.4, q - 0.05)
        n_courses = r.randint(0, 3) if status == "active" else r.randint(0, 1)
        for c_i in range(n_courses):
            done = r.random() < q
            emp.learning.append(
                EmployeeLearningRecord(
                    course_name=r.choice(_COURSES),
                    completed_on=_iso(_add_months(as_of, -r.randint(1, 10))) if done else None,
                    l1_rating_5=round(min(5.0, max(1.0, r.gauss(3.0 + 1.5 * q, 0.35))), 2) if done else None,
                    tni_identified=tni_id and c_i == 0,
                    tni_fulfilled=tni_ok and c_i == 0 and done,
                    source="leadership_program" if grade.startswith("M") and r.random() < 0.3 else "course",
                )
            )
        if tni_id and not emp.learning:
            emp.learning.append(
                EmployeeLearningRecord(
                    course_name="TNI Placeholder",
                    completed_on=None,
                    tni_identified=True,
                    tni_fulfilled=False,
                )
            )

        # Skills
        mapped = status == "active" and r.random() < max(0.35, q - 0.05)
        if status == "active":
            for skill in r.sample(_ROLE_SKILLS, k=r.randint(1, 3)):
                emp.skills.append(
                    EmployeeSkillRecord(
                        skill_type="role_skill",
                        name=skill,
                        proficiency=r.choice(["Beginner", "Intermediate", "Advanced"]),
                        mapped_to_role=mapped,
                    )
                )
            if r.random() < 0.4:
                emp.skills.append(
                    EmployeeSkillRecord(
                        skill_type="certification",
                        name=r.choice(["PMP", "AWS SAA", "Six Sigma Green Belt", "ITIL"]),
                        proficiency="Certified",
                        mapped_to_role=mapped,
                        valid_until=_iso(_add_months(as_of, r.randint(6, 36))),
                    )
                )
            emp.skills.append(
                EmployeeSkillRecord(
                    skill_type="language",
                    name=r.choice(_LANGS),
                    proficiency=r.choice(["Speaking", "Reading", "Writing", "Fluent"]),
                    mapped_to_role=False,
                )
            )

        # Development / PLI / IDP — M3C/M4A proxies + top talent
        pli_eligible = grade in ("M3C", "M4A") or (top_talent and grade.startswith("M"))
        has_idp = (top_talent or pli_eligible) and r.random() < max(0.4, q - 0.05)
        pli_done = pli_eligible and r.random() < q
        emp.development.append(
            EmployeeDevRecord(
                year=assessment_year,
                dc_type="PLI" if pli_eligible else ("DC" if top_talent and r.random() < 0.5 else None),
                dc_score=round(r.uniform(2.5, 4.8), 2) if pli_done or (top_talent and r.random() < 0.4) else None,
                pli_completed=pli_done,
                has_idp=has_idp,
                nine_box=r.choice(_NINE_BOX) if (top_talent or pli_eligible) else None,
            )
        )

        # Events
        emp.events.append(
            EmployeeEventRecord(event_type="hire", effective_date=_iso(hire), reason_code="new_hire")
        )
        if tenure_m > 24 and r.random() < 0.35:
            promo_date = _iso(_add_months(hire, r.randint(12, max(13, tenure_m - 3))))
            grade_idx = next((i for i, g in enumerate(_GRADES) if g[0] == grade), 1)
            prev = _GRADES[max(0, grade_idx - 1)][0]
            emp.events.append(
                EmployeeEventRecord(
                    event_type="promote",
                    effective_date=promo_date,
                    reason_code="july_jan_promotion",
                    from_grade=prev,
                    to_grade=grade,
                )
            )
        if status == "active" and r.random() < 0.12:
            emp.events.append(
                EmployeeEventRecord(
                    event_type="transfer",
                    effective_date=_iso(_add_months(as_of, -r.randint(2, 18))),
                    reason_code="internal_move",
                    from_ic=company_code,
                    to_ic=company_code,
                )
            )
        if status == "active" and r.random() < 0.08:
            emp.events.append(
                EmployeeEventRecord(
                    event_type="deputation",
                    effective_date=_iso(_add_months(as_of, -r.randint(1, 12))),
                    reason_code="project_deputation",
                    from_ic=company_code,
                    to_ic=company_code,
                )
            )
        if is_leaver and separation:
            regrettable = top_talent or cpr >= 7 or r.random() < (0.35 * (1.2 - q))
            emp.events.append(
                EmployeeEventRecord(
                    event_type="resign",
                    effective_date=separation,
                    reason_code=r.choice(_EXIT_REASONS),
                    regrettable=regrettable,
                )
            )
            emp.events.append(
                EmployeeEventRecord(
                    event_type="separate",
                    effective_date=separation,
                    reason_code="exit",
                    regrettable=regrettable,
                )
            )

        employees.append(emp)

    # IC-level knobs for non-SF / still-needed CompanyRaw fields
    active_hc = sum(1 for e in employees if e.status == "active")
    offers = max(5, int(active_hc * r.uniform(0.08, 0.22)))
    joined = min(offers, round(offers * min(1.0, max(0.4, r.gauss(q + 0.03, 0.06)))))
    cohort = max(1, joined + r.randint(0, 4))
    ahc_elig = max(1, int(active_hc * r.uniform(0.7, 0.95)))

    return WorkforceBatch(
        company_code=company_code,
        archetype=arch,
        as_of=_iso(as_of),
        assessment_year=assessment_year,
        employees=employees,
        ppw_on_time=1 if r.random() < q else 0,
        training_calendar=2 if r.random() < q else r.choice([0, 1]),
        offers=offers,
        joined=joined,
        avg_days_to_fill=round(r.gauss(60 / max(q, 0.3) * 0.95, 8), 1),
        positions_closed=max(1, int(offers * r.uniform(0.6, 1.0))),
        hire_cohort=cohort,
        retained_12m=min(cohort, round(cohort * min(1.0, max(0.4, r.gauss(q + 0.05, 0.05))))),
        ahc_eligible=ahc_elig,
        ahc_completed=round(ahc_elig * min(1.0, max(0.3, r.gauss(q - 0.1, 0.08)))),
        unique_logins=round(active_hc * min(1.0, max(0.3, r.gauss(q - 0.05, 0.08)))),
    )


def simulate_group(
    assignments: list[tuple[str, Archetype]],
    *,
    per_ic: int | None = None,
    as_of: date | None = None,
    seed: str | None = None,
) -> list[WorkforceBatch]:
    return [
        simulate_ic(code, arch, n=per_ic, as_of=as_of, seed=seed)
        for code, arch in assignments
    ]
