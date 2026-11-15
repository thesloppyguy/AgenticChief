"""Editor-only manual KPIs: validation, upsert, change history."""
from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.logger import audit
from app.core.security import Principal
from app.db.models import Company, KpiRecord, ManualInputHistory

MANUAL_KPIS = {"cost_per_hire", "top_talent_review", "idps_top_talent", "gptw_score"}


def added_manual_kpi_keys(db: Session) -> set[str]:
    """Keys of admin-added scored KPIs (always manual-entry)."""
    from app.scorecard_config import service as config_service

    rules, _ = config_service.active(db)
    return {a.key for a in rules.added_kpis}


def all_manual_kpi_keys(db: Session) -> set[str]:
    return MANUAL_KPIS | added_manual_kpi_keys(db)


class ManualInput(BaseModel):
    company_id: int
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    kpi_key: str
    value: float | None = Field(default=None, ge=0)  # idps_top_talent, gptw_score, added KPIs
    recruitment_cost: float | None = Field(default=None, ge=0)  # cost_per_hire
    hires: int | None = Field(default=None, ge=0)
    reviewed: bool | None = None  # top_talent_review
    review_date: date | None = None

    @model_validator(mode="after")
    def _check(self) -> ManualInput:
        k = self.kpi_key
        # Built-in manual KPIs keep field-specific rules; added KPIs are validated in save.
        if k in MANUAL_KPIS:
            if k == "cost_per_hire" and (self.recruitment_cost is None or self.hires is None):
                raise ValueError("recruitment_cost and hires are required")
            if k == "top_talent_review":
                if self.reviewed is None:
                    raise ValueError("reviewed is required")
                if self.reviewed and self.review_date is None:
                    raise ValueError("review_date is required when reviewed is true")
            if k in ("idps_top_talent", "gptw_score") and self.value is None:
                raise ValueError("value is required")
            return self
        # Candidate added / unknown key: require a simple value; membership checked at save.
        if self.value is None:
            raise ValueError("value is required")
        return self


def _snapshot(r: KpiRecord | None) -> dict | None:
    if r is None:
        return None
    return {"achievement": r.achievement, "numerator": r.numerator,
            "denominator": r.denominator, "detail": r.detail}


def save_manual_input(db: Session, who: Principal, inp: ManualInput) -> KpiRecord:
    who.require_company(inp.company_id)
    if db.get(Company, inp.company_id) is None:
        raise HTTPException(404, "Unknown company")
    allowed = all_manual_kpi_keys(db)
    if inp.kpi_key not in allowed:
        raise HTTPException(422, f"{inp.kpi_key} is not a manual KPI")
    rec = db.scalar(select(KpiRecord).where(
        KpiRecord.company_id == inp.company_id, KpiRecord.kpi_key == inp.kpi_key,
        KpiRecord.period == inp.period))
    old = _snapshot(rec)
    ach = num = den = detail = None
    if inp.kpi_key == "cost_per_hire":
        num, den = inp.recruitment_cost, float(inp.hires)  # type: ignore[arg-type]
        ach = num / den if den else None  # no hires -> no value, not zero
    elif inp.kpi_key == "top_talent_review":
        ach = 1.0 if inp.reviewed else 0.0
        detail = {"reviewed": inp.reviewed, "review_date": inp.review_date.isoformat() if inp.review_date else None}
    else:
        ach = inp.value
    if rec is None:
        rec = KpiRecord(company_id=inp.company_id, kpi_key=inp.kpi_key, period=inp.period, source="manual")
        db.add(rec)
    rec.achievement, rec.numerator, rec.denominator, rec.detail, rec.source = ach, num, den, detail, "manual"
    db.add(ManualInputHistory(company_id=inp.company_id, kpi_key=inp.kpi_key, period=inp.period,
                              user_id=who.user_id, old_value=old, new_value=_snapshot(rec)))
    audit(db, who, "manual_input", f"{inp.company_id}:{inp.kpi_key}:{inp.period}")
    db.commit()
    return rec
