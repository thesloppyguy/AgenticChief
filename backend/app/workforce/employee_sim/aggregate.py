"""Derive scorecard CompanyRaw aggregates from a WorkforceBatch census."""
from __future__ import annotations

from app.ingestion.stubgen import CompanyRaw

from .schemas import WorkforceBatch


def to_company_raw(batch: WorkforceBatch) -> CompanyRaw:
    """Map employee-level census (+ IC knobs) into the existing CompanyRaw shape."""
    active = [e for e in batch.employees if e.status == "active"]
    headcount = len(active)
    # Eligible ≈ active non-trainees (performance cycle population).
    eligible = [e for e in active if not e.is_trainee]
    eligible_n = max(1, len(eligible)) if headcount else 0

    year = batch.assessment_year

    def perf(e):
        for p in e.performance:
            if p.assessment_year == year:
                return p
        return e.performance[0] if e.performance else None

    kra_submitted = sum(1 for e in eligible if (p := perf(e)) and p.kra_submitted)
    mid_term = sum(1 for e in eligible if (p := perf(e)) and p.mid_term_completed)
    feedback_vals = [p.feedback_entries_ytd for e in eligible if (p := perf(e))]
    avg_feedback = round(sum(feedback_vals) / len(feedback_vals), 2) if feedback_vals else 0.0

    l1_ratings: list[float] = []
    tni_identified_emps = 0
    for e in eligible:
        saw_tni = False
        for lr in e.learning:
            if lr.tni_identified:
                saw_tni = True
            if lr.l1_rating_5 is not None:
                l1_ratings.append(lr.l1_rating_5)
        if saw_tni:
            tni_identified_emps += 1
    # Align with scorecard: tni_employees = completed TNI / eligible.
    tni_done_employees = sum(
        1
        for e in eligible
        if any((lr.tni_fulfilled or (lr.tni_identified and lr.completed_on)) for lr in e.learning)
    )
    tni_need_events = max(
        tni_identified_emps,
        sum(1 for e in eligible for lr in e.learning if lr.tni_identified),
        1,
    ) if eligible else 0
    tni_fulfilled_events = min(
        tni_need_events,
        sum(1 for e in eligible for lr in e.learning if lr.tni_fulfilled),
    )

    skills_mapped = sum(
        1 for e in active if any(s.mapped_to_role and s.skill_type == "role_skill" for s in e.skills)
    )

    pli_pool = [
        e
        for e in active
        if e.grade_cadre in ("M3C", "M4A")
        or any(d.dc_type == "PLI" for d in e.development)
    ]
    pli_total = max(1, len(pli_pool)) if active else 0
    pli_completed = sum(
        1
        for e in pli_pool
        if any(d.year == year and d.pli_completed for d in e.development)
    )

    idp_targets = [
        e
        for e in active
        if e.top_talent or e.cpr_band >= 7 or e.grade_cadre in ("M3C", "M4A")
    ]
    idp_target_n = max(1, len(idp_targets)) if active else 0
    idps_created = sum(
        1
        for e in idp_targets
        if any(d.year == year and d.has_idp for d in e.development)
    )

    # Retention: retentions ≈ active headcount still retained YTD (simplified).
    # Leavers in the window reduce retention numerator relative to avg headcount.
    leavers = [e for e in batch.employees if e.status == "separated"]
    avg_headcount = max(1, headcount + len(leavers) // 2) if (headcount or leavers) else 1
    retentions = headcount  # still employed at as_of

    cpr7 = [e for e in active if e.cpr_band >= 7 or e.top_talent]
    cpr7_hc = max(1, len(cpr7)) if active else 0
    # Count unique regrettable leavers, not double resign+separate.
    regrettable_ps = {
        e.ps_number
        for e in leavers
        if any(ev.regrettable for ev in e.events)
    }
    regrettable_exits = min(cpr7_hc, len(regrettable_ps))

    trainees_onboarded = sum(1 for e in batch.employees if e.is_trainee or e.employee_group == "Trainee")
    # Include separated trainees in onboarded; remaining = active trainees with tenure < 36m
    # plus a synthetic "3-year cohort" remaining count.
    trainees_remaining = sum(
        1
        for e in active
        if e.is_trainee and e.time_in_company_months < 36
    )
    # Ensure onboarded >= remaining
    trainees_onboarded = max(trainees_onboarded, trainees_remaining)

    avg_rating = round(sum(l1_ratings) / len(l1_ratings), 2) if l1_ratings else round(3.0 + 1.2 * _q(batch), 2)
    avg_rating = min(5.0, max(1.0, avg_rating))

    return CompanyRaw(
        company_code=batch.company_code,
        archetype=batch.archetype,
        headcount=max(1, headcount),
        eligible_employees=max(1, eligible_n) if headcount else 1,
        offers=batch.offers,
        joined=batch.joined,
        avg_days_to_fill=batch.avg_days_to_fill,
        positions_closed=batch.positions_closed,
        hire_cohort=batch.hire_cohort,
        retained_12m=batch.retained_12m,
        ppw_on_time=batch.ppw_on_time,
        kra_submitted=kra_submitted,
        mid_term_completed=mid_term,
        avg_feedback_entries=avg_feedback,
        tni_completed=tni_done_employees,
        training_calendar=batch.training_calendar,
        tni_identified=tni_need_events,
        tni_fulfilled=tni_fulfilled_events,
        avg_rating_5=avg_rating,
        skills_mapped=skills_mapped,
        pli_total=pli_total or 1,
        pli_completed=min(pli_completed, pli_total or 1),
        idp_target_employees=idp_target_n or 1,
        idps_created=min(idps_created, idp_target_n or 1),
        ahc_eligible=batch.ahc_eligible,
        ahc_completed=batch.ahc_completed,
        unique_logins=batch.unique_logins,
        retentions=retentions,
        avg_headcount=avg_headcount,
        cpr7_headcount=cpr7_hc or 1,
        regrettable_exits=regrettable_exits,
        trainees_onboarded=trainees_onboarded,
        trainees_remaining=trainees_remaining,
    )


def _q(batch: WorkforceBatch) -> float:
    return {"strong": 0.92, "steady": 0.82, "struggling": 0.64, "early_stage": 0.55}.get(
        batch.archetype, 0.8
    )
