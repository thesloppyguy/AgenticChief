import argparse
import io
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from app.db import models  # noqa: F401
from app.db.session import Base

ROOT = Path(__file__).resolve().parents[1]


def cfg(connection=None, buf=None) -> Config:
    c = Config(str(ROOT / "alembic.ini"), output_buffer=buf)
    c.set_main_option("script_location", str(ROOT / "migrations"))
    if connection is not None:
        c.attributes["connection"] = connection
    return c


def _ignore_fts(obj, name, type_, reflected, compare_to):
    """chunk_fts is an SQLite FTS5 virtual table (plus shadow tables) the ORM deliberately does not model."""
    return not (type_ == "table" and name.startswith("chunk_fts"))


@pytest.fixture()
def engine(tmp_path):
    return create_engine(f"sqlite:///{tmp_path / 'm.db'}")


def test_single_head():
    assert len(ScriptDirectory.from_config(cfg()).get_heads()) == 1


def test_upgrade_matches_models_and_downgrades_cleanly(engine):
    with engine.begin() as conn:
        command.upgrade(cfg(conn), "head")
    tables = {t for t in inspect(engine).get_table_names() if not t.startswith("chunk_fts")} - {"alembic_version"}
    assert tables == set(Base.metadata.tables)
    # The migrations must produce exactly what the models describe: no drift.
    with engine.connect() as conn:
        diff = compare_metadata(
            MigrationContext.configure(conn, opts={"compare_type": True, "include_object": _ignore_fts}), Base.metadata)
    assert diff == [], f"models and migrations have diverged: {diff}"
    with engine.begin() as conn:
        command.downgrade(cfg(conn), "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}  # including the FTS tables


def test_migrations_still_render_for_postgres():
    """SQLite is the database now. This guards the way back: the migrations must stay dialect-neutral.

    Offline mode only needs the dialect, not a server or driver. (SQLite itself cannot do offline
    migrations: its batch mode has to reflect a live database.)
    """
    buf = io.StringIO()
    c = cfg(buf=buf)
    c.cmd_opts = argparse.Namespace(x=["url=postgresql+psycopg://user:pw@host/db"])
    command.upgrade(c, "head", sql=True)
    sql = buf.getvalue()
    assert "CREATE TABLE kpi_record" in sql and "UNIQUE (company_id, kpi_key, period)" in sql
    assert "now()" in sql and "CURRENT_TIMESTAMP" not in sql  # portable server defaults
    assert "INSERT INTO alembic_version" in sql


def test_fresh_database_file_is_created_with_foreign_keys_wal_and_a_busy_timeout(tmp_path):
    from app.db.sqlite import configure_sqlite, ensure_sqlite_dir

    url = f"sqlite:///{tmp_path / 'nested' / 'dir' / 'x.db'}"
    ensure_sqlite_dir(url)                                   # creates the missing folders
    eng = configure_sqlite(create_engine(url))
    with eng.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == 10_000
    assert (tmp_path / "nested" / "dir" / "x.db").exists()


def test_a_stale_schema_is_refused_with_the_fix_in_the_message(tmp_path):
    from app.db.migrate import assert_schema_current

    eng = create_engine(f"sqlite:///{tmp_path / 's.db'}")
    with eng.begin() as conn:
        command.upgrade(cfg(conn), "0003")                   # one revision behind
    with eng.connect() as conn, pytest.raises(RuntimeError, match=r"revision 0003.*alembic upgrade head"):
        assert_schema_current(conn)
    with eng.connect() as conn, pytest.raises(RuntimeError, match="revision none"):
        assert_schema_current(create_engine(f"sqlite:///{tmp_path / 'empty.db'}").connect())
    with eng.begin() as conn:
        command.upgrade(cfg(conn), "head")
    with eng.connect() as conn:
        assert_schema_current(conn)                           # current: no error


def test_the_app_will_not_start_on_a_stale_database(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.db import session

    eng = create_engine(f"sqlite:///{tmp_path / 'stale.db'}")
    with eng.begin() as conn:
        command.upgrade(cfg(conn), "0003")
    monkeypatch.setattr(session, "engine", eng)
    from app.main import app
    with pytest.raises(RuntimeError, match="alembic upgrade head"), TestClient(app):
        pass


def test_the_suite_is_isolated_from_a_developers_env_file_and_key():
    from app.core.config import settings

    assert settings.anthropic_api_key is None and settings.integrations == {} and not settings.mock_sources_enabled
    assert settings.stub_data_enabled is True and settings.mock_source_token is None
