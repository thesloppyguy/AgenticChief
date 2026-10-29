"""Run ingestion for a period. Usage: uv run python -m scripts.ingest --period 2026-10 [--source successfactors]"""
import argparse

from app.alerts import engine as alerts_engine
from app.db import models  # noqa: F401
from app.db.migrate import upgrade_head
from app.db.session import SessionLocal
from app.ingestion import registry
from app.ingestion.runner import ingest

ap = argparse.ArgumentParser()
ap.add_argument("--period", required=True)
ap.add_argument("--source", action="append")
a = ap.parse_args()

upgrade_head()
with SessionLocal() as db:
    summaries = ingest(db, a.period, registry.build_extractors(db=db), a.source)
    alerts_engine.on_ingestion(db, summaries, a.period)
    alerts_engine.evaluate_period(db, a.period)
    for s in summaries:
        print(f"{s.source:15} {s.mode:5} {s.status:8} ok={s.companies_ok} failed={s.companies_failed} "
              f"records={s.records_written}")
