"""Orchestrate ICHRATTRITION fetch → AttritionEmployee upsert for all ICs.

SQLite is single-writer: never hold a write transaction open across CPI HTTP calls.
Commit the run row first, fetch outside the DB, then commit per IC.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.attrition.adapter import upsert_employee_from_attrition
from app.core.config import settings
from app.db.models import AttritionEmployee, AttritionSyncRun, Company
from app.integrations.ich_attrition import (
    SOURCE_KEY,
    IchAttritionClient,
    map_employee_row,
)
from app.org.companies import LNT_BY_CODE, LNT_CODES


def _ensure_company(db: Session, code: str, name: str | None) -> None:
    code = code.upper()
    row = db.scalar(select(Company).where(Company.code == code))
    roster_name = LNT_BY_CODE.get(code, (code, "steady"))[0]
    display = (name or "").strip() or roster_name
    if row is None:
        db.add(Company(code=code, name=display))
        return
    if display and display != code and row.name in (code, "", roster_name if roster_name == code else code):
        row.name = display
    elif display and display != code and row.name == code:
        row.name = display


def _upsert_mapped(db: Session, mapped: dict[str, Any]) -> AttritionEmployee:
    eid = mapped["employee_id"]
    if not eid:
        raise ValueError("employee row missing EMPLOYEEID")
    row = db.scalar(select(AttritionEmployee).where(AttritionEmployee.employee_id == eid))
    if row is None:
        row = AttritionEmployee(employee_id=eid)
        db.add(row)
    for key, value in mapped.items():
        if key == "employee_id":
            continue
        setattr(row, key, value)
    upsert_employee_from_attrition(db, row)
    return row


def _is_locked(exc: BaseException) -> bool:
    return "locked" in str(exc).lower()


def _commit(db: Session) -> None:
    db.commit()


def _persist_ic(db: Session, code: str, raw_employees: list[dict[str, Any]], now: datetime) -> int:
    """Upsert one IC's employees and commit. Retries the whole IC write on lock. Returns rows written."""
    delay = 0.05
    for attempt in range(8):
        try:
            returned_ids: set[str] = set()
            ic_desc = ""
            n = 0
            for raw in raw_employees:
                mapped = map_employee_row(raw, synced_at=now)
                if not mapped["company_code"]:
                    mapped["company_code"] = code
                if mapped["ic_description"]:
                    ic_desc = mapped["ic_description"]
                _ensure_company(db, mapped["company_code"], mapped.get("ic_description"))
                if not mapped["employee_id"]:
                    continue
                returned_ids.add(mapped["employee_id"])
                _upsert_mapped(db, mapped)
                n += 1
            _ensure_company(db, code, ic_desc or None)
            if returned_ids:
                stale = db.scalars(
                    select(AttritionEmployee).where(
                        AttritionEmployee.company_code == code,
                        AttritionEmployee.employee_id.not_in(returned_ids),
                    )
                )
                for s in stale:
                    db.delete(s)
            db.commit()
            return n
        except OperationalError as exc:
            db.rollback()
            if not _is_locked(exc) or attempt == 7:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 1.0)
    return 0


def sync_attrition(
    db: Session,
    *,
    ics: list[str] | None = None,
    triggered_by: str = "",
    client: IchAttritionClient | None = None,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Fetch attrition for each IC and upsert locally. Continues on per-IC failures."""
    cfg = settings.integration(SOURCE_KEY)
    codes = [c.strip().upper() for c in (ics or LNT_CODES) if c and c.strip()]
    if not codes:
        raise ValueError("No IC codes to sync")

    # Drop any ambient read transaction from auth/deps so we don't upgrade a long lock.
    db.rollback()

    run = AttritionSyncRun(
        status="running",
        ics_requested=codes,
        ics_ok=[],
        ics_failed=[],
        rows_upserted=0,
        errors=[],
        triggered_by=triggered_by or "",
    )
    db.add(run)
    _commit(db)
    run_id = run.id

    own_client = client is None
    if client is None:
        if not cfg.enabled:
            run.status = "error"
            run.finished_at = datetime.now(timezone.utc)
            run.errors = [f"{SOURCE_KEY} integration is disabled"]
            run.ics_failed = codes
            _commit(db)
            return _run_dict(run)
        client = IchAttritionClient(cfg, transport=transport)

    ok: list[str] = []
    failed: list[str] = []
    errors: list[dict[str, str]] = []
    rows = 0
    now = datetime.now(timezone.utc)

    try:
        for i, code in enumerate(codes, 1):
            try:
                print(f"[{i}/{len(codes)}] Fetching {code} ...", flush=True)
                # HTTP outside any write transaction
                raw_employees = client.fetch_ic(code)
                n = _persist_ic(db, code, raw_employees, now)
                rows += n
                ok.append(code)
                print(f"[{i}/{len(codes)}] {code}: {n} rows", flush=True)
                _checkpoint_run(db, run_id, ok=ok, failed=failed, rows=rows, errors=errors)
            except Exception as exc:  # noqa: BLE001 — continue other ICs
                db.rollback()
                failed.append(code)
                errors.append({"ic": code, "error": str(exc)[:500]})
                print(f"[{i}/{len(codes)}] {code}: FAILED {exc}", flush=True)
                _checkpoint_run(db, run_id, ok=ok, failed=failed, rows=rows, errors=errors)
    finally:
        if own_client and client is not None:
            client.close()

    run = db.get(AttritionSyncRun, run_id)
    if run is None:
        return {
            "id": run_id,
            "status": "error",
            "started_at": None,
            "finished_at": datetime.now(timezone.utc),
            "ics_requested": codes,
            "ics_ok": ok,
            "ics_failed": failed,
            "rows_upserted": rows,
            "errors": errors + [{"error": "sync run row disappeared"}],
            "triggered_by": triggered_by or "",
        }

    run.ics_ok = ok
    run.ics_failed = failed
    run.rows_upserted = rows
    run.errors = errors
    run.finished_at = datetime.now(timezone.utc)
    if failed and ok:
        run.status = "partial"
    elif failed and not ok:
        run.status = "error"
    else:
        run.status = "ok"
    _commit(db)
    db.refresh(run)
    return _run_dict(run)


def _checkpoint_run(
    db: Session,
    run_id: int,
    *,
    ok: list[str],
    failed: list[str],
    rows: int,
    errors: list[dict[str, str]],
) -> None:
    run = db.get(AttritionSyncRun, run_id)
    if run is None:
        return
    run.ics_ok = list(ok)
    run.ics_failed = list(failed)
    run.rows_upserted = rows
    run.errors = list(errors)
    try:
        db.commit()
    except OperationalError as exc:
        db.rollback()
        if not _is_locked(exc):
            raise
        # Progress checkpoint is best-effort; IC data already committed.


def _run_dict(run: AttritionSyncRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "ics_requested": run.ics_requested or [],
        "ics_ok": run.ics_ok or [],
        "ics_failed": run.ics_failed or [],
        "rows_upserted": run.rows_upserted,
        "errors": run.errors or [],
        "triggered_by": run.triggered_by,
    }


def attrition_status(db: Session) -> dict[str, Any]:
    cfg = settings.integration(SOURCE_KEY)
    last = db.scalar(select(AttritionSyncRun).order_by(AttritionSyncRun.id.desc()).limit(1))
    by_ic = dict(
        db.execute(
            select(AttritionEmployee.company_code, func.count())
            .group_by(AttritionEmployee.company_code)
            .order_by(AttritionEmployee.company_code)
        ).all()
    )
    total = int(db.scalar(select(func.count()).select_from(AttritionEmployee)) or 0)
    return {
        "enabled": cfg.enabled,
        "base_url_configured": bool(cfg.base_url),
        "auth": cfg.auth,
        "total_rows": total,
        "rows_by_ic": by_ic,
        "ic_roster": LNT_CODES,
        "last_sync": _run_dict(last) if last else None,
    }
