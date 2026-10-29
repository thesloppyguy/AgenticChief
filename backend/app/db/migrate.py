from pathlib import Path

from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[2]


def alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))  # independent of the CWD
    return cfg


def upgrade_head() -> None:
    command.upgrade(alembic_config(), "head")


def assert_schema_current(connection) -> None:
    """Fail fast with the fix in the message, instead of opaque 500s from missing tables later."""
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    current = MigrationContext.configure(connection).get_current_revision()
    if current != head:
        raise RuntimeError(
            f"Database schema is at revision {current or 'none'} but this code needs {head}. "
            "Run: uv run alembic upgrade head")
