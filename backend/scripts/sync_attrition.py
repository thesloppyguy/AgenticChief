"""Sync ICHRATTRITION attrition for all (or selected) ICs into local SQLite.

Usage:
  uv run python -m scripts.sync_attrition
  uv run python -m scripts.sync_attrition --ics WETI,RCF --timeout 60 --attempts 1
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

from sqlalchemy import select

from app.attrition.sync import sync_attrition
from app.core.config import settings
from app.db.migrate import upgrade_head
from app.db.models import AttritionSyncRun
from app.db.session import SessionLocal
from app.integrations.ich_attrition import SOURCE_KEY, IchAttritionClient
from app.org.companies import LNT_CODES
from scripts.seed import ensure_companies


def _abandon_stale_runs(db) -> None:
    now = datetime.now(timezone.utc)
    for run in db.scalars(select(AttritionSyncRun).where(AttritionSyncRun.status == "running")):
        run.status = "error"
        run.finished_at = now
        errs = list(run.errors or [])
        errs.append({"error": "abandoned by scripts.sync_attrition (stale running row)"})
        run.errors = errs
    db.commit()


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync attrition data from ICHRATTRITION for all ICs")
    ap.add_argument("--ics", default="", help="Comma-separated IC codes (default: full roster)")
    ap.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Per-request timeout seconds (default 60; avoids multi-minute hangs)",
    )
    ap.add_argument(
        "--attempts",
        type=int,
        default=1,
        help="Attempts per IC (default 1 = fail fast, continue to next IC)",
    )
    args = ap.parse_args()
    ics = [c.strip().upper() for c in args.ics.split(",") if c.strip()] or None
    targets = ics or LNT_CODES

    upgrade_head()
    base = settings.integration(SOURCE_KEY)
    cfg = base.model_copy(update={"timeout_s": float(args.timeout), "enabled": True})
    if not cfg.base_url or not cfg.username or not cfg.password:
        print("ICHRATTRITION credentials/base_url missing in env", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        ensure_companies(db)
        _abandon_stale_runs(db)
        print(
            f"Syncing {len(targets)} ICs | timeout={args.timeout}s | attempts={args.attempts}",
            flush=True,
        )
        print(f"ICs: {', '.join(targets)}", flush=True)
        t0 = time.time()
        with IchAttritionClient(cfg, max_attempts=args.attempts) as client:
            result = sync_attrition(
                db,
                ics=ics,
                triggered_by="cli:sync_attrition",
                client=client,
            )
        print(f"Finished in {round(time.time() - t0, 1)}s", flush=True)

    print(json.dumps(result, default=str, indent=2))
    ok = len(result.get("ics_ok") or [])
    failed = len(result.get("ics_failed") or [])
    print(
        f"Summary: status={result.get('status')} rows={result.get('rows_upserted')} "
        f"ok={ok} failed={failed}",
        flush=True,
    )
    return 0 if result.get("status") in ("ok", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())
