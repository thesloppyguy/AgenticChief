from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.core.security import Role, make_token
from app.db.session import get_db
from app.ingestion.runner import ingest
from app.ingestion.sources import SOURCE_KPIS
from app.ingestion.stub import StubExtractor
from app.kpi_registry.seed import DEFAULT_CONFIG as CFG
from app.kpi_registry.seed import KPIS
from app.main import app
from app.scorecard_config.rules import DEFAULT_RULES, ScorecardRules, to_scoring_config
from app.scoring import score_ic, score_kpi
from app.scoring.models import KpiValue
from tests.api.conftest import client  # noqa: F401

P = "2026-10"


def h(user, role=Role.ADMIN, companies=None):
    return {"Authorization": f"Bearer {make_token(user, role, companies)}"}


ALICE, BOB = h("alice"), h("bob")


def v(x):
    return KpiValue(x)


# --- engine: the new rules ---

def test_prorating_scores_a_year_to_date_kpi_against_the_part_of_the_year_elapsed():
    idps = next(k for k in KPIS if k.key == "idps_top_talent")           # target 25 for the full year, cumulative
    pro = replace(CFG, prorate_cumulative=True)
    assert score_kpi(idps, v(5), 4, CFG).score == pytest.approx(20)       # April, 5 of 25: looks terrible
    assert score_kpi(idps, v(5), 4, pro).score == pytest.approx(240)      # target is 25/12 in April, so 5 is well ahead
    assert score_kpi(idps, v(12.5), 9, pro).score == pytest.approx(100)   # September: 6 of 12 months, target 12.5
    assert score_kpi(idps, v(25), 3, pro).score == pytest.approx(100)     # March: the full target
    other = next(k for k in KPIS if k.key == "gptw_score")                # not cumulative: never pro-rated
    assert score_kpi(other, v(40), 4, pro).score == score_kpi(other, v(40), 4, CFG).score == pytest.approx(50)


def test_low_coverage_withholds_the_status_but_keeps_the_score():
    only_retention = {"overall_retention": v(100)}                         # 15% of the weight
    plain = score_ic(KPIS, only_retention, 8, CFG)
    assert plain.status is not None and not plain.status_withheld
    strict = score_ic(KPIS, only_retention, 8, replace(CFG, min_coverage_for_status=0.7))
    assert strict.score == pytest.approx(100) and strict.status is None and strict.status_withheld
    enough = score_ic(KPIS, {k.key: v(k.target) for k in KPIS}, 8, replace(CFG, min_coverage_for_status=0.7))
    assert enough.status is not None and not enough.status_withheld
    empty = score_ic(KPIS, {}, 8, replace(CFG, min_coverage_for_status=0.7))
    assert empty.score is None and not empty.status_withheld              # nothing to withhold


def test_cap_and_thresholds_flow_from_the_rules():
    rules = ScorecardRules(score_cap=100, green_min=95, amber_min=80)
    cfg = to_scoring_config(rules, 7)
    assert cfg.version == "7" and cfg.score_cap == 100 and (cfg.green_min, cfg.amber_min) == (95, 80)
    gptw = next(k for k in KPIS if k.key == "gptw_score")
    assert score_kpi(gptw, v(120), 8, CFG).score == pytest.approx(150)    # uncapped by default
    assert score_kpi(gptw, v(120), 8, cfg).score == pytest.approx(100)


# --- rules validation ---

@pytest.mark.parametrize("change,msg", [
    ({"pillar_weights": {**DEFAULT_RULES.pillar_weights, "retention": 0.5}}, "add up to 100%"),
    ({"pillar_weights": {"retention": 1.0}}, "exactly the 7 pillars"),
    ({"pillar_weights": {**DEFAULT_RULES.pillar_weights, "retention": 0.0, "talent_management": 0.35}}, "above zero"),
    ({"green_min": 70, "amber_min": 75}, "below green_min"),
    ({"score_cap": 80}, "green unreachable"),
    ({"score_cap": 100, "zero_lower_is_better_score": 150}, "cannot exceed score_cap"),
    ({"min_coverage_for_status": 1.5}, "less than or equal to 1"),
    ({"missing_ic_policy": "guess"}, "exclude"),
])
def test_invalid_rules_never_validate(change, msg):
    with pytest.raises(ValidationError, match=msg):
        ScorecardRules(**{**DEFAULT_RULES.model_dump(), **change})


def test_defaults_reproduce_todays_behaviour():
    cfg = to_scoring_config(DEFAULT_RULES, 1)
    assert (cfg.score_cap, cfg.min_coverage_for_status, cfg.prorate_cumulative) == (None, 0.0, False)
    assert cfg.pillar_weights == CFG.pillar_weights and (cfg.green_min, cfg.amber_min) == (90, 75)


# --- the workflow: draft -> preview -> second admin approves -> live ---

@pytest.fixture()
def data(client):
    db = next(app.dependency_overrides[get_db]())
    ex = {s: StubExtractor(s) for s in SOURCE_KPIS}
    ingest(db, P, ex)
    yield db
    db.close()


def draft(client, rules, headers=ALICE, note="tighten"):
    return client.post("/scorecard-config/drafts", json={"rules": rules, "note": note}, headers=headers)


def activate(client, version):
    r = client.post("/approvals", json={"action": "activate_scorecard_config", "args": {"version": version}}, headers=ALICE)
    if r.status_code != 201:
        return r
    return client.post(f"/approvals/{r.json()['approval']['id']}/decision", json={"decision": "approve"}, headers=BOB)


def test_starts_on_the_built_in_defaults_as_version_one(client, data):
    o = client.get("/scorecard-config", headers=h("vic", Role.VIEWER)).json()
    assert o["active"]["version"] == 1 and o["active"]["built_in"] and o["versions"] == []
    sc = client.get("/scorecard", params={"period": P}, headers=ALICE).json()
    assert sc["calc_version"] == "1" and sc["thresholds"] == {"green_min": 90.0, "amber_min": 75.0}
    assert all(p["status"] in ("green", "amber", "red") for p in sc["group"]["pillars"] if p["score"] is not None)


def test_a_draft_is_a_partial_change_validated_and_never_a_no_op(client, data):
    r = draft(client, {"score_cap": 100})
    assert r.status_code == 201 and r.json()["version"] == 2 and r.json()["status"] == "draft"
    assert r.json()["rules"]["score_cap"] == 100 and r.json()["rules"]["green_min"] == 90     # unchanged fields carried over
    assert draft(client, {"pillar_weights": {"retention": 0.9}}).status_code == 422
    bad = draft(client, {"green_min": 50, "amber_min": 60})
    assert bad.status_code == 422 and "below green_min" in bad.json()["detail"]
    assert draft(client, {}).status_code == 422                                              # changes nothing
    assert draft(client, {"score_cap": 100}, headers=h("e", Role.EDITOR)).status_code == 403


def test_preview_shows_the_effect_before_anything_is_activated(client, data):
    v2 = draft(client, {"score_cap": 100, "green_min": 95}).json()["version"]
    pv = client.get(f"/scorecard-config/{v2}/preview", params={"period": P}, headers=ALICE).json()
    assert pv["draft"]["distribution"]["green"] < pv["active"]["distribution"]["green"]       # a higher bar: fewer green
    assert pv["companies_changing_status"] > 0 and pv["examples"][0]["from"] != pv["examples"][0]["to"]
    live = client.get("/scorecard", params={"period": P}, headers=ALICE).json()
    assert live["calc_version"] == "1"                                                        # a preview changes nothing
    assert client.get("/scorecard-config/99/preview", headers=ALICE).status_code == 404


def test_activation_needs_a_second_admin_and_then_drives_every_score(client, data):
    before = client.get("/scorecard", params={"period": P}, headers=ALICE).json()
    v2 = draft(client, {"score_cap": 100, "green_min": 95, "amber_min": 80}).json()["version"]
    prop = client.post("/approvals", json={"action": "activate_scorecard_config", "args": {"version": v2}}, headers=ALICE).json()
    ctx = prop["approval"]["context"]
    assert ctx["replacing_version"] == 1 and ctx["changes"]["score_cap"] == {"from": None, "to": 100}
    assert set(ctx["changes"]) == {"score_cap", "green_min", "amber_min"}                     # the approver sees exactly what changes
    assert client.post(f"/approvals/{prop['approval']['id']}/decision", json={"decision": "approve"}, headers=ALICE).status_code == 403
    assert client.get("/scorecard", params={"period": P}, headers=ALICE).json()["calc_version"] == "1"
    done = client.post(f"/approvals/{prop['approval']['id']}/decision", json={"decision": "approve"}, headers=BOB).json()
    assert done["status"] == "executed" and done["result"] == {"active_version": 2}

    after = client.get("/scorecard", params={"period": P}, headers=ALICE).json()
    assert after["calc_version"] == "2" and after["thresholds"] == {"green_min": 95.0, "amber_min": 80.0}
    n_green = lambda c: sum(x["status"] == "green" for x in c["companies"])
    assert n_green(after) < n_green(before)
    assert max(c["score"] for c in after["companies"] if c["score"] is not None) <= 100        # the cap applies everywhere
    o = client.get("/scorecard-config", headers=ALICE).json()
    assert o["active"]["version"] == 2 and not o["active"]["built_in"]
    assert [(x["version"], x["status"]) for x in o["versions"]] == [(2, "active")]
    assert client.get("/kpis", headers=ALICE).json()["thresholds"] == {"green_min": 95.0, "amber_min": 80.0}
    snap = client.post("/reports/snapshots", params={"period": P}, headers=ALICE).json()["id"]
    assert client.get(f"/reports/snapshots/{snap}", headers=ALICE).json()["calc_version"] == "2"  # reports keep their version


def test_a_later_version_supersedes_and_only_drafts_can_be_activated(client, data):
    v2 = draft(client, {"score_cap": 100}).json()["version"]
    assert activate(client, v2).json()["status"] == "executed"
    assert activate(client, v2).status_code == 422                                            # already active
    assert activate(client, 9).status_code == 422                                             # unknown
    v3 = draft(client, {"prorate_cumulative": True, "min_coverage_for_status": 0.5}).json()
    assert v3["version"] == 3 and v3["rules"]["score_cap"] == 100                             # builds on the ACTIVE rules
    assert activate(client, 3).json()["status"] == "executed"
    o = client.get("/scorecard-config", headers=ALICE).json()
    assert {x["version"]: x["status"] for x in o["versions"]} == {3: "active", 2: "superseded"}
    assert o["active"]["rules"]["prorate_cumulative"] is True


def test_low_coverage_withholds_status_through_the_api(client, data, monkeypatch):
    """Coverage is the share of PILLAR weight with something scoreable. With every source off, only the
    Engagement pillar (via a manual GPTW entry) can be scored: 10% of the weight."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "stub_data_enabled", False)
    editor = h("erin", Role.EDITOR)
    for cid in (1, 2, 3):
        assert client.post("/inputs", json={"company_id": cid, "period": P, "kpi_key": "gptw_score", "value": 85},
                           headers=editor).status_code == 201
    thin = client.get("/scorecard", params={"period": P}, headers=ALICE).json()
    assert thin["group"]["pillar_coverage"] == pytest.approx(0.10) and thin["group"]["status"] is not None  # default: no rule

    v2 = draft(client, {"min_coverage_for_status": 0.5}).json()["version"]
    assert activate(client, v2).json()["status"] == "executed"
    sc = client.get("/scorecard", params={"period": P}, headers=ALICE).json()
    assert sc["group"]["score"] is not None and sc["group"]["status"] is None and sc["group"]["status_withheld"]
    assert all(c["status"] is None and c["status_withheld"] and c["score"] is not None for c in sc["companies"])
    co = client.get("/scorecard/companies/1", params={"period": P}, headers=ALICE).json()
    assert co["status_withheld"] and co["status"] is None


def test_the_catalog_and_scoring_endpoints_reject_outsiders(client, data):
    assert client.get("/scorecard-config").status_code in (401, 403)
    assert client.post("/scorecard-config/drafts", json={"rules": {"score_cap": 100}}, headers=h("sam", Role.ADMIN, [1])).status_code == 403
    assert client.get("/scorecard-config/2/preview", headers=h("vic", Role.VIEWER)).status_code == 403
