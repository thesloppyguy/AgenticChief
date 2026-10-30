from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts.engine import safe_evaluate
from app.audit.logger import audit
from app.core.security import Principal, get_principal, require_admin, require_editor
from app.db.models import AuditEvent, ManualInputHistory, ReportSnapshot
from app.db.session import get_db
from app.kpi_registry.seed import KPIS, PILLAR_WEIGHTS
from app.reports import export
from app.reports.integrity import canonical_hash
from app.reports.markdown import render_markdown
from app.reports.pdf import render_pdf
from app.services import scorecard as sc
from app.services import timeline
from app.services.manual_inputs import MANUAL_KPIS, ManualInput, save_manual_input

router = APIRouter()
PERIOD = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/companies")
def companies(db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    return [{"id": c.id, "code": c.code, "name": c.name} for c in sc.visible_companies(db, who)]


@router.get("/kpis")
def kpi_definitions(db: Session = Depends(get_db), _: Principal = Depends(get_principal)):
    cfg = sc.active_config(db)
    return {
        "calc_version": cfg.version,
        "pillar_weights": cfg.pillar_weights,
        "thresholds": {"green_min": cfg.green_min, "amber_min": cfg.amber_min},
        "kpis": [{**asdict(k), "direction": k.direction.value, "manual": k.key in MANUAL_KPIS,
                  "default_weight": d.weight, "default_target": d.target}  # the defaults let an editor see what was changed
                 for k, d in zip(sc.active_kpis(db), KPIS, strict=True)],
    }


@router.get("/scorecard")
def scorecard(period: str | None = PERIOD, db: Session = Depends(get_db),
              who: Principal = Depends(get_principal)):
    return sc.build_scorecard(db, who, period or sc.current_period())


@router.get("/reports/export/scorecard.{fmt}")
def export_scorecard(fmt: str, period: str | None = PERIOD, db: Session = Depends(get_db),
                     who: Principal = Depends(get_principal)):
    """The scorecard as Excel or CSV, for exactly the companies you are allowed to see."""
    if fmt not in ("xlsx", "csv"):
        raise HTTPException(404, "Formats: xlsx, csv")
    period = period or sc.current_period()
    data = export.collect(db, who, period)
    audit(db, who, "scorecard_exported", f"{period}.{fmt}")
    db.commit()
    name = f"group-hr-scorecard-{period}.{fmt}"
    headers = {"Content-Disposition": f'attachment; filename="{name}"'}
    if fmt == "csv":
        return Response(export.to_csv(data), media_type="text/csv; charset=utf-8", headers=headers)
    return Response(export.to_xlsx(data, who, period),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)


@router.get("/scorecard/companies/{company_id}")
def company_scorecard(company_id: int, period: str | None = PERIOD, db: Session = Depends(get_db),
                      who: Principal = Depends(get_principal)):
    if db.get(sc.Company, company_id) is None:
        raise HTTPException(404, "Unknown company")
    return sc.build_company_scorecard(db, who, company_id, period or sc.current_period())


@router.get("/scorecard/pillars/{pillar}")
def pillar_drilldown(pillar: str, period: str | None = PERIOD, db: Session = Depends(get_db),
                     who: Principal = Depends(get_principal)):
    if pillar not in PILLAR_WEIGHTS:
        raise HTTPException(404, "Unknown pillar")
    return sc.build_pillar_drilldown(db, who, pillar, period or sc.current_period())


@router.post("/inputs", status_code=201)
def submit_input(inp: ManualInput, db: Session = Depends(get_db), who: Principal = Depends(require_editor)):
    rec = save_manual_input(db, who, inp)
    safe_evaluate(db, inp.period, [inp.company_id])
    return {"id": rec.id, "achievement": rec.achievement}


@router.get("/inputs/history")
def input_history(company_id: int, db: Session = Depends(get_db), who: Principal = Depends(require_editor)):
    who.require_company(company_id)
    rows = db.scalars(select(ManualInputHistory).where(ManualInputHistory.company_id == company_id)
                      .order_by(ManualInputHistory.id.desc()).limit(200))
    return [{"kpi_key": r.kpi_key, "period": r.period, "user": r.user_id, "at": r.created_at,
             "old": r.old_value, "new": r.new_value} for r in rows]


@router.post("/reports/snapshots", status_code=201)
def create_snapshot(period: str | None = PERIOD, db: Session = Depends(get_db),
                    who: Principal = Depends(require_admin)):
    if who.company_ids is not None:
        raise HTTPException(403, "Group-wide scope required")
    period = period or sc.current_period()
    payload = sc.build_scorecard(db, who, period)
    snap = ReportSnapshot(kind="scorecard", period=period, calc_version=sc.active_config(db).version, payload=payload,
                          content_hash=canonical_hash(payload), created_by=who.user_id)
    db.add(snap)
    audit(db, who, "snapshot_created", period)
    db.commit()
    return {"id": snap.id, "period": period}


@router.get("/reports/snapshots")
def list_snapshots(db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    if who.company_ids is not None:
        raise HTTPException(403, "Group-wide scope required")
    rows = db.scalars(select(ReportSnapshot).order_by(ReportSnapshot.id.desc()).limit(100))
    return [{"id": r.id, "kind": r.kind, "period": r.period, "calc_version": r.calc_version,
             "content_hash": r.content_hash, "run_id": r.run_id, "created_by": r.created_by,
             "created_at": r.created_at} for r in rows]


@router.get("/reports/snapshots/{snap_id}")
def get_snapshot(snap_id: int, db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    if who.company_ids is not None:
        raise HTTPException(403, "Group-wide scope required")
    snap = db.get(ReportSnapshot, snap_id)
    if snap is None:
        raise HTTPException(404, "Not found")
    return {"id": snap.id, "kind": snap.kind, "period": snap.period, "calc_version": snap.calc_version,
            "content_hash": snap.content_hash, "run_id": snap.run_id, "created_by": snap.created_by,
            "created_at": snap.created_at,
            # Recomputed from the stored payload: False means the stored report no longer matches its hash.
            "verified": None if snap.content_hash is None else canonical_hash(snap.payload) == snap.content_hash,
            "payload": snap.payload}


@router.get("/reports/snapshots/{snap_id}/pdf")
def snapshot_pdf(snap_id: int, db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    if who.company_ids is not None:
        raise HTTPException(403, "Group-wide scope required")
    snap = db.get(ReportSnapshot, snap_id)
    if snap is None or snap.kind != "monthly_review":
        raise HTTPException(404, "Not found")
    pdf = render_pdf(snap.payload, {"hash": snap.content_hash or "unhashed", "by": snap.created_by, "at": snap.created_at.isoformat(),
                                    "snapshot_id": snap.id})
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="monthly-review-{snap.period}-published.pdf"'})


@router.get("/reports/snapshots/{snap_id}/markdown", response_class=PlainTextResponse)
def snapshot_markdown(snap_id: int, db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    if who.company_ids is not None:
        raise HTTPException(403, "Group-wide scope required")
    snap = db.get(ReportSnapshot, snap_id)
    if snap is None or snap.kind != "monthly_review":
        raise HTTPException(404, "Not found")
    return render_markdown(snap.payload)


@router.get("/audit")
def audit_log(limit: int = 100, db: Session = Depends(get_db), _: Principal = Depends(require_admin)):
    rows = db.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(min(limit, 500)))
    return [{"at": r.at, "actor": r.actor, "role": r.role, "action": r.action, "target": r.target} for r in rows]


@router.get("/timeline")
def activity_timeline(limit: int = 50, cursor: str | None = None, kinds: str | None = None,
                      company_id: int | None = None, db: Session = Depends(get_db),
                      who: Principal = Depends(get_principal)):
    """What the platform did, newest first. Unlike /audit (the raw compliance log, admins only) this
    is a product surface: each source is scoped to the caller, so it works for a scoped editor too."""
    if company_id is not None:
        who.require_company(company_id)
    return timeline.fetch(db, who, limit=limit, cursor=cursor,
                          kinds=[k for k in kinds.split(",") if k] if kinds else None,
                          company_id=company_id)
