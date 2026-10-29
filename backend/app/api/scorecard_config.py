from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, get_principal, require_admin
from app.db.models import ScorecardConfigVersion
from app.db.session import get_db
from app.scorecard_config import service
from app.scorecard_config.rules import ScorecardRules, effective_kpis, to_scoring_config
from app.services import scorecard as sc

router = APIRouter(prefix="/scorecard-config")
PERIOD = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


def admin(who: Principal = Depends(require_admin)) -> Principal:
    if who.company_ids is not None:
        raise HTTPException(403, "Group-wide scope required")
    return who


def _out(r: ScorecardConfigVersion) -> dict:
    return {"version": r.version, "status": r.status, "rules": r.rules, "note": r.note, "created_by": r.created_by,
            "created_at": r.created_at, "activated_by": r.activated_by, "activated_at": r.activated_at}


@router.get("")
def overview(db: Session = Depends(get_db), _: Principal = Depends(get_principal)):
    rules, version = service.active(db)
    rows = db.scalars(select(ScorecardConfigVersion).order_by(ScorecardConfigVersion.version.desc())).all()
    return {"active": {"version": version, "rules": rules.model_dump(), "built_in": not any(r.status == "active" for r in rows)},
            "versions": [_out(r) for r in rows]}


class DraftIn(BaseModel):
    rules: dict
    note: str = Field(default="", max_length=300)


@router.post("/drafts", status_code=201)
def create_draft(body: DraftIn, db: Session = Depends(get_db), who: Principal = Depends(admin)):
    """`rules` may be partial: anything omitted keeps the ACTIVE value, so a draft is a small, reviewable change."""
    active_rules, _ = service.active(db)
    try:
        rules = ScorecardRules(**{**active_rules.model_dump(), **body.rules})
    except ValidationError as e:
        raise HTTPException(422, "; ".join(err["msg"].removeprefix("Value error, ") for err in e.errors())) from e
    if not service.diff(active_rules, rules):
        raise HTTPException(422, "That draft changes nothing compared with the active rules")
    return _out(service.create_draft(db, who, rules, body.note))


@router.get("/{version}/preview")
def preview(version: int, period: str | None = PERIOD, db: Session = Depends(get_db), who: Principal = Depends(admin)):
    """What would change if this draft were active: Group score, status mix, and the companies that move."""
    row = db.scalar(select(ScorecardConfigVersion).where(ScorecardConfigVersion.version == version))
    if row is None:
        raise HTTPException(404, "Version not found")
    period = period or sc.current_period()
    now = sc.build_scorecard(db, who, period)
    cfg = to_scoring_config(ScorecardRules(**row.rules), row.version, sc.registry.no_source_kpis(db=db))
    then = sc.build_scorecard(db, who, period, cfg, effective_kpis(ScorecardRules(**row.rules).kpi_overrides))

    def summary(card: dict) -> dict:
        d = Counter(c["status"] or ("withheld" if c["status_withheld"] else "none") for c in card["companies"])
        g = card["group"]
        return {"group_score": g["score"], "group_status": g["status"], "status_withheld": g["status_withheld"],
                "distribution": {k: d.get(k, 0) for k in ("green", "amber", "red", "withheld", "none")}}

    before = {c["code"]: c for c in now["companies"]}
    moved = [{"code": c["code"], "from": before[c["code"]]["status"], "to": c["status"],
              "score_from": before[c["code"]]["score"], "score_to": c["score"]}
             for c in then["companies"] if c["status"] != before[c["code"]]["status"]]
    return {"period": period, "active": summary(now), "draft": summary(then),
            "companies_changing_status": len(moved), "examples": moved[:15]}
