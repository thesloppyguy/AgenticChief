import json

import httpx
import pytest

from app.core.config import IntegrationConfig, Settings
from app.ingestion import registry
from app.ingestion.base import IntegrationDisabled
from app.ingestion.live import RestExtractor, dig
from app.ingestion.stub import StubExtractor

MAPPING = {"kra_submission": {
    "path": "/api/kra", "params": {"company": "{company_code}", "period": "{period}"},
    "result_path": "d.results.0", "fields": {"submitted": "Submitted", "eligible": "Eligible"}},
    "mid_term_review": {"path": "/api/mt", "result_path": "d.results.0",
                        "fields": {"completed": "Done", "eligible": "Elig"}}}


def cfg(tmp_path, **kw):
    f = tmp_path / "m.json"
    f.write_text(json.dumps(MAPPING))
    return IntegrationConfig(enabled=True, base_url="https://sf.example", token="tok", mapping_file=str(f), **kw)


def test_dig():
    assert dig({"a": [{"b": 5}]}, "a.0.b") == 5
    assert dig({"a": []}, "a.0.b") is None and dig({}, "x") is None and dig({"a": 1}, "") == {"a": 1}


def test_disabled_integration_cannot_be_built():
    with pytest.raises(IntegrationDisabled):
        RestExtractor("successfactors", IntegrationConfig())


def test_rest_extractor_maps_fields_sends_auth_and_skips_unmapped(tmp_path):
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        if req.url.path == "/api/kra":
            return httpx.Response(200, json={"d": {"results": [{"Submitted": 90, "Eligible": 100}]}})
        return httpx.Response(200, json={"d": {"results": []}})  # no row for mid-term

    ex = RestExtractor("successfactors", cfg(tmp_path), transport=httpx.MockTransport(handler))
    out = ex.fetch("IC007", "2026-10")
    assert out == {"kra_submission": {"submitted": 90.0, "eligible": 100.0}}  # mid-term: no row -> omitted
    assert ex.mapped_kpis == ("kra_submission", "mid_term_review")  # the other 12 SF KPIs have no source
    kra = next(r for r in seen if r.url.path == "/api/kra")
    assert kra.headers["authorization"] == "Bearer tok"
    assert kra.url.params["company"] == "IC007" and kra.url.params["period"] == "2026-10"


def test_http_error_propagates_for_runner_to_record(tmp_path):
    ex = RestExtractor("successfactors", cfg(tmp_path),
                       transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(httpx.HTTPStatusError):
        ex.fetch("IC001", "2026-10")


def test_mapping_for_foreign_kpi_rejected(tmp_path):
    f = tmp_path / "m.json"
    f.write_text(json.dumps({"ahc_completion": {}}))  # belongs to MyHealth
    with pytest.raises(ValueError):
        RestExtractor("successfactors", IntegrationConfig(enabled=True, base_url="https://x", token="t",
                                                          mapping_file=str(f)))


def test_missing_credentials_error_does_not_leak(tmp_path):
    c = IntegrationConfig(enabled=True, base_url="https://x", auth="basic", mapping_file=None)
    with pytest.raises(ValueError, match="credentials"):
        RestExtractor("successfactors", c, transport=httpx.MockTransport(lambda r: httpx.Response(200)))._auth_headers()


# --- registry / flags ---

def S(**kw):
    return Settings(_env_file=None, **kw)


def test_default_is_stub_for_every_source_and_live_flags_are_off():
    s = S(stub_data_path="/nonexistent.json")
    ex = registry.build_extractors(s)
    assert set(ex) == {"successfactors", "peoplestrong", "myhealth", "hi5plus"}
    assert all(isinstance(e, StubExtractor) for e in ex.values())
    assert all(not d["live_enabled"] and d["mode"] == "stub" for d in registry.describe(s))


def test_stub_off_and_live_off_means_disabled_sources_absent():
    s = S(stub_data_enabled=False)
    assert registry.build_extractors(s) == {}
    assert {d["mode"] for d in registry.describe(s)} == {"disabled"}


def test_live_flag_wins_for_that_source_only(tmp_path):
    s = S(stub_data_path="/nonexistent.json", integrations={
        "successfactors": IntegrationConfig(enabled=True, base_url="https://sf.example", token="t")})
    ex = registry.build_extractors(s)
    assert isinstance(ex["successfactors"], RestExtractor)
    assert isinstance(ex["myhealth"], StubExtractor)


def test_flags_load_from_environment(monkeypatch):
    monkeypatch.setenv("INTEGRATIONS__SUCCESSFACTORS__ENABLED", "true")
    monkeypatch.setenv("INTEGRATIONS__SUCCESSFACTORS__BASE_URL", "https://sf.example")
    s = Settings(_env_file=None)
    assert s.integration("successfactors").enabled and s.integration("successfactors").base_url
    assert not s.integration("myhealth").enabled


def test_a_real_vendor_sends_no_origin_header_so_its_data_is_never_marked_synthetic(tmp_path):
    """The origin marker exists only for the AI-backed mock systems; real data must not be labelled."""
    from sqlalchemy.orm import sessionmaker

    from app.core.security import Principal, Role
    from app.db.models import Company
    from app.db.session import Base
    from app.db.sqlite import configure_sqlite
    from app.ingestion.runner import ingest
    from app.services.scorecard import build_scorecard

    f = tmp_path / "m.json"
    f.write_text(json.dumps({"kra_submission": {"path": "/api/kra", "result_path": "d.results.0",
                                                "fields": {"submitted": "Submitted", "eligible": "Eligible"}}}))

    def respond(headers):
        return httpx.MockTransport(lambda r: httpx.Response(200, json={"d": {"results": [{"Submitted": 90, "Eligible": 100}]}}, headers=headers))

    cfg = IntegrationConfig(enabled=True, base_url="https://sf.example", token="t", mapping_file=str(f))
    real, mock = RestExtractor("successfactors", cfg, transport=respond({})), RestExtractor("successfactors", cfg, transport=respond({"X-Data-Origin": "ai"}))
    real.fetch("IC1", "2026-10"), mock.fetch("IC1", "2026-10")
    assert real.lineage_for("kra_submission") == {} and mock.lineage_for("kra_submission") == {"origin": "ai"}

    from sqlalchemy import create_engine
    eng = configure_sqlite(create_engine(f"sqlite:///{tmp_path / 'x.db'}", connect_args={"check_same_thread": False}))
    Base.metadata.create_all(eng)
    factory = sessionmaker(eng, expire_on_commit=False)
    with factory() as db:
        db.add(Company(code="IC1", name="One"))
        db.commit()
        who = Principal("a", Role.ADMIN, None)
        ingest(db, "2026-10", {"successfactors": real})
        assert build_scorecard(db, who, "2026-10")["synthetic_data"] is False                 # genuinely real as far as we can tell
        ingest(db, "2026-10", {"successfactors": mock})
        assert build_scorecard(db, who, "2026-10")["synthetic_data"] is True                  # the same numbers, now declared AI-made
    eng.dispose()
