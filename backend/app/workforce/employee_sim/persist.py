"""Persist / reload WorkforceBatch rows into the census tables."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import (
    Employee,
    EmployeeDevelopment,
    EmployeeEvent,
    EmployeeLearning,
    EmployeePerformance,
    EmployeeSkill,
    MockCompanyData,
)
from app.ingestion.stubgen import CompanyRaw

from .aggregate import to_company_raw
from .generate import simulate_group, simulate_ic
from .schemas import (
    EmployeeDevRecord,
    EmployeeEventRecord,
    EmployeeLearningRecord,
    EmployeePerformanceRecord,
    EmployeeRecord,
    EmployeeSkillRecord,
    WorkforceBatch,
)


def clear_census(db: Session, company_code: str | None = None) -> None:
    """Delete census rows (optionally for one IC)."""
    if company_code:
        ids = list(
            db.scalars(select(Employee.id).where(Employee.company_code == company_code))
        )
        if not ids:
            return
        for model in (
            EmployeeEvent,
            EmployeeDevelopment,
            EmployeeSkill,
            EmployeeLearning,
            EmployeePerformance,
        ):
            db.execute(delete(model).where(model.employee_id.in_(ids)))
        db.execute(delete(Employee).where(Employee.company_code == company_code))
    else:
        for model in (
            EmployeeEvent,
            EmployeeDevelopment,
            EmployeeSkill,
            EmployeeLearning,
            EmployeePerformance,
            Employee,
        ):
            db.execute(delete(model))
    db.flush()


def persist_batch(db: Session, batch: WorkforceBatch) -> int:
    """Insert one IC census. Returns employee row count."""
    n = 0
    for rec in batch.employees:
        row = Employee(
            ps_number=rec.ps_number,
            company_code=rec.company_code,
            legal_entity=rec.legal_entity,
            business_unit=rec.business_unit,
            department=rec.department,
            job_code=rec.job_code,
            job_title=rec.job_title,
            job_function=rec.job_function,
            grade_cadre=rec.grade_cadre,
            band=rec.band,
            employment_type=rec.employment_type,
            appointment_type=rec.appointment_type,
            employee_group=rec.employee_group,
            manager_ps_number=rec.manager_ps_number,
            position_id=rec.position_id,
            hire_date=rec.hire_date,
            joining_date=rec.joining_date,
            separation_date=rec.separation_date,
            status=rec.status,
            time_in_company_months=rec.time_in_company_months,
            time_in_position_months=rec.time_in_position_months,
            is_trainee=rec.is_trainee,
            contract_training_end_date=rec.contract_training_end_date,
            top_talent=rec.top_talent,
            cpr_band=rec.cpr_band,
            willing_to_relocate=rec.willing_to_relocate,
            base_location=rec.base_location,
            full_name=rec.full_name,
            archetype=rec.archetype,
        )
        db.add(row)
        db.flush()
        n += 1
        for p in rec.performance:
            db.add(
                EmployeePerformance(
                    employee_id=row.id,
                    assessment_year=p.assessment_year,
                    mvg_rating=p.mvg_rating,
                    cp_rating=p.cp_rating,
                    pdr_rating=p.pdr_rating,
                    feedback_entries_ytd=p.feedback_entries_ytd,
                    kra_submitted=p.kra_submitted,
                    mid_term_completed=p.mid_term_completed,
                )
            )
        for lr in rec.learning:
            db.add(
                EmployeeLearning(
                    employee_id=row.id,
                    course_name=lr.course_name,
                    completed_on=lr.completed_on,
                    l1_rating_5=lr.l1_rating_5,
                    tni_identified=lr.tni_identified,
                    tni_fulfilled=lr.tni_fulfilled,
                    source=lr.source,
                )
            )
        for sk in rec.skills:
            db.add(
                EmployeeSkill(
                    employee_id=row.id,
                    skill_type=sk.skill_type,
                    name=sk.name,
                    proficiency=sk.proficiency,
                    mapped_to_role=sk.mapped_to_role,
                    valid_until=sk.valid_until,
                )
            )
        for d in rec.development:
            db.add(
                EmployeeDevelopment(
                    employee_id=row.id,
                    year=d.year,
                    dc_type=d.dc_type,
                    dc_score=d.dc_score,
                    pli_completed=d.pli_completed,
                    has_idp=d.has_idp,
                    nine_box=d.nine_box,
                )
            )
        for ev in rec.events:
            db.add(
                EmployeeEvent(
                    employee_id=row.id,
                    event_type=ev.event_type,
                    effective_date=ev.effective_date,
                    reason_code=ev.reason_code,
                    from_ic=ev.from_ic,
                    to_ic=ev.to_ic,
                    from_grade=ev.from_grade,
                    to_grade=ev.to_grade,
                    regrettable=ev.regrettable,
                )
            )
    return n


def _employee_to_record(
    row: Employee,
    performance: list[EmployeePerformance],
    learning: list[EmployeeLearning],
    skills: list[EmployeeSkill],
    development: list[EmployeeDevelopment],
    events: list[EmployeeEvent],
) -> EmployeeRecord:
    return EmployeeRecord(
        ps_number=row.ps_number,
        company_code=row.company_code,
        full_name=row.full_name,
        legal_entity=row.legal_entity,
        business_unit=row.business_unit,
        department=row.department,
        job_code=row.job_code,
        job_title=row.job_title,
        job_function=row.job_function,
        grade_cadre=row.grade_cadre,
        band=row.band,
        employment_type=row.employment_type,
        appointment_type=row.appointment_type,
        employee_group=row.employee_group,
        manager_ps_number=row.manager_ps_number,
        position_id=row.position_id,
        hire_date=row.hire_date,
        joining_date=row.joining_date,
        separation_date=row.separation_date,
        status=row.status,  # type: ignore[arg-type]
        time_in_company_months=row.time_in_company_months,
        time_in_position_months=row.time_in_position_months,
        is_trainee=row.is_trainee,
        contract_training_end_date=row.contract_training_end_date,
        top_talent=row.top_talent,
        cpr_band=row.cpr_band,
        willing_to_relocate=row.willing_to_relocate,
        base_location=row.base_location,
        archetype=row.archetype,  # type: ignore[arg-type]
        performance=[
            EmployeePerformanceRecord(
                assessment_year=p.assessment_year,
                mvg_rating=p.mvg_rating,
                cp_rating=p.cp_rating,
                pdr_rating=p.pdr_rating,
                feedback_entries_ytd=p.feedback_entries_ytd,
                kra_submitted=p.kra_submitted,
                mid_term_completed=p.mid_term_completed,
            )
            for p in performance
        ],
        learning=[
            EmployeeLearningRecord(
                course_name=lr.course_name,
                completed_on=lr.completed_on,
                l1_rating_5=lr.l1_rating_5,
                tni_identified=lr.tni_identified,
                tni_fulfilled=lr.tni_fulfilled,
                source=lr.source,  # type: ignore[arg-type]
            )
            for lr in learning
        ],
        skills=[
            EmployeeSkillRecord(
                skill_type=sk.skill_type,  # type: ignore[arg-type]
                name=sk.name,
                proficiency=sk.proficiency,
                mapped_to_role=sk.mapped_to_role,
                valid_until=sk.valid_until,
            )
            for sk in skills
        ],
        development=[
            EmployeeDevRecord(
                year=d.year,
                dc_type=d.dc_type,
                dc_score=d.dc_score,
                pli_completed=d.pli_completed,
                has_idp=d.has_idp,
                nine_box=d.nine_box,
            )
            for d in development
        ],
        events=[
            EmployeeEventRecord(
                event_type=ev.event_type,  # type: ignore[arg-type]
                effective_date=ev.effective_date,
                reason_code=ev.reason_code,
                from_ic=ev.from_ic,
                to_ic=ev.to_ic,
                from_grade=ev.from_grade,
                to_grade=ev.to_grade,
                regrettable=ev.regrettable,
            )
            for ev in events
        ],
    )


def load_census_from_db(db: Session, company_code: str) -> WorkforceBatch | None:
    """Rebuild a WorkforceBatch from persisted rows (IC knobs reconstructed from aggregate)."""
    rows = list(
        db.scalars(
            select(Employee).where(Employee.company_code == company_code).order_by(Employee.id)
        )
    )
    if not rows:
        return None
    ids = [r.id for r in rows]
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

    def by_emp(items, attr="employee_id"):
        out: dict[int, list] = {}
        for it in items:
            out.setdefault(getattr(it, attr), []).append(it)
        return out

    pmap, lmap, smap, dmap, emap = (
        by_emp(perfs),
        by_emp(learns),
        by_emp(skills),
        by_emp(devs),
        by_emp(events),
    )
    employees = [
        _employee_to_record(
            r,
            pmap.get(r.id, []),
            lmap.get(r.id, []),
            smap.get(r.id, []),
            dmap.get(r.id, []),
            emap.get(r.id, []),
        )
        for r in rows
    ]
    arch = rows[0].archetype
    years = [p.assessment_year for p in perfs] or [2026]
    # Prefer stored MockCompanyData knobs when present.
    mcd = db.scalar(select(MockCompanyData).where(MockCompanyData.company_code == company_code))
    raw = CompanyRaw(**mcd.raw) if mcd else None
    return WorkforceBatch(
        company_code=company_code,
        archetype=arch,  # type: ignore[arg-type]
        as_of=f"{max(years)}-11-01",
        assessment_year=max(years),
        employees=employees,
        ppw_on_time=raw.ppw_on_time if raw else 1,
        training_calendar=raw.training_calendar if raw else 2,
        offers=raw.offers if raw else 0,
        joined=raw.joined if raw else 0,
        avg_days_to_fill=raw.avg_days_to_fill if raw else 60.0,
        positions_closed=raw.positions_closed if raw else 0,
        hire_cohort=raw.hire_cohort if raw else 0,
        retained_12m=raw.retained_12m if raw else 0,
        ahc_eligible=raw.ahc_eligible if raw else 0,
        ahc_completed=raw.ahc_completed if raw else 0,
        unique_logins=raw.unique_logins if raw else 0,
    )


def save_mock_from_batch(db: Session, batch: WorkforceBatch, *, origin: str = "census") -> CompanyRaw:
    """Upsert MockCompanyData from a census batch."""
    raw = to_company_raw(batch)
    existing = db.scalar(
        select(MockCompanyData).where(MockCompanyData.company_code == batch.company_code)
    )
    if existing:
        existing.archetype = raw.archetype
        existing.origin = origin
        existing.model = None
        existing.raw = raw.model_dump()
    else:
        db.add(
            MockCompanyData(
                company_code=batch.company_code,
                archetype=raw.archetype,
                origin=origin,
                model=None,
                raw=raw.model_dump(),
            )
        )
    db.flush()
    return raw


def seed_census(
    db: Session,
    assignments: list[tuple[str, str]],
    *,
    per_ic: int | None = None,
    seed: str | None = None,
    clear: bool = True,
) -> dict:
    """Generate + persist census for each (code, archetype); write MockCompanyData."""
    if clear:
        clear_census(db)
    batches = simulate_group(
        [(c, a) for c, a in assignments],  # type: ignore[arg-type]
        per_ic=per_ic,
        seed=seed,
    )
    counts: dict[str, int] = {}
    raws: dict[str, dict] = {}
    for batch in batches:
        clear_census(db, batch.company_code)
        counts[batch.company_code] = persist_batch(db, batch)
        raw = save_mock_from_batch(db, batch)
        raws[batch.company_code] = raw.model_dump()
    db.commit()
    return {"employees": counts, "companies": list(counts), "raw": raws}


def census_fixture_dict(
    assignments: list[tuple[str, str]],
    *,
    per_ic: int | None = None,
    seed: str | None = None,
) -> dict:
    """JSON-serializable fixture: employees + derived CompanyRaw per IC."""
    from datetime import UTC, datetime

    batches = simulate_group(
        [(c, a) for c, a in assignments],  # type: ignore[arg-type]
        per_ic=per_ic,
        seed=seed,
    )
    companies = {}
    for batch in batches:
        raw = to_company_raw(batch)
        companies[batch.company_code] = {
            "origin": "census",
            "raw": raw.model_dump(),
            "census": batch.model_dump(),
        }
    return {
        "meta": {
            "generated_at": datetime.now(UTC).isoformat(),
            "model": None,
            "count": len(companies),
            "ai_generated": 0,
            "notes": ["employee_census"],
            "seed": seed or "v1",
        },
        "companies": companies,
    }


def ensure_census_profile(db: Session, code: str, archetype: str) -> CompanyRaw:
    """If census missing for code, simulate one IC and persist; return CompanyRaw."""
    batch = load_census_from_db(db, code)
    if batch is None:
        batch = simulate_ic(code, archetype)  # type: ignore[arg-type]
        persist_batch(db, batch)
        raw = save_mock_from_batch(db, batch)
        db.commit()
        return raw
    return to_company_raw(batch)
