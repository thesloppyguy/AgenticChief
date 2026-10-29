"""Create tables, seed 88 ICs, and (optionally) synthetic KPI data for dev/load work.

Usage: uv run python -m scripts.seed [--demo] [--period 2026-10]
"""
import argparse
import random

from sqlalchemy import select

from app.db import models  # noqa: F401
from app.db.migrate import upgrade_head
from app.db.models import Company, KpiRecord
from app.db.session import SessionLocal
from app.kpi_registry.seed import KPIS

N_COMPANIES = 88
MANUAL = {"cost_per_hire", "top_talent_review", "idps_top_talent", "gptw_score"}


def ensure_companies(db) -> None:
    if not db.scalar(select(Company).limit(1)):
        db.add_all(Company(code=f"IC{i:03d}", name=f"Independent Company {i}") for i in range(1, N_COMPANIES + 1))
        db.commit()


def run(demo: bool, period: str) -> None:
    upgrade_head()
    with SessionLocal() as db:
        ensure_companies(db)
        if demo:
            rng = random.Random(42)
            for c in db.scalars(select(Company)):
                for k in KPIS:
                    if rng.random() < 0.1 or db.scalar(select(KpiRecord).where(
                            KpiRecord.company_id == c.id, KpiRecord.kpi_key == k.key, KpiRecord.period == period)):
                        continue
                    ach = k.target * rng.uniform(0.6, 1.15) if k.direction.value == "higher" else k.target * rng.uniform(0.8, 1.6)
                    db.add(KpiRecord(company_id=c.id, kpi_key=k.key, period=period, achievement=ach,
                                     source="manual" if k.key in MANUAL else "demo"))
            db.commit()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--period", default="2026-10")
    a = ap.parse_args()
    run(a.demo, a.period)
