from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import settings
from app.db import models  # noqa: F401  (registers tables on Base.metadata)
from app.db.session import Base
from app.db.sqlite import configure_sqlite, ensure_sqlite_dir

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    # An explicit -x url=... or a connection injected by tests wins over settings.
    return context.get_x_argument(as_dictionary=True).get("url") or settings.database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _migrate(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    injected = config.attributes.get("connection")  # tests pass an open connection
    if injected is not None:
        _migrate(injected)
        return
    url = _url()
    ensure_sqlite_dir(url)
    # foreign_keys off: SQLite batch migrations recreate tables, which FK enforcement would block.
    engine = configure_sqlite(create_engine(url, poolclass=pool.NullPool), foreign_keys=False)
    with engine.connect() as connection:
        _migrate(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
