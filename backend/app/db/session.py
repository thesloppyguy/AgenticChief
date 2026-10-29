from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

from .sqlite import configure_sqlite, ensure_sqlite_dir


class Base(DeclarativeBase):
    pass


ensure_sqlite_dir(settings.database_url)
_is_sqlite = settings.database_url.startswith("sqlite")
engine = configure_sqlite(create_engine(
    settings.database_url,
    pool_pre_ping=True,
    # FastAPI serves sync routes and background tasks from a thread pool, so connections cross threads.
    connect_args={"check_same_thread": False} if _is_sqlite else {},
))
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db
