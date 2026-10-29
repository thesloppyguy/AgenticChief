"""SQLite setup shared by the app, Alembic and tests.

SQLite differs from a server database in ways that bite quietly, so they are handled in one place:
- foreign keys are OFF unless each connection turns them on;
- the default rollback journal blocks readers during a write, so use WAL;
- a writer that finds the file locked fails at once unless told to wait (busy_timeout).
It is a single-writer database: fine for one API process (plus its background tasks), not for several
hosts sharing a file.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine, make_url


def ensure_sqlite_dir(url: str) -> None:
    """Create the folder for a file database so a fresh checkout just works."""
    u = make_url(url)
    if u.get_backend_name() == "sqlite" and u.database and u.database != ":memory:":
        Path(u.database).parent.mkdir(parents=True, exist_ok=True)


def configure_sqlite(engine: Engine, foreign_keys: bool = True, busy_timeout_ms: int = 10_000) -> Engine:
    """Apply per-connection pragmas. No-op for other databases.

    Alembic passes foreign_keys=False: its batch mode recreates tables, which FK checks would block.
    """
    if engine.dialect.name != "sqlite":
        return engine

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        cur.execute("PRAGMA journal_mode=WAL")  # a no-op ("memory") for in-memory databases
        cur.execute("PRAGMA synchronous=NORMAL")  # safe with WAL; much faster commits
        cur.execute(f"PRAGMA foreign_keys={'ON' if foreign_keys else 'OFF'}")
        cur.close()

    return engine
