import json
import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import IntegrationConfig, Settings
from app.core.security import Role, make_token
from app.db.models import KpiRecord, MockCompanyData
from app.ingestion import registry
from app.ingestion.live import RestExtractor
from app.ingestion.raw import to_metric
from app.ingestion.runner import ingest
from app.ingestion.sources import SOURCE_KPIS
from app.ingestion.stub import StubExtractor
from app.ingestion.stubgen import CompanyRaw
from app.mock_sources import router as mock_router
from app.mock_sources import store
from app.mock_sources.catalog import mapping_for
from scripts.setup_mock_sources import MAPPINGS, env_block, write_mappings
from tests.mock_sources.conftest import TOKEN

P = "2026-10"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def h(user="alice", role=Role.ADMIN, companies=None):
    return {"Authorization": f"Bearer {make_token(user, role, companies)}"}


SF_KRA = "/mock-sources/successfactors/odata/v2/KraSubmission"
SF_Q = {"$filter": "companyCode eq 'IC001' and period eq '2026-10'", "$format": "json"}


# --- authentication ---

def test_the_mock_systems_require_their_own_bearer_token(env, monkeypatch):
    c = env.client
    assert c.get(SF_KRA, params=SF_Q).status_code == 401
    assert c.get(SF_KRA, params=SF_Q, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert c.get(SF_KRA, params=SF_Q, headers={"Authorization": f"Basic {TOKEN}"}).status_code == 401
    assert c.get(SF_KRA, params=SF_Q, headers=h()).status_code == 401                       # a platform login is not a source credential
    assert c.get(SF_KRA, params=SF_Q, headers=AUTH).status_code == 200
    monkeypatch.setattr("app.mock_sources.router.settings.mock_source_token", None)
    assert c.get(SF_KRA, params=SF_Q, headers=AUTH).status_code == 503                       # unconfigured: refuse, never open
    assert env.ai.calls == [["IC001"]]                                                       # only the authorized call cost anything


# --- each system answers in its own style ---

def test_each_source_has_its_own_response_shape(env):
    c = env.client
    sf = c.get(SF_KRA, params=SF_Q, headers=AUTH).json()
    assert set(sf["d"]["results"][0]) == {"Submitted", "Eligible"} and sf["d"]["results"][0]["Eligible"] > 0
    ps = c.get("/mock-sources/peoplestrong/api/v1/recruitment/offer-to-joining", params={"company": "IC001", "period": P}, headers=AUTH).json()
    assert ps["status"] == "ok" and set(ps["data"]) == {"joined", "offers"}
    mh = c.get("/mock-sources/myhealth/v2/ahc/summary", params={"orgCode": "IC001", "month": P}, headers=AUTH).json()
    assert set(mh) == {"completed", "eligible"}                                              # flat
    hi = c.get("/mock-sources/hi5plus/engagement/adoption", params={"entity": "IC001", "ym": P}, headers=AUTH).json()
    assert set(hi["result"]["adoption"]) == {"uniqueLogins", "activeEmployees"}              # nested, camelCase
    r = c.get("/mock-sources/myhealth/v2/ahc/summary", params={"orgCode": "IC001", "month": P}, headers=AUTH)
    assert r.headers["x-data-origin"] == "ai"


def test_bad_requests_are_422_and_unknown_companies_get_an_empty_row_without_any_ai_call(env):
    c = env.client
    assert c.get(SF_KRA, params={"$filter": "anything"}, headers=AUTH).status_code == 422
    assert c.get(SF_KRA, params={}, headers=AUTH).status_code == 422
    assert c.get("/mock-sources/myhealth/v2/ahc/summary", params={"orgCode": "IC001"}, headers=AUTH).status_code == 422
    assert c.get("/mock-sources/myhealth/v2/ahc/summary", params={"orgCode": "IC001", "month": "2026-13"}, headers=AUTH).status_code == 422
    ghost = c.get(SF_KRA, params={"$filter": "companyCode eq 'IC999' and period eq '2026-10'"}, headers=AUTH)
    assert ghost.status_code == 200 and ghost.json() == {"d": {"results": []}} and ghost.headers["x-data-origin"] == "none"
    evil = c.get(SF_KRA, params={"$filter": "companyCode eq 'x'; DROP TABLE company' and period eq '2026-10'"}, headers=AUTH)
    assert evil.status_code == 422
    assert env.ai.calls == []                                                                # nothing here may spend money


# --- generation: on first need, once, consistently ---

def test_a_company_is_generated_on_first_request_then_served_from_storage(env):
    c = env.client
    first = c.get(SF_KRA, params=SF_Q, headers=AUTH).json()
    again = c.get(SF_KRA, params=SF_Q, headers=AUTH).json()
    assert first == again and env.ai.calls == [["IC001"]]                                    # one AI call, however often it is asked
    with env.factory() as db:
        row = db.scalar(select(MockCompanyData))
        assert (row.company_code, row.origin, row.model) == ("IC001", "ai", store.model_name())
        assert CompanyRaw(**row.raw).company_code == "IC001"
    other = c.get(SF_KRA, params={"$filter": "companyCode eq 'IC002' and period eq '2026-10'"}, headers=AUTH).json()
    assert other != first and env.ai.calls == [["IC001"], ["IC002"]]


def test_numbers_are_consistent_across_periods_and_valid_in_every_month(env):
    c = env.client
    seen = []
    for p in ("2026-04", "2026-07", "2026-10"):
        row = c.get(SF_KRA, params={"$filter": f"companyCode eq 'IC001' and period eq '{p}'"}, headers=AUTH).json()["d"]["results"][0]
        assert row["Submitted"] <= row["Eligible"]
        seen.append(row["Eligible"])
    assert len(set(seen)) <= 3 and max(seen) - min(seen) <= 0.07 * max(seen)               # a stable base with small drift
    cal = lambda p: c.get("/mock-sources/successfactors/odata/v2/TrainingCalendar", headers=AUTH,
                          params={"$filter": f"companyCode eq 'IC001' and period eq '{p}'", "$format": "json"}).json()["d"]["results"][0]["Value"]
    assert all(cal(p) <= 1 for p in ("2026-04", "2026-09"))                                  # the Oct-Mar calendar cannot exist yet


def test_simultaneous_requests_for_a_new_company_make_one_ai_call(env):
    results = []
    gate = threading.Barrier(6)

    def go():
        gate.wait()
        results.append(TestClient(env.app).get(SF_KRA, params=SF_Q, headers=AUTH).status_code)

    ts = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in ts]
    [t.join(timeout=30) for t in ts]
    assert results == [200] * 6 and env.ai.calls == [["IC001"]]


def test_when_the_model_is_unavailable_the_endpoint_says_so_unless_fallback_is_allowed(env, monkeypatch):
    env.ai.fail = True
    r = env.client.get(SF_KRA, params=SF_Q, headers=AUTH)
    assert r.status_code == 503 and "unavailable" in r.json()["detail"]
    with env.factory() as db:
        assert db.query(MockCompanyData).count() == 0                                        # nothing invented in the failure case
    monkeypatch.setattr("app.mock_sources.router.settings.mock_sources_allow_fallback", True)
    monkeypatch.setattr(store.settings, "mock_sources_allow_fallback", True)
    r = env.client.get(SF_KRA, params=SF_Q, headers=AUTH)
    assert r.status_code == 200 and r.headers["x-data-origin"] == "fallback"                 # and it is labelled


# --- warming everything up in the background ---

def wait_job(c, headers, secs=20):
    for _ in range(secs * 10):
        s = c.get("/mock-sources/admin/status", headers=headers).json()
        if not s["job"]["running"]:
            return s
        time.sleep(0.1)
    raise AssertionError("generation did not finish")


def test_admin_can_generate_everything_in_the_background_and_reset(env):
    c, adm = env.client, h()
    assert c.get("/mock-sources/admin/status", headers=adm).json()["generated"] == 0
    assert c.post("/mock-sources/admin/generate", headers=adm).status_code == 202
    s = wait_job(c, adm)
    assert s["generated"] == 3 and s["ai"] == 3 and s["job"]["result"] == {"ai": 3, "fallback": 0, "failed": [], "notes": []}
    assert env.ai.calls == [["IC001", "IC002", "IC003"]]                                     # one batched call for all three
    assert c.post("/mock-sources/admin/generate", headers=adm).status_code == 202            # nothing missing: a no-op, not an error
    wait_job(c, adm)
    assert env.ai.calls == [["IC001", "IC002", "IC003"]]
    assert c.delete("/mock-sources/admin/data", headers=adm).status_code == 204
    assert c.get("/mock-sources/admin/status", headers=adm).json()["generated"] == 0


def test_a_company_the_model_drops_is_retried_then_reported(env):
    env.ai.drop = {"IC002"}
    c, adm = env.client, h()
    c.post("/mock-sources/admin/generate", headers=adm)
    s = wait_job(c, adm)
    assert s["ai"] == 2 and s["job"]["result"]["failed"] == ["IC002"]
    assert env.ai.calls == [["IC001", "IC002", "IC003"], ["IC002"]]                          # the retry asked only for the missing one


def test_admin_endpoints_are_admin_only_and_need_a_key(env):
    c = env.client
    for who in (h("e", Role.EDITOR), h("v", Role.VIEWER), h("s", Role.ADMIN, [1])):
        assert c.get("/mock-sources/admin/status", headers=who).status_code == 403
        assert c.post("/mock-sources/admin/generate", headers=who).status_code == 403
        assert c.delete("/mock-sources/admin/data", headers=who).status_code == 403
    env.app.dependency_overrides[mock_router.get_ai_client] = lambda: None
    assert c.post("/mock-sources/admin/generate", headers=h()).status_code == 503


# --- the contract with the live adapters ---

def test_the_committed_mapping_files_match_the_catalog():
    for source in SOURCE_KPIS:
        assert json.loads((MAPPINGS / f"{source}.mapping.json").read_text()) == mapping_for(source), f"{source}: rerun scripts.setup_mock_sources"


def test_setup_writes_mappings_and_a_complete_env_block_once(tmp_path):
    env_ = env_block("http://localhost:8000/api", "tok")
    assert env_["MOCK_SOURCES_ENABLED"] == "true" and env_["MOCK_SOURCE_TOKEN"] == "tok"
    assert {k for k in env_ if k.endswith("__ENABLED") and k.startswith("INTEGRATIONS__")} == {f"INTEGRATIONS__{s.upper()}__ENABLED" for s in SOURCE_KPIS}
    assert len(write_mappings()) == 4


@pytest.mark.parametrize("source", list(SOURCE_KPIS))
def test_every_kpi_of_every_source_round_trips_through_the_real_live_adapter_over_http(server, source):
    """live adapter -> bearer auth -> HTTP -> mock endpoint -> AI-generated profile: the raw counts that
    come back must equal what the profile says, for every KPI the source supplies."""
    cfg = IntegrationConfig(enabled=True, base_url=server.url, auth="bearer", token=TOKEN,
                            mapping_file=str(MAPPINGS / f"{source}.mapping.json"), timeout_s=30)
    ex = RestExtractor(source, cfg)
    assert set(ex.mapped_kpis) == set(SOURCE_KPIS[source])                                   # nothing left without a source
    got = ex.fetch("IC001", P)
    with server.factory() as db:
        prof = {r.company_code: CompanyRaw(**r.raw) for r in db.scalars(select(MockCompanyData))}
    want = StubExtractor(source, prof).fetch("IC001", P)
    assert set(got) == set(want) == set(SOURCE_KPIS[source])
    for kpi in want:
        assert got[kpi] == {k: pytest.approx(float(v)) for k, v in want[kpi].items()}, kpi
        to_metric(kpi, got[kpi])                                                             # and they pass the production validation


def test_a_wrong_token_makes_the_live_adapter_fail_cleanly(server):
    cfg = IntegrationConfig(enabled=True, base_url=server.url, auth="bearer", token="wrong",
                            mapping_file=str(MAPPINGS / "myhealth.mapping.json"), timeout_s=10)
    import httpx
    with pytest.raises(httpx.HTTPStatusError):
        RestExtractor("myhealth", cfg).fetch("IC001", P)


def test_a_full_ingestion_run_uses_the_live_adapters_and_stores_live_lineage(server, monkeypatch):
    """The point of the exercise: 'live' sources whose data is AI-generated, ingested like real ones."""
    integrations = {s: IntegrationConfig(enabled=True, base_url=server.url, auth="bearer", token=TOKEN,
                                         mapping_file=str(MAPPINGS / f"{s}.mapping.json"), timeout_s=30) for s in SOURCE_KPIS}
    cfg = Settings(_env_file=None, integrations=integrations, stub_data_enabled=False)
    assert {d["mode"] for d in registry.describe(cfg)} == {"live"} and registry.no_source_kpis(cfg) == frozenset()
    with server.factory() as db:
        summaries = ingest(db, P, registry.build_extractors(cfg, db=db))
        assert [(s.source, s.mode, s.status, s.companies_ok) for s in summaries] == [(s, "live", "success", 3) for s in SOURCE_KPIS]
        assert sum(s.records_written for s in summaries) == 3 * 19
        rec = db.scalar(select(KpiRecord).where(KpiRecord.kpi_key == "kra_submission", KpiRecord.company_id == 1))
        assert rec.detail["mode"] == "live" and rec.source == "successfactors" and rec.numerator and rec.denominator
        prof = CompanyRaw(**db.scalar(select(MockCompanyData).where(MockCompanyData.company_code == "IC001")).raw)
        assert rec.detail["origin"] == "ai"                                                  # the source said how its data was made
        from app.core.security import Principal
        from app.services.scorecard import build_scorecard
        card = build_scorecard(db, Principal("a", Role.ADMIN, None), P)
        assert card["synthetic_data"] is True                                                # no manual or seed data here: it is the AI origin
        assert rec.denominator == pytest.approx(prof.eligible_employees, rel=0.04)           # it is the AI profile's number (plus small drift)
    asked = sorted(code for call in server.ai.calls for code in call)
    assert asked == ["IC001", "IC002", "IC003"]                                              # each company generated exactly once
