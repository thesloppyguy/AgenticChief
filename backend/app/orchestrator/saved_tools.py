"""Versioned custom/saved tools (OpenExecutive pattern, SQLite-backed)."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.core.config import DATA_DIR

DB_PATH = DATA_DIR / "saved_tools.db"


class SavedTool(BaseModel):
    name: str
    description: str
    enabled: bool
    kind: str
    active_version: int
    workflow_approved_version: int | None = None
    updated_at: str


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def initialize() -> None:
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS saved_tools (
                name TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                kind TEXT NOT NULL DEFAULT 'script',
                active_version INTEGER NOT NULL DEFAULT 1,
                workflow_approved_version INTEGER,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS saved_tool_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                version INTEGER NOT NULL,
                code TEXT NOT NULL,
                description TEXT NOT NULL,
                called_tools TEXT,
                origin TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(name, version)
            );
            CREATE TABLE IF NOT EXISTS saved_tool_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                version INTEGER NOT NULL,
                result TEXT,
                call_count INTEGER DEFAULT 0,
                duration_ms INTEGER,
                origin TEXT,
                created_at TEXT NOT NULL
            );
        """)
        conn.commit()


def list_tools() -> list[SavedTool]:
    initialize()
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM saved_tools ORDER BY name").fetchall()
    return [
        SavedTool(
            name=r["name"],
            description=r["description"],
            enabled=bool(r["enabled"]),
            kind=r["kind"],
            active_version=r["active_version"],
            workflow_approved_version=r["workflow_approved_version"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


def get_tool(name: str) -> dict[str, Any] | None:
    initialize()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM saved_tools WHERE name = ?", (name,)).fetchone()
        if row is None:
            return None
        versions = conn.execute(
            "SELECT version, description, code, called_tools, origin, created_at "
            "FROM saved_tool_versions WHERE name = ? ORDER BY version DESC",
            (name,),
        ).fetchall()
        runs = conn.execute(
            "SELECT id, version, result, call_count, duration_ms, origin, created_at "
            "FROM saved_tool_runs WHERE name = ? ORDER BY id DESC LIMIT 20",
            (name,),
        ).fetchall()
    return {
        "name": row["name"],
        "description": row["description"],
        "enabled": bool(row["enabled"]),
        "kind": row["kind"],
        "active_version": row["active_version"],
        "workflow_approved_version": row["workflow_approved_version"],
        "updated_at": row["updated_at"],
        "versions": [dict(v) for v in versions],
        "runs": [dict(r) for r in runs],
    }


def set_enabled(name: str, enabled: bool) -> bool:
    initialize()
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE saved_tools SET enabled = ?, updated_at = ? WHERE name = ?",
            (int(enabled), datetime.now(UTC).isoformat(), name),
        )
        conn.commit()
        return cur.rowcount > 0


def rollback(name: str, version: int) -> bool:
    initialize()
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM saved_tool_versions WHERE name = ? AND version = ?",
            (name, version),
        ).fetchone()
        if row is None:
            return False
        conn.execute(
            "UPDATE saved_tools SET active_version = ?, updated_at = ? WHERE name = ?",
            (version, datetime.now(UTC).isoformat(), name),
        )
        conn.commit()
        return True


def approve_for_workflows(name: str, version: int | None = None) -> bool:
    initialize()
    with _conn() as conn:
        tool = conn.execute("SELECT * FROM saved_tools WHERE name = ?", (name,)).fetchone()
        if tool is None:
            return False
        ver = version if version is not None else tool["active_version"]
        conn.execute(
            "UPDATE saved_tools SET workflow_approved_version = ?, updated_at = ? WHERE name = ?",
            (ver, datetime.now(UTC).isoformat(), name),
        )
        conn.commit()
        return True


def get_active_code(name: str, *, workflow: bool = False) -> dict[str, Any] | None:
    """Return {name, description, code, version, kind, enabled} for the active (or workflow-approved) version."""
    initialize()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM saved_tools WHERE name = ?", (name,)).fetchone()
        if row is None:
            return None
        version = row["active_version"]
        if workflow:
            if row["workflow_approved_version"] is None:
                return None
            version = row["workflow_approved_version"]
        ver = conn.execute(
            "SELECT code, description FROM saved_tool_versions WHERE name = ? AND version = ?",
            (name, version),
        ).fetchone()
        if ver is None:
            return None
        return {
            "name": row["name"],
            "description": row["description"],
            "code": ver["code"],
            "version": version,
            "kind": row["kind"],
            "enabled": bool(row["enabled"]),
        }


def record_run(
    name: str,
    version: int,
    *,
    result: str,
    call_count: int = 0,
    duration_ms: int | None = None,
    origin: str = "chat",
) -> None:
    initialize()
    with _conn() as conn:
        conn.execute(
            "INSERT INTO saved_tool_runs "
            "(name, version, result, call_count, duration_ms, origin, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                name,
                version,
                result[:8000],
                call_count,
                duration_ms,
                origin,
                datetime.now(UTC).isoformat(),
            ),
        )
        conn.commit()


def upsert_version(
    name: str,
    *,
    description: str,
    code: str,
    called_tools: list[str] | None = None,
    origin: str = "api",
    kind: str = "script",
) -> int:
    initialize()
    now = datetime.now(UTC).isoformat()
    with _conn() as conn:
        existing = conn.execute("SELECT * FROM saved_tools WHERE name = ?", (name,)).fetchone()
        if existing is None:
            version = 1
            conn.execute(
                "INSERT INTO saved_tools "
                "(name, description, enabled, kind, active_version, updated_at) "
                "VALUES (?, ?, 1, ?, ?, ?)",
                (name, description, kind, version, now),
            )
        else:
            version = int(existing["active_version"]) + 1
            conn.execute(
                "UPDATE saved_tools SET description = ?, active_version = ?, updated_at = ? "
                "WHERE name = ?",
                (description, version, now, name),
            )
        conn.execute(
            "INSERT INTO saved_tool_versions "
            "(name, version, code, description, called_tools, origin, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                name,
                version,
                code,
                description,
                json.dumps(called_tools or []),
                origin,
                now,
            ),
        )
        conn.commit()
        return version
