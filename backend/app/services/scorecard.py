"""Glue between stored KPI records and the pure scoring engine. All numbers come from here."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal
from app.db.models import Company, KpiRecord
from app.ingestion import registry
from app.ingestion.manual_seed import SYNTHETIC_SOURCES
from app.scorecard_config import service as config_service
from app.scorecard_config.rules import effective_kpis, to_scoring_config
from app.scoring import group_values, score_group, score_ic, status_for
from app.scoring.models import KpiDef, KpiValue, OverallResult, ScoringConfig


def active_config(db: Session) -> ScoringConfig:
    """Scoring config for this deployment: the admin-approved active rules plus which KPIs have no
    source right now."""
    rules, version = config_service.active(db)
    return to_scoring_config(rules, version, registry.no_source_kpis(db=db))


def active_kpis(db: Session) -> list[KpiDef]:
    """The KPI definitions in force: the defaults with any approved weight/target overrides applied."""
    rules, _ = config_service.active(db)
    return effective_kpis(rules.kpi_overrides)


def _thresholds(cfg: ScoringConfig) -> dict:
    return {"green_min": cfg.green_min, "amber_min": cfg.amber_min}


def current_period() -> str:
    t = date.today()
    return f"{t.year}-{t.month:02d}"


def period_month(period: str) -> int:
    return int(period.split("-")[1])


def visible_companies(db: Session, who: Principal) -> list[Company]:
    q = select(Company).where(Company.active).order_by(Company.code)
    return [c for c in db.scalars(q) if who.can_see(c.id)]


def load_values(db: Session, period: str, company_ids: list[int]) -> dict[int, dict[str, KpiValue]]:
    out: dict[int, dict[str, KpiValue]] = {cid: {} for cid in company_ids}
    if not company_ids:
        return out
    rows = db.scalars(
        select(KpiRecord).where(KpiRecord.period == period, KpiRecord.company_id.in_(company_ids))
    )
    for r in rows:
        out[r.company_id][r.kpi_key] = KpiValue(r.achievement, r.numerator, r.denominator)
    return out


def has_synthetic_data(db: Session, period: str, company_ids: list[int]) -> bool:
    """True if any value in scope came from stub/demo data rather than a real source or a person."""
    if not company_ids:
        return False
    rows = db.execute(
        select(KpiRecord.source, KpiRecord.detail).where(
            KpiRecord.period == period, KpiRecord.company_id.in_(company_ids), KpiRecord.source != "manual")
    )
    return any(src in SYNTHETIC_SOURCES or (d or {}).get("mode") == "stub" or (d or {}).get("origin") in ("ai", "fallback")
               for src, d in rows)


def _overall(r: OverallResult, cfg: ScoringConfig) -> dict:
    return {
        "score": r.score,
        "status": r.status.value if r.status else None,
        "pillar_coverage": r.pillar_coverage,
        "status_withheld": r.status_withheld,
        "pillars": [
            {
                "pillar": p.pillar,
                "score": p.score,
                "status": (status_for(p.score, cfg).value if p.score is not None else None),
                "eligible_weight": p.eligible_weight,
                "kpis": [asdict(k) for k in p.kpis],
            }
            for p in r.pillars
        ],
    }


def build_scorecard(db: Session, who: Principal, period: str, cfg: ScoringConfig | None = None,
                    kpis: list[KpiDef] | None = None) -> dict:
    """`cfg` and `kpis` let a draft rule set be previewed; normally the active rules are used."""
    companies = visible_companies(db, who)
    values = load_values(db, period, [c.id for c in companies])
    month = period_month(period)
    cfg = cfg or active_config(db)
    kpis = kpis or active_kpis(db)
    ics = []
    for c in companies:
        res = score_ic(kpis, values[c.id], month, cfg)
        ics.append({"company_id": c.id, "code": c.code, "name": c.name, **_overall(res, cfg)})
    group = score_group(kpis, values, month, cfg)
    with_data = sum(1 for c in companies if any(v.achievement is not None for v in values[c.id].values()))
    return {
        "period": period,
        "calc_version": cfg.version,
        "thresholds": _thresholds(cfg),
        "scope": "group" if who.company_ids is None else "restricted",
        "synthetic_data": has_synthetic_data(db, period, [c.id for c in companies]),
        "no_source_kpis": sorted(cfg.no_source),
        "group": {**_overall(group, cfg), "companies_in_scope": len(companies), "companies_with_data": with_data},
        "companies": ics,
    }


def build_company_scorecard(db: Session, who: Principal, company_id: int, period: str) -> dict:
    who.require_company(company_id)
    company = db.get(Company, company_id)
    values = load_values(db, period, [company_id])[company_id]
    cfg, kpis = active_config(db), active_kpis(db)
    res = score_ic(kpis, values, period_month(period), cfg)
    return {
        "period": period,
        "company": {"id": company_id, "code": company.code, "name": company.name},
        "values": {k: asdict(v) for k, v in values.items()},
        "thresholds": _thresholds(cfg),
        **_overall(res, cfg),
    }


def build_pillar_drilldown(db: Session, who: Principal, pillar: str, period: str) -> dict:
    """Group -> pillar -> sub-KPI -> IC, with target, formula inputs and coverage."""
    companies = visible_companies(db, who)
    values = load_values(db, period, [c.id for c in companies])
    cfg, kpis = active_config(db), active_kpis(db)
    gv = group_values(kpis, values, cfg)
    month = period_month(period)
    from app.scoring import score_kpi
    from app.scoring.fiscal import target_for

    rows = []
    for k in (k for k in kpis if k.pillar == pillar):
        per_ic = []
        for c in companies:
            v = values[c.id].get(k.key)
            r = score_kpi(k, v, month, cfg)
            per_ic.append({"company_id": c.id, "code": c.code, "achievement": v.achievement if v else None,
                           "score": r.score, "excluded_reason": r.excluded_reason})
        g = score_kpi(k, gv[k.key], month, cfg)
        rows.append({
            "key": k.key, "weight": k.weight, "direction": k.direction.value,
            "target": target_for(k, month, cfg.prorate_cumulative), "group_achievement": gv[k.key].achievement,
            "group_score": g.score, "group_excluded_reason": g.excluded_reason,
            "no_source": k.key in cfg.no_source,
            "coverage": 0 if k.key in cfg.no_source else sum(1 for p in per_ic if p["achievement"] is not None),
            "companies": per_ic,
        })
    return {"period": period, "pillar": pillar, "kpis": rows}
