import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.workflows import get_async_llm, get_llm, get_session_factory
from app.core.security import Role, make_token
from app.db import models  # noqa: F401
from app.db.models import Company
from app.db.session import Base, get_db
from app.db.sqlite import configure_sqlite
from app.knowledge.store import ensure_fts
from app.main import app


@pytest.fixture()
def client():
    eng = configure_sqlite(create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}))
    Base.metadata.create_all(eng)
    ensure_fts(eng)  # the full-text table comes from a migration in real databases
    S = sessionmaker(eng, expire_on_commit=False)
    with S() as db:
        db.add_all(Company(code=f"IC{i}", name=f"Co {i}") for i in range(1, 4))
        db.commit()

    def _db():
        with S() as db:
            yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_session_factory] = lambda: S  # background workflows use the test database
    app.dependency_overrides[get_llm] = lambda: None  # never call a real model from tests
    app.dependency_overrides[get_async_llm] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def auth(role: Role, companies=None):
    return {"Authorization": f"Bearer {make_token('u1', role, companies)}"}
