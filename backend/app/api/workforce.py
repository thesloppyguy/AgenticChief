"""HTTP surface for fixture-backed workforce intelligence."""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.security import Principal, get_principal
from app.workforce import loader

router = APIRouter(prefix="/workforce", tags=["workforce"])


@router.get("/pulse")
def get_pulse(
    company_code: str | None = None,
    _: Principal = Depends(get_principal),
) -> dict[str, Any]:
    code = (company_code or "").strip().upper() or None
    data = loader.pulse(code)
    if not data:
        raise HTTPException(404, "workforce pulse fixture not found")
    return {**data, "artifact": loader.artifact_for("pulse", data)}


@router.get("/skills")
def get_skills(_: Principal = Depends(get_principal)) -> dict[str, Any]:
    data = loader.skills()
    if not data:
        raise HTTPException(404, "workforce skills fixture not found")
    return {**data, "artifact": loader.artifact_for("skills", data)}


@router.get("/succession")
def get_succession(
    company_code: str | None = None,
    _: Principal = Depends(get_principal),
) -> dict[str, Any]:
    code = (company_code or "").strip().upper() or None
    data = loader.succession(code)
    if not data:
        raise HTTPException(404, "workforce succession fixture not found")
    return {**data, "artifact": loader.artifact_for("succession", data)}


@router.get("/actions")
def get_actions(_: Principal = Depends(get_principal)) -> dict[str, Any]:
    data = loader.draft_actions()
    if not data:
        raise HTTPException(404, "workforce actions fixture not found")
    return {**data, "artifact": loader.artifact_for("actions", data)}


@router.get("/export/{kind}")
def export_csv(kind: str, _: Principal = Depends(get_principal)) -> StreamingResponse:
    """CSV export for chat Export CTA / reports."""
    kind = kind.strip().lower().removeprefix("workforce_")
    mapping = {
        "pulse": ("pulse", _rows_pulse),
        "skills": ("skills", _rows_skills),
        "succession": ("succession", _rows_succession),
        "actions": ("actions", _rows_actions),
    }
    if kind not in mapping:
        raise HTTPException(404, f"unknown export kind '{kind}'")
    section, row_fn = mapping[kind]
    data = loader.load_section(section)
    if not data:
        raise HTTPException(404, "fixture empty")
    buf = io.StringIO()
    writer = csv.writer(buf)
    headers, rows = row_fn(data)
    writer.writerow(headers)
    writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="workforce_{kind}.csv"'},
    )


def _rows_pulse(data: dict) -> tuple[list[str], list[list]]:
    headers = ["key", "label", "value", "unit", "delta_pct", "note"]
    rows = [
        [
            c.get("key"),
            c.get("label"),
            c.get("value"),
            c.get("unit"),
            c.get("delta_pct"),
            c.get("note"),
        ]
        for c in data.get("cells") or []
    ]
    return headers, rows


def _rows_skills(data: dict) -> tuple[list[str], list[list]]:
    headers = ["domain", "demand", "supply", "gap", "path"]
    rows = [
        [d.get("label"), d.get("demand"), d.get("supply"), d.get("gap"), d.get("path")]
        for d in data.get("domains") or []
    ]
    return headers, rows


def _rows_succession(data: dict) -> tuple[list[str], list[list]]:
    headers = ["function", "ready_now", "ready_1_2y", "no_successor"]
    rows = [
        [r.get("function"), r.get("ready_now"), r.get("ready_1_2y"), r.get("no_successor")]
        for r in data.get("by_function") or []
    ]
    return headers, rows


def _rows_actions(data: dict) -> tuple[list[str], list[list]]:
    headers = ["key", "title", "severity", "sla", "action"]
    rows = [
        [d.get("key"), d.get("title"), d.get("severity"), d.get("sla"), d.get("action")]
        for d in data.get("drafts") or []
    ]
    return headers, rows
