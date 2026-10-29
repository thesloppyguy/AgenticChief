import re
import socket
import threading
import time
from types import SimpleNamespace as NS

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.workflows import get_session_factory
from app.core.config import settings
from app.db import models  # noqa: F401
from app.db.models import Company
from app.db.session import Base, get_db
from app.db.sqlite import configure_sqlite
from app.ingestion.stubgen import CompanyBatch, synthetic_company
from app.knowledge.store import ensure_fts
from app.mock_sources import router as mock_router

TOKEN = "mock-token-for-tests"


class FakeAI:
    """Stands in for Claude: answers each generation request with valid, seeded companies, and counts calls."""

    def __init__(self, fail=False, drop=()):
        self.calls, self.fail, self.drop = [], fail, set(drop)
        self.messages = self
        self.lock = threading.Lock()

    def parse(self, **kw):
        prompt = kw["messages"][0]["content"]
        wanted = re.findall(r"- (IC\d+): archetype=(\w+)", prompt)
        with self.lock:
            self.calls.append([c for c, _ in wanted])
        if self.fail:
            import anthropic

            raise anthropic.APIConnectionError(request=NS())
        comps = [synthetic_company(c, a) for c, a in wanted if c not in self.drop]
        return NS(parsed_output=CompanyBatch(companies=comps), stop_reason="end_turn")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """A file-backed database with 3 companies, the mock-source router on its own app, and a fake model."""
    eng = configure_sqlite(create_engine(f"sqlite:///{tmp_path / 'm.db'}", connect_args={"check_same_thread": False}))
    Base.metadata.create_all(eng)
    ensure_fts(eng)
    factory = sessionmaker(eng, expire_on_commit=False)
    with factory() as db:
        db.add_all(Company(code=f"IC{i:03d}", name=f"Co {i}") for i in range(1, 4))
        db.commit()
    monkeypatch.setattr(settings, "mock_source_token", SecretStr(TOKEN))
    monkeypatch.setattr(settings, "mock_sources_allow_fallback", False)
    monkeypatch.setattr(mock_router, "JOB", {"running": False, "started_at": None, "finished_at": None, "done": 0, "total": 0, "result": None})
    ai = FakeAI()
    app = FastAPI()
    app.include_router(mock_router.router)

    def _db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.dependency_overrides[mock_router.get_ai_client] = lambda: ai
    yield NS(app=app, client=TestClient(app), factory=factory, ai=ai, tmp=tmp_path)
    eng.dispose()


@pytest.fixture()
def server(env):
    """The same app on a real port, so the live adapters can be exercised over real HTTP."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(env.app, host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    env.url = f"http://127.0.0.1:{port}"
    yield env
    srv.should_exit = True
    t.join(timeout=5)
