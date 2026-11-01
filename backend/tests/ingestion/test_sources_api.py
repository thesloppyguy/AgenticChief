"""Sources status/sync API, freshness SLA, get_source_status tool, and mock-source ASGI smoke."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.alerts import engine as alerts_engine
from app.api.ingestion import get_extractors
from app.core.config import IntegrationConfig, settings as app_settings
from app.core.security import Principal, Role
from app.copilot.tools import run_tool
from app.db.models import IngestionRun, MockCompanyData
from app.db.session import get_db
from app.ingestion.live import RestExtractor
from app.ingestion.stub import StubExtractor
from app.ingestion.stubgen import synthetic_company
from app.main import app
from tests.api.conftest import auth, client  # noqa: F401

P = "2026-10"
ADMIN = Principal("u1", Role.ADMIN, None)


@pytest.fixture()
def db(client):
    gen = app.dependency_overrides[get_db]()
    d = next(gen)
    yield d
    d.close()


def test_sources_status_envelope_and_sla_states(client, db, monkeypatch):
    monkeypatch.setattr(app_settings, "source_freshness_sla_hours", 72.0)
    now = datetime.now(UTC)
    db.add(IngestionRun(
        source="successfactors", mode="stub", period=P, status="success",
        companies_ok=3, companies_failed=0, records_written=10,
        started_at=now - timedelta(hours=1), finished_at=now - timedelta(hours=1),
    ))
    db.add(IngestionRun(
        source="myhealth", mode="stub", period=P, status="success",
        companies_ok=3, companies_failed=0, records_written=3,
        started_at=now - timedelta(hours=100), finished_at=now - timedelta(hours=100),
    ))
    db.commit()

    r = client.get("/sources/status", headers=auth(Role.ADMIN))
    assert r.status_code == 200
    body = r.json()
    assert "mock_sources_enabled" in body and "sla_hours" in body and "sources" in body
    by = {s["source"]: s for s in body["sources"]}
    assert by["successfactors"]["freshness"] == "fresh"
    assert by["myhealth"]["freshness"] == "stale"
    assert by["hi5plus"]["freshness"] == "never"
    assert client.get("/sources/status", headers=auth(Role.VIEWER)).status_code == 403


def test_sources_sync_uses_extractors_and_records_runs(client, db):
    app.dependency_overrides[get_extractors] = lambda: {"successfactors": StubExtractor("successfactors")}
    admin = auth(Role.ADMIN)
    r = client.post("/sources/successfactors/sync", json={"period": P}, headers=admin)
    assert r.status_code == 200
    assert r.json()[0]["source"] == "successfactors" and r.json()[0]["status"] == "success"
    assert db.scalar(select(IngestionRun).where(IngestionRun.source == "successfactors")) is not None
    all_r = client.post("/sources/sync", json={"period": P}, headers=admin)
    assert all_r.status_code == 200
    assert client.post("/sources/nope/sync", json={"period": P}, headers=admin).status_code == 422
    app.dependency_overrides.pop(get_extractors, None)


def test_ingestion_status_includes_freshness_fields(client, db):
    st = client.get("/ingestion/status", headers=auth(Role.ADMIN)).json()
    assert isinstance(st, list) and st
    assert "freshness" in st[0] and "sla_hours" in st[0]


def test_get_source_status_tool_no_anthropic(db):
    out = run_tool(db, ADMIN, "get_source_status", {"period": P})
    assert "error" not in out
    assert out["as_of_month"] == P
    assert "source_freshness" in out and isinstance(out["data"], list)
    one = run_tool(db, ADMIN, "get_source_status", {"source": "successfactors", "period": P})
    assert len(one["data"]) == 1 and one["data"][0]["source"] == "successfactors"
    bad = run_tool(db, ADMIN, "get_source_status", {"source": "nope"})
    assert "error" in bad


def test_scorecard_includes_freshness(client, db):
    sc = client.get("/scorecard", params={"period": P}, headers=auth(Role.ADMIN)).json()
    assert "freshness" in sc
    assert sc["freshness"]["overall"] in ("fresh", "stale", "never", "partial")
    assert "sources" in sc["freshness"]


def test_check_source_freshness_raises_alerts(db, monkeypatch):
    monkeypatch.setattr(app_settings, "source_freshness_sla_hours", 1.0)
    now = datetime.now(UTC)
    db.add(IngestionRun(
        source="hi5plus", mode="stub", period=P, status="success",
        companies_ok=1, companies_failed=0, records_written=1,
        started_at=now - timedelta(hours=10), finished_at=now - timedelta(hours=10),
    ))
    db.commit()
    created = alerts_engine.check_source_freshness(db, period=P)
    kinds = {a.kind for a in created}
    assert "source_stale" in kinds
    again = alerts_engine.check_source_freshness(db, period=P)
    assert again == []


def test_live_extractor_against_mock_sources_asgi(client, db, tmp_path, monkeypatch):
    """RestExtractor → /mock-sources with pre-seeded MockCompanyData (no Anthropic)."""
    from app.mock_sources.router import router as mock_router

    already = any(getattr(r, "path", "").startswith("/mock-sources") for r in app.router.routes)
    if not already:
        app.include_router(mock_router)

    token = "test-mock-token"
    monkeypatch.setattr(app_settings, "mock_source_token", SecretStr(token))

    raw = synthetic_company("IC1", "steady")
    db.add(MockCompanyData(
        company_code="IC1", archetype="steady", origin="ai", model="test", raw=raw.model_dump(),
    ))
    db.commit()

    mapping = {
        "ahc_completion": {
            "path": "/mock-sources/myhealth/v2/ahc/summary",
            "params": {"orgCode": "{company_code}", "month": "{period}"},
            "result_path": "",
            "fields": {"completed": "completed", "eligible": "eligible"},
        }
    }
    mf = tmp_path / "myhealth.mapping.json"
    mf.write_text(json.dumps(mapping))

    def forward(req: httpx.Request) -> httpx.Response:
        r = client.request(
            req.method,
            req.url.path,
            params=dict(req.url.params),
            headers={"Authorization": req.headers.get("authorization", "")},
        )
        return httpx.Response(r.status_code, json=r.json(), headers=dict(r.headers))

    cfg = IntegrationConfig(
        enabled=True,
        base_url="http://testserver",
        auth="bearer",
        token=SecretStr(token),
        mapping_file=str(mf),
        timeout_s=30,
    )
    ex = RestExtractor("myhealth", cfg, transport=httpx.MockTransport(forward))
    out = ex.fetch("IC1", P)
    assert "ahc_completion" in out
    assert out["ahc_completion"]["completed"] is not None
    assert out["ahc_completion"]["eligible"] is not None
    assert ex.lineage_for("ahc_completion").get("origin") == "ai"
