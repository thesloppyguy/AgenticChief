"""One-shot wipe + load of the L&T Group CHRO demo.

Usage:
  uv run python -m scripts.seed_lnt --reset
  uv run python -m scripts.seed_lnt --reset --through 2026-10
"""
from __future__ import annotations

import argparse
import json

from app.db.migrate import upgrade_head
from app.db.session import SessionLocal
from app.fixtures.lnt_loader import load_lnt
from app.services.scorecard import current_period


def main() -> None:
    ap = argparse.ArgumentParser(description="Load L&T Group CHRO fixtures")
    ap.add_argument("--reset", action="store_true", help="wipe existing org/KPI/demo data first")
    ap.add_argument("--through", default=current_period())
    ap.add_argument("--no-ingest", action="store_true", help="skip stub KPI ingestion")
    a = ap.parse_args()

    upgrade_head()
    with SessionLocal() as db:
        summary = load_lnt(
            db=db,
            reset=a.reset,
            ingest=not a.no_ingest,
            through=a.through,
        )
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
