import pytest

from app.core.security import Role

from .conftest import auth

P = "2026-10"


def put(client, h, **kw):
    return client.post("/inputs", json={"period": P, **kw}, headers=h)


def test_requires_auth(client):
    assert client.get("/scorecard").status_code in (401, 403)


def test_viewer_cannot_enter_manual_input(client):
    r = put(client, auth(Role.VIEWER), company_id=1, kpi_key="gptw_score", value=70)
    assert r.status_code == 403


def test_editor_scoped_to_own_companies(client):
    h = auth(Role.EDITOR, [1])
    assert put(client, h, company_id=1, kpi_key="gptw_score", value=70).status_code == 201
    assert put(client, h, company_id=2, kpi_key="gptw_score", value=70).status_code == 403
    assert client.get("/companies", headers=h).json() == [{"id": 1, "code": "IC1", "name": "Co 1"}]
    assert client.get("/scorecard/companies/2", params={"period": P}, headers=h).status_code == 403


def test_validation(client):
    h = auth(Role.EDITOR)
    assert put(client, h, company_id=1, kpi_key="time_to_fill", value=5).status_code == 422  # not manual
    assert put(client, h, company_id=1, kpi_key="gptw_score", value=-1).status_code == 422
    assert put(client, h, company_id=1, kpi_key="cost_per_hire", recruitment_cost=10).status_code == 422
    assert put(client, h, company_id=1, kpi_key="top_talent_review", reviewed=True).status_code == 422
    assert client.post("/inputs", json={"company_id": 1, "period": "2026-13", "kpi_key": "gptw_score",
                                        "value": 1}, headers=h).status_code == 422


def test_history_records_old_and_new(client):
    h = auth(Role.EDITOR)
    put(client, h, company_id=1, kpi_key="gptw_score", value=70)
    put(client, h, company_id=1, kpi_key="gptw_score", value=80)
    hist = client.get("/inputs/history", params={"company_id": 1}, headers=h).json()
    assert len(hist) == 2
    assert hist[0]["old"]["achievement"] == 70 and hist[0]["new"]["achievement"] == 80
    assert hist[0]["user"] == "u1"


def test_scorecard_group_cost_per_hire_and_scoring(client):
    h = auth(Role.ADMIN)
    put(client, h, company_id=1, kpi_key="cost_per_hire", recruitment_cost=100000, hires=1)
    put(client, h, company_id=2, kpi_key="cost_per_hire", recruitment_cost=5_000_000, hires=100)
    put(client, h, company_id=1, kpi_key="gptw_score", value=80)
    sc = client.get("/scorecard", params={"period": P}, headers=h).json()
    assert sc["group"]["companies_with_data"] == 2
    assert sc["synthetic_data"] is False  # manual entries are real
    drill = client.get("/scorecard/pillars/talent_acquisition", params={"period": P}, headers=h).json()
    cph = next(k for k in drill["kpis"] if k["key"] == "cost_per_hire")
    assert cph["group_achievement"] == pytest.approx(5_100_000 / 101)
    assert cph["coverage"] == 2
    ic1 = next(c for c in sc["companies"] if c["code"] == "IC1")
    ew = next(p for p in ic1["pillars"] if p["pillar"] == "engagement_wellness")
    assert ew["score"] == pytest.approx(100)  # only GPTW eligible, 80/80


def test_snapshot_admin_only_and_immutable_listing(client):
    assert client.post("/reports/snapshots", headers=auth(Role.EDITOR)).status_code == 403
    r = client.post("/reports/snapshots", params={"period": P}, headers=auth(Role.ADMIN))
    assert r.status_code == 201
    got = client.get(f"/reports/snapshots/{r.json()['id']}", headers=auth(Role.VIEWER)).json()
    assert got["period"] == P
    assert client.get("/reports/snapshots", headers=auth(Role.VIEWER, [1])).status_code == 403
