import pytest
from pydantic import ValidationError

from app.core.security import Role, make_token
from app.db.models import Document
from app.db.session import get_db
from app.ingestion.runner import ingest
from app.ingestion.sources import SOURCE_KPIS
from app.ingestion.stub import StubExtractor
from app.knowledge import store
from app.kpi_registry.seed import DEFAULT_CONFIG as CFG
from app.kpi_registry.seed import KPIS
from app.main import app
from app.scorecard_config.rules import DEFAULT_RULES, ScorecardRules, effective_kpis
from app.scorecard_config.service import diff
from app.scoring import score_ic, score_kpi
from app.scoring.models import KpiValue
from tests.api.conftest import client  # noqa: F401

P = "2026-10"


def h(user, role=Role.ADMIN):
    return {"Authorization": f"Bearer {make_token(user, role, None)}"}


ALICE, BOB = h("alice"), h("bob")


def rules(**ov):
    return ScorecardRules(**{**DEFAULT_RULES.model_dump(), "kpi_overrides": ov})


def v(x):
    return KpiValue(x)


# --- the rules ---

def test_overrides_change_only_what_they_name():
    kp = {k.key: k for k in effective_kpis(rules(gptw_score={"target": 70}).kpi_overrides)}
    assert kp["gptw_score"].target == 70 and kp["gptw_score"].weight == 0.5            # weight untouched
    assert kp["kra_submission"].target == 100 and kp["kra_submission"].weight == 0.25   # everything else untouched
    assert effective_kpis({}) == list(KPIS)


def test_a_pillars_kpi_weights_must_still_add_up_to_100_percent():
    ok = rules(offer_to_joining={"weight": 0.40}, time_to_fill={"weight": 0.20}, new_hire_retention_12m={"weight": 0.20}, cost_per_hire={"weight": 0.20})
    assert sum(k.weight for k in effective_kpis(ok.kpi_overrides) if k.pillar == "talent_acquisition") == pytest.approx(1.0)
    with pytest.raises(ValidationError, match=r"Talent Acquisition: KPI weights add up to 110%"):
        rules(offer_to_joining={"weight": 0.35})
    with pytest.raises(ValidationError, match="Engagement / Wellness"):
        rules(gptw_score={"weight": 0.4})                                               # 25+25+40 = 90%


@pytest.mark.parametrize("ov,msg", [
    ({"nope": {"target": 5}}, "unknown KPI"),
    ({"training_calendar": {"target": 3}}, "calendar rule"),
    ({"gptw_score": {}}, "must change the weight or the target"),
    ({"gptw_score": {"target": 0}}, "greater than 0"), ({"gptw_score": {"target": -5}}, "greater than 0"),
    ({"gptw_score": {"weight": 1.5}}, "less than or equal to 1"),
])
def test_bad_overrides_are_refused(ov, msg):
    with pytest.raises(ValidationError, match=msg):
        rules(**ov)


def test_diff_reports_effective_kpi_changes_and_ignores_no_ops():
    d = diff(DEFAULT_RULES, rules(kra_submission={"target": 50}, gptw_score={"target": 80}))   # 80 is already the default
    assert d == {"kpi.kra_submission.target": {"from": 100, "to": 50}}


def test_overrides_flow_through_the_engine():
    gptw = next(k for k in effective_kpis(rules(gptw_score={"target": 40}).kpi_overrides) if k.key == "gptw_score")
    assert score_kpi(gptw, v(40), 8, CFG).score == pytest.approx(100)                   # target 40: a score of 40 is on target
    assert score_kpi(next(k for k in KPIS if k.key == "gptw_score"), v(40), 8, CFG).score == pytest.approx(50)
    heavy = effective_kpis(rules(offer_to_joining={"weight": 0.55}, time_to_fill={"weight": 0.15}, new_hire_retention_12m={"weight": 0.15},
                                 cost_per_hire={"weight": 0.15}).kpi_overrides)
    vals = {"offer_to_joining": v(100), "time_to_fill": v(120), "new_hire_retention_12m": v(100)}   # time to fill scores 50
    plain = next(p for p in score_ic(KPIS, vals, 8, CFG).pillars if p.pillar == "talent_acquisition").score
    weighted = next(p for p in score_ic(heavy, vals, 8, CFG).pillars if p.pillar == "talent_acquisition").score
    assert plain == pytest.approx((100 + 50 + 100) / 3) and weighted == pytest.approx((55 * 100 + 15 * 50 + 15 * 100) / 85)


# --- the workflow ---

@pytest.fixture()
def data(client):
    db = next(app.dependency_overrides[get_db]())
    ingest(db, P, {s: StubExtractor(s) for s in SOURCE_KPIS})
    yield db
    db.close()


def activate(client, version):
    r = client.post("/approvals", json={"action": "activate_scorecard_config", "args": {"version": version}}, headers=ALICE)
    return r if r.status_code != 201 else client.post(f"/approvals/{r.json()['approval']['id']}/decision", json={"decision": "approve"}, headers=BOB)


def test_a_target_change_is_drafted_previewed_approved_and_then_used_everywhere(client, data):
    before = client.get("/scorecard/pillars/performance_management", params={"period": P}, headers=ALICE).json()
    kra0 = next(k for k in before["kpis"] if k["key"] == "kra_submission")
    assert kra0["target"] == 100
    d = client.post("/scorecard-config/drafts", json={"rules": {"kpi_overrides": {"kra_submission": {"target": 90}}}, "note": "KRA bar is 90%"}, headers=ALICE)
    assert d.status_code == 201 and d.json()["rules"]["kpi_overrides"] == {"kra_submission": {"weight": None, "target": 90.0}}
    prop = client.post("/approvals", json={"action": "activate_scorecard_config", "args": {"version": 2}}, headers=ALICE).json()
    assert prop["approval"]["context"]["changes"] == {"kpi.kra_submission.target": {"from": 100.0, "to": 90.0}}   # the approver sees exactly this
    pv = client.get("/scorecard-config/2/preview", params={"period": P}, headers=ALICE).json()
    assert pv["draft"]["group_score"] != pv["active"]["group_score"]                                            # and its effect, before activation
    assert client.get("/kpis", headers=ALICE).json()["calc_version"] == "1"

    done = client.post(f"/approvals/{prop['approval']['id']}/decision", json={"decision": "approve"}, headers=BOB).json()
    assert done["status"] == "executed"
    after = client.get("/scorecard/pillars/performance_management", params={"period": P}, headers=ALICE).json()
    kra1 = next(k for k in after["kpis"] if k["key"] == "kra_submission")
    assert kra1["target"] == 90 and kra1["group_score"] == pytest.approx(kra0["group_score"] * 100 / 90)       # scored against the new bar
    cat = next(k for k in client.get("/kpis", headers=ALICE).json()["kpis"] if k["key"] == "kra_submission")
    assert (cat["target"], cat["default_target"], cat["weight"]) == (90, 100, 0.25)
    assert client.get("/scorecard", params={"period": P}, headers=ALICE).json()["calc_version"] == "2"


def test_the_builtin_kpi_document_is_refreshed_atomically_with_the_activation(client, data):
    def doc_text():
        return " ".join(h_.text for h_ in store.search(data, "KRA submission timeliness target", limit=4))

    from app.knowledge import builtin
    builtin.seed_builtin(data)
    data.expire_all()
    assert "Target: 100" in doc_text()
    client.post("/scorecard-config/drafts", json={"rules": {"kpi_overrides": {"kra_submission": {"target": 85}}}}, headers=ALICE)
    assert activate(client, 2).json()["status"] == "executed"
    data.expire_all()
    text = doc_text()
    assert "Target: 85" in text and "Target: 100. Higher is better. Source: SAP SuccessFactors.\nEmployees who submitted" not in text
    assert data.query(Document).filter_by(builtin=True, domain="scorecard").count() == 2                                            # replaced, not duplicated


def test_invalid_kpi_changes_are_rejected_at_draft_time_with_the_reason(client, data):
    r = client.post("/scorecard-config/drafts", json={"rules": {"kpi_overrides": {"offer_to_joining": {"weight": 0.5}}}}, headers=ALICE)
    assert r.status_code == 422 and "Talent Acquisition" in r.json()["detail"] and "125%" in r.json()["detail"]
    assert client.post("/scorecard-config/drafts", json={"rules": {"kpi_overrides": {"training_calendar": {"target": 3}}}}, headers=ALICE).status_code == 422
    assert client.get("/scorecard-config", headers=ALICE).json()["versions"] == []


def test_resetting_an_override_back_to_the_default_counts_as_no_change(client, data):
    client.post("/scorecard-config/drafts", json={"rules": {"kpi_overrides": {"kra_submission": {"target": 90}}}}, headers=ALICE)
    activate(client, 2)
    r = client.post("/scorecard-config/drafts", json={"rules": {"kpi_overrides": {}}}, headers=ALICE)          # back to defaults
    assert r.status_code == 201
    prop = client.post("/approvals", json={"action": "activate_scorecard_config", "args": {"version": 3}}, headers=ALICE).json()
    assert prop["approval"]["context"]["changes"] == {"kpi.kra_submission.target": {"from": 90.0, "to": 100.0}}
