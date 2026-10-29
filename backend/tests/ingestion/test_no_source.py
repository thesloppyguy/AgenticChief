import json

import pytest

from app.copilot.tools import run_tool
from app.core.config import IntegrationConfig, Settings, settings
from app.core.security import Principal, Role
from app.db.session import get_db
from app.ingestion import registry
from app.ingestion.sources import SOURCE_KPIS
from app.main import app
from tests.api.conftest import auth, client  # noqa: F401

P = "2026-10"


def S(**kw):
    return Settings(_env_file=None, **kw)


def test_stub_mode_means_everything_has_a_source():
    assert registry.no_source_kpis(S()) == frozenset()


def test_everything_disabled_means_all_19_sourced_kpis_have_no_source():
    ns = registry.no_source_kpis(S(stub_data_enabled=False))
    assert len(ns) == 19 and ns == {k for ks in SOURCE_KPIS.values() for k in ks}
    assert not ns & {"cost_per_hire", "gptw_score", "idps_top_talent", "top_talent_review"}  # manual


def test_live_source_only_covers_kpis_in_its_mapping(tmp_path):
    f = tmp_path / "m.json"
    f.write_text(json.dumps({"kra_submission": {}, "mid_term_review": {}}))
    s = S(integrations={"successfactors": IntegrationConfig(enabled=True, base_url="https://x", token="t",
                                                            mapping_file=str(f))})
    ns = registry.source_no_source_kpis("successfactors", s)
    assert ns == set(SOURCE_KPIS["successfactors"]) - {"kra_submission", "mid_term_review"}
    assert registry.source_no_source_kpis("myhealth", s) == frozenset()  # still on stub data
    # live enabled but no mapping file at all: nothing is mapped yet
    s2 = S(integrations={"successfactors": IntegrationConfig(enabled=True, base_url="https://x", token="t")})
    assert registry.source_no_source_kpis("successfactors", s2) == set(SOURCE_KPIS["successfactors"])
    assert registry.describe(s)[0]["no_source_kpis"]


@pytest.fixture()
def seeded(client):
    from app.ingestion.runner import ingest
    from app.ingestion.stub import StubExtractor
    db = next(app.dependency_overrides[get_db]())
    ingest(db, P, {s: StubExtractor(s) for s in SOURCE_KPIS})
    yield db
    db.close()


def test_api_marks_no_source_ignores_stale_values_and_leaves_manual_alone(client, seeded, monkeypatch):
    admin = auth(Role.ADMIN)
    before = client.get("/scorecard", params={"period": P}, headers=admin).json()
    assert before["no_source_kpis"] == [] and before["group"]["companies_with_data"] == 3
    ta0 = next(p for p in before["group"]["pillars"] if p["pillar"] == "talent_acquisition")

    monkeypatch.setattr(settings, "stub_data_enabled", False)  # sources vanish; stored values go stale
    after = client.get("/scorecard", params={"period": P}, headers=admin).json()
    assert len(after["no_source_kpis"]) == 19
    ta = next(p for p in after["group"]["pillars"] if p["pillar"] == "talent_acquisition")
    assert {k["key"]: k["excluded_reason"] for k in ta["kpis"]}["time_to_fill"] == "no_source"
    assert ta["score"] != ta0["score"]

    d = client.get("/scorecard/pillars/talent_acquisition", params={"period": P}, headers=admin).json()
    ttf = next(k for k in d["kpis"] if k["key"] == "time_to_fill")
    assert ttf["no_source"] is True and ttf["coverage"] == 0 and ttf["group_excluded_reason"] == "no_source"
    assert {c["excluded_reason"] for c in ttf["companies"]} == {"no_source"}


def test_copilot_tools_separate_no_source_from_missing_submissions(client, seeded, monkeypatch):
    who = Principal("u", Role.ADMIN, None)
    monkeypatch.setattr(settings, "stub_data_enabled", False)
    miss = run_tool(seeded, who, "list_missing_submissions", {"period": P})
    assert len(miss["no_source_kpis"]) == 19
    assert not {m["kpi_key"] for m in miss["missing"]} & set(miss["no_source_kpis"])  # not "owed" by anyone
    grp = run_tool(seeded, who, "get_group_score", {"period": P})
    assert "time_to_fill" in grp["no_source_kpis"]
