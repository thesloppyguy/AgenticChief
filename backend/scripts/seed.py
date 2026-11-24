"""Create tables and seed Independent Companies from the attrition IC roster.

Usage: uv run python -m scripts.seed [--demo] [--period 2026-10] [--reset]
"""
from __future__ import annotations

import argparse
import random

from sqlalchemy import select

from app.db import models  # noqa: F401
from app.db.migrate import upgrade_head
from app.db.models import Company, KpiRecord
from app.db.session import SessionLocal
from app.kpi_registry.seed import KPIS
from app.org.companies import LNT_COMPANIES

MANUAL = {"cost_per_hire", "top_talent_review", "idps_top_talent", "gptw_score"}


def ensure_companies(db, *, reset: bool = False) -> None:
    """Upsert all ICs from the roster. With reset=True, wipe org data first."""
    if reset:
        from app.org.reset import reset_org

        reset_org(db)
    existing = {c.code: c for c in db.scalars(select(Company))}
    for code, name, _ in LNT_COMPANIES:
        row = existing.get(code)
        if row is None:
            db.add(Company(code=code, name=name))
        elif row.name != name and row.name in (code, ""):
            # Refresh placeholder names (e.g. WETI) if still code-only
            row.name = name
    db.commit()


def run(demo: bool, period: str, reset: bool) -> None:
    upgrade_head()
    with SessionLocal() as db:
        ensure_companies(db, reset=reset)
        if demo:
            rng = random.Random(42)
            for c in db.scalars(select(Company)):
                for k in KPIS:
                    if rng.random() < 0.1 or db.scalar(
                        select(KpiRecord).where(
                            KpiRecord.company_id == c.id,
                            KpiRecord.kpi_key == k.key,
                            KpiRecord.period == period,
                        )
                    ):
                        continue
                    ach = (
                        k.target * rng.uniform(0.6, 1.15)
                        if k.direction.value == "higher"
                        else k.target * rng.uniform(0.8, 1.6)
                    )
                    db.add(
                        KpiRecord(
                            company_id=c.id,
                            kpi_key=k.key,
                            period=period,
                            achievement=ach,
                            source="manual" if k.key in MANUAL else "demo",
                        )
                    )
            db.commit()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--period", default="2026-10")
    ap.add_argument("--reset", action="store_true", help="wipe existing companies/KPI data first")
    a = ap.parse_args()
    run(a.demo, a.period, a.reset)
