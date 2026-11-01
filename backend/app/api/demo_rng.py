"""Deterministic RNG / demo endpoints for L&T CHRO monitoring and stub HRIS shapes.

Gated by STUB_DATA_ENABLED (or DEMO_RNG_ENABLED) and admin auth.
"""
from __future__ import annotations

import hashlib
import random
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.alerts import watches as watches_mod
from app.approvals import service as approvals
from app.core.config import settings
from app.core.security import Principal, require_admin
from app.db.models import Company, KpiRecord, UserMemory, Watch
from app.db.session import get_db
from app.ingestion.stubgen import to_kpi_raw
from app.ingestion.stubgen import synthetic_company
from app.kpi_registry.seed import KPIS
from app.org.companies import LNT_BY_CODE, LNT_CODES
from app.services.scorecard import build_scorecard, current_period

router = APIRouter(prefix="/demo/rng", tags=["demo-rng"])

SourceName = Literal["successfactors", "peoplestrong", "myhealth", "hi5plus"]


def _enabled() -> None:
    if not (settings.stub_data_enabled or settings.demo_rng_enabled):
        raise HTTPException(403, "demo RNG disabled (set STUB_DATA_ENABLED or DEMO_RNG_ENABLED)")


def _rng(*parts: str) -> random.Random:
    return random.Random(int.from_bytes(hashlib.sha256("|".join(parts).encode()).digest()[:8], "big"))


class ScorecardIn(BaseModel):
    period: str | None = None
    seed: int = 42
    company_codes: list[str] | None = None


@router.post("/scorecard")
def rng_scorecard(
    body: ScorecardIn,
    db: Session = Depends(get_db),
    who: Principal = Depends(require_admin),
):
    _enabled()
    period = body.period or current_period()
    codes = [c.upper() for c in (body.company_codes or LNT_CODES)]
    written = 0
    for code in codes:
        company = db.scalar(select(Company).where(Company.code == code))
        if company is None:
            continue
        arch = LNT_BY_CODE.get(code, ("", "steady"))[1]
        raw = synthetic_company(f"{code}:{body.seed}", arch)
        # Re-key company_code for clarity in detail
        detail = raw.model_dump()
        detail["company_code"] = code
        detail["rng_seed"] = body.seed
        db.execute(
            delete(KpiRecord).where(KpiRecord.company_id == company.id, KpiRecord.period == period)
        )
        r = _rng("scorecard", code, period, str(body.seed))
        for k in KPIS:
            # Map from synthetic quality with light jitter
            base = k.target * (0.55 + 0.45 * {"strong": 0.95, "steady": 0.85, "struggling": 0.65, "early_stage": 0.55}[arch])
            if k.direction.value == "higher":
                ach = base * r.uniform(0.92, 1.08)
            else:
                ach = (k.target ** 2 / max(base, 0.01)) * r.uniform(0.92, 1.08)
            db.add(
                KpiRecord(
                    company_id=company.id,
                    kpi_key=k.key,
                    period=period,
                    achievement=round(ach, 4),
                    source="demo_rng",
                    detail={"seed": body.seed, "archetype": arch},
                )
            )
            written += 1
    db.commit()
    card = build_scorecard(db, who, period)
    return {
        "period": period,
        "seed": body.seed,
        "records_written": written,
        "group_score": card["group"]["score"],
        "group_status": card["group"]["status"],
        "companies": [
            {"code": c["code"], "score": c["score"], "status": c["status"]} for c in card["companies"]
        ],
    }


class JitterIn(BaseModel):
    period: str | None = None
    seed: int = 7


@router.post("/period-jitter")
def period_jitter(body: JitterIn, db: Session = Depends(get_db), who: Principal = Depends(require_admin)):
    _enabled()
    period = body.period or current_period()
    r = _rng("jitter", period, str(body.seed))
    n = 0
    for row in db.scalars(select(KpiRecord).where(KpiRecord.period == period)):
        if row.achievement is None:
            continue
        row.achievement = round(row.achievement * r.uniform(0.97, 1.03), 4)
        row.source = "demo_rng_jitter"
        n += 1
    db.commit()
    return {"period": period, "seed": body.seed, "jittered": n}


@router.get("/monitoring")
def monitoring(
    period: str | None = None,
    db: Session = Depends(get_db),
    who: Principal = Depends(require_admin),
):
    _enabled()
    period = period or current_period()
    card = build_scorecard(db, who, period)
    from sqlalchemy import func

    from app.db.models import ApprovalRequest, Goal, OpenLoop

    pending_n = db.scalar(
        select(func.count()).select_from(ApprovalRequest).where(ApprovalRequest.status == "pending")
    ) or 0
    open_loops = db.scalar(
        select(func.count()).select_from(OpenLoop).where(OpenLoop.status == "open")
    ) or 0
    at_risk_goals = db.scalar(
        select(func.count()).select_from(Goal).where(Goal.status.in_(("at_risk", "off_track")))
    ) or 0
    watches = list(db.scalars(select(Watch).where(Watch.enabled.is_(True))))
    firings = []
    for w in watches:
        try:
            seen = watches_mod.observe(db, w, period)
            if seen["would_fire"]:
                firings.append({"watch_id": w.id, "name": w.name, "observed": seen["observed"]})
        except Exception:
            continue
    return {
        "period": period,
        "group": {"score": card["group"]["score"], "status": card["group"]["status"]},
        "companies": [
            {
                "code": c["code"],
                "name": c.get("name"),
                "score": c["score"],
                "status": c["status"],
                "pillars": [
                    {"pillar": p["pillar"], "score": p["score"], "status": p["status"]}
                    for p in c.get("pillars", [])
                ],
            }
            for c in card["companies"]
        ],
        "pending_approvals": pending_n,
        "open_loops": open_loops,
        "at_risk_goals": at_risk_goals,
        "watch_firings": firings,
        "generated_at": datetime.now(UTC).isoformat(),
    }


class FireIn(BaseModel):
    period: str | None = None
    force: bool = False


@router.post("/watches/fire")
def fire_watches(body: FireIn, db: Session = Depends(get_db), who: Principal = Depends(require_admin)):
    _enabled()
    period = body.period or current_period()
    raised = []
    for w in db.scalars(select(Watch).where(Watch.enabled.is_(True))):
        try:
            if body.force or watches_mod.observe(db, w, period)["would_fire"]:
                alert = watches_mod.evaluate(db, w, period)
                if alert is None and body.force:
                    # Force a synthetic breach observation into an alert via evaluate after tweaking —
                    # fall back to creating via engine if condition doesn't fire.
                    from app.alerts import engine as alerts_engine

                    code = (
                        db.scalar(select(Company.code).where(Company.id == w.company_id))
                        if w.company_id
                        else None
                    )
                    alert = alerts_engine._raise(
                        db,
                        kind="watch_fired",
                        severity="medium",
                        company_id=w.company_id,
                        entity=code or "group",
                        period=period,
                        title=f"Forced watch '{w.name}' ({period})"[:200],
                        detail={"watch_id": w.id, "forced": True},
                        dedupe_key=f"watch-force:{w.id}:{period}:{datetime.now(UTC).timestamp()}",
                        audience_user_id=w.user_id,
                    )
                if alert is not None:
                    raised.append({"alert_id": alert.id, "watch_id": w.id, "title": alert.title})
        except Exception as e:
            raised.append({"watch_id": w.id, "error": type(e).__name__})
    db.commit()
    return {"period": period, "raised": raised}


class MemoryIn(BaseModel):
    n: int = Field(default=5, ge=1, le=50)
    seed: int = 1
    user_id: str | None = None


@router.post("/memory")
def rng_memory(body: MemoryIn, db: Session = Depends(get_db), who: Principal = Depends(require_admin)):
    _enabled()
    uid = body.user_id or who.user_id
    r = _rng("memory", uid, str(body.seed))
    kinds = ["decision", "initiative", "advice"]
    domains = ["hr", "talent", "retention", "performance"]
    templates = [
        "Reviewed {ic} {pillar} pillar — status warrants follow-up this week.",
        "Initiative: close IDP gaps at {ic} before top-talent review window.",
        "Advice: send KPI reminder for {ic} on {pillar} before monthly publish.",
        "Decision: keep Talent Management weight at 20%; fix process compliance at {ic}.",
        "Open loop: confirm training calendar H2 milestone for {ic}.",
    ]
    added = []
    for i in range(body.n):
        ic = r.choice(LNT_CODES)
        pillar = r.choice(
            [
                "Talent Acquisition",
                "Performance Management",
                "L&D",
                "Retention",
                "Engagement",
            ]
        )
        summary = r.choice(templates).format(ic=ic, pillar=pillar)[:400]
        m = UserMemory(
            user_id=uid,
            kind=r.choice(kinds),
            domain=r.choice(domains),
            summary=summary,
            pinned=r.random() < 0.2,
        )
        db.add(m)
        added.append(summary)
    db.commit()
    return {"added": len(added), "summaries": added}


class ApprovalsIn(BaseModel):
    n: int = Field(default=3, ge=1, le=10)
    period: str | None = None
    seed: int = 3


@router.post("/approvals")
def rng_approvals(
    body: ApprovalsIn, db: Session = Depends(get_db), who: Principal = Depends(require_admin)
):
    _enabled()
    period = body.period or current_period()
    from app.core.security import Role

    r = _rng("approvals", period, str(body.seed))
    requester = Principal("chro-ops", Role.EDITOR, None)
    created = []
    for i in range(body.n):
        codes = r.sample(LNT_CODES, k=min(2, len(LNT_CODES)))
        try:
            with db.begin_nested():
                res = approvals.submit(
                    db,
                    requester,
                    "send_kpi_reminder",
                    {
                        "company_codes": codes,
                        "period": period,
                        "kpi_key": r.choice([None, "overall_retention", "kra_submission", "gptw_score"]),
                        "note": f"RNG demo reminder #{i + 1} (seed={body.seed})",
                    },
                    via="api",
                    context={"reason": "demo_rng"},
                )
            created.append({"verdict": res.verdict, "approval_id": res.approval.id if res.approval else None})
        except Exception as e:
            created.append({"error": type(e).__name__})
    db.commit()
    return {"period": period, "created": created}


@router.get("/sources/{source}")
def rng_source(
    source: SourceName,
    company_code: str = "LTTS",
    period: str | None = None,
    seed: int = 0,
    _: Principal = Depends(require_admin),
):
    """Deterministic HRIS-shaped payload for mock mapping tests (no AI)."""
    _enabled()
    period = period or current_period()
    code = company_code.strip().upper()
    arch = LNT_BY_CODE.get(code, ("", "steady"))[1]
    raw = synthetic_company(f"{code}:{seed}:{source}", arch)
    kpi = to_kpi_raw(raw)
    # Shape loosely like each system
    if source == "successfactors":
        rows = [
            {"companyCode": code, "period": period, "kpi": k, "Value": v}
            for k, v in list(kpi.items())[:8]
        ]
        return {"d": {"results": rows}, "meta": {"seed": seed, "archetype": arch}}
    if source == "peoplestrong":
        return {
            "company": code,
            "period": period,
            "recruitment": kpi.get("offer_to_joining"),
            "time_to_fill": kpi.get("time_to_fill"),
            "meta": {"seed": seed, "archetype": arch},
        }
    if source == "myhealth":
        return {
            "orgCode": code,
            "month": period,
            "ahc": kpi.get("ahc_completion"),
            "meta": {"seed": seed, "archetype": arch},
        }
    return {
        "entity": code,
        "ym": period,
        "engagement": kpi.get("platform_adoption"),
        "meta": {"seed": seed, "archetype": arch},
    }
