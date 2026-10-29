import pytest
from sqlalchemy import select

from app.alerts import engine
from app.alerts.engine import prev_period
from app.core.security import Role, make_token
from app.db.models import Alert, Company, KpiRecord
from app.db.session import get_db
from app.ingestion.runner import SourceSummary
from app.kpi_registry.seed import KPIS
from app.main import app
from tests.api.conftest import client  # noqa: F401


def h(user, role, companies=None):
    return {"Authorization": f"Bearer {make_token(user, role, companies)}"}


@pytest.fixture()
def db(client):
    d = next(app.dependency_overrides[get_db]())
    yield d
    d.close()


def cid(db, code):
    return db.scalar(select(Company.id).where(Company.code == code))


def fill(db, code, period, factor):
    """Every sourced KPI at `factor` of target (lower-is-better ones inversely) -> IC score ~ factor*100."""
    for k in KPIS:
        ach = k.target / factor if k.direction.value == "lower" else k.target * factor
        db.add(KpiRecord(company_id=cid(db, code), kpi_key=k.key, period=period, achievement=ach, source="t"))
    db.commit()


def alerts(db):
    return {(a.entity, a.period): a for a in db.scalars(select(Alert))}


def test_prev_period_stays_inside_the_fiscal_year():
    assert prev_period("2026-10") == "2026-09"
    assert prev_period("2027-01") == "2026-12"
    assert prev_period("2026-04") is None   # new April-March year starts fresh


def test_turned_red_alert_has_severity_and_drivers(db):
    fill(db, "IC1", "2026-09", 1.0)    # green last month
    fill(db, "IC1", "2026-10", 0.5)    # red now
    fill(db, "IC2", "2026-09", 0.8)    # amber last month
    fill(db, "IC2", "2026-10", 0.5)
    fill(db, "IC3", "2026-09", 0.5)    # red both months: no change, no alert
    fill(db, "IC3", "2026-10", 0.5)
    created = engine.evaluate_period(db, "2026-10")
    got = alerts(db)
    assert ("IC3", "2026-10") not in got
    a1, a2 = got[("IC1", "2026-10")], got[("IC2", "2026-10")]
    assert (a1.severity, a2.severity) == ("high", "medium")
    assert "turned red (was green)" in a1.title and a1.company_id == cid(db, "IC1")
    assert a1.detail["previous_status"] == "green" and len(a1.detail["weakest_pillars"]) == 2
    assert ("group", "2026-10") in got and got[("group", "2026-10")].company_id is None
    assert len(created) == 3


def test_first_reading_is_low_and_group_urgent_only_when_it_changes(db):
    fill(db, "IC1", "2026-04", 0.5)   # April: no previous period
    engine.evaluate_period(db, "2026-04")
    got = alerts(db)
    assert got[("IC1", "2026-04")].severity == "low" and "first reading" in got[("IC1", "2026-04")].title
    assert got[("group", "2026-04")].severity == "high"       # new red at group level
    fill(db, "IC1", "2026-05", 1.0)
    engine.evaluate_period(db, "2026-05")
    fill(db, "IC1", "2026-06", 0.5)
    engine.evaluate_period(db, "2026-06")
    assert alerts(db)[("group", "2026-06")].severity == "urgent"   # green -> red at group level


def test_reevaluating_does_not_duplicate(db):
    fill(db, "IC1", "2026-09", 1.0)
    fill(db, "IC1", "2026-10", 0.5)
    first = engine.evaluate_period(db, "2026-10")
    again = engine.evaluate_period(db, "2026-10")
    assert first and again == [] and db.query(Alert).count() == len(first)


def test_no_alert_when_not_red(db):
    fill(db, "IC1", "2026-09", 1.0)
    fill(db, "IC1", "2026-10", 0.8)   # amber
    assert engine.evaluate_period(db, "2026-10") == []


def test_ingestion_failure_alerts_dedupe_per_run(db):
    bad = SourceSummary("successfactors", "live", "failed", 0, 3, 0, run_id=7)
    part = SourceSummary("myhealth", "live", "partial", 2, 1, 5, run_id=8)
    ok = SourceSummary("hi5plus", "stub", "success", 3, 0, 9, run_id=9)
    assert len(engine.on_ingestion(db, [bad, part, ok], "2026-10")) == 2
    assert engine.on_ingestion(db, [bad], "2026-10") == []
    sev = {a.entity: a.severity for a in db.scalars(select(Alert))}
    assert sev == {"successfactors": "high", "myhealth": "medium"}


def test_scoped_users_see_only_their_companies_and_read_state_is_per_user(client, db):
    fill(db, "IC1", "2026-09", 1.0)
    fill(db, "IC1", "2026-10", 0.5)
    fill(db, "IC2", "2026-09", 1.0)
    fill(db, "IC2", "2026-10", 0.5)
    engine.evaluate_period(db, "2026-10")
    admin, ic1 = h("root", Role.ADMIN), h("one", Role.VIEWER, [1])
    assert {a["entity"] for a in client.get("/alerts", headers=admin).json()} == {"group", "IC1", "IC2"}
    mine = client.get("/alerts", headers=ic1).json()
    assert [a["entity"] for a in mine] == ["IC1"]            # no IC2, and no group-wide alerts
    assert client.get("/unread/summary", headers=ic1).json()["alerts"] == 1
    other = client.get("/alerts", headers=admin).json()
    ic2_id = next(a["id"] for a in other if a["entity"] == "IC2")
    assert client.post(f"/alerts/{ic2_id}/read", headers=ic1).status_code == 404   # cannot even touch it
    assert client.post(f"/alerts/{mine[0]['id']}/read", headers=ic1).status_code == 200
    assert client.get("/unread/summary", headers=ic1).json()["alerts"] == 0
    assert client.get("/alerts", params={"unread_only": True}, headers=ic1).json() == []
    assert client.get("/alerts", headers=ic1).json()[0]["read"] is True
    assert client.get("/unread/summary", headers=admin).json()["alerts"] == 3     # admin's own state differs
    assert client.post("/alerts/read-all", headers=admin).json() == {"marked": 3}
    assert client.get("/unread/summary", headers=admin).json()["alerts"] == 0


def test_manual_input_that_turns_a_company_red_raises_an_alert(client, db):
    db.add(KpiRecord(company_id=cid(db, "IC1"), kpi_key="gptw_score", period="2026-09", achievement=80, source="manual"))
    db.commit()
    editor = h("erin", Role.EDITOR)
    r = client.post("/inputs", json={"company_id": cid(db, "IC1"), "period": "2026-10", "kpi_key": "gptw_score",
                                     "value": 20}, headers=editor)
    assert r.status_code == 201
    got = alerts(db)
    assert ("IC1", "2026-10") in got and "turned red" in got[("IC1", "2026-10")].title
    assert ("group", "2026-10") not in got       # a single company's edit does not re-judge the group


def test_ingestion_run_endpoint_raises_failure_and_status_alerts(client, db):
    from app.api.ingestion import get_extractors
    from app.ingestion.base import Extractor

    class Broken(Extractor):
        source, mode, kpis = "hi5plus", "live", ("platform_adoption",)

        def fetch(self, company_code, period):
            raise ConnectionError("down")

    app.dependency_overrides[get_extractors] = lambda: {"hi5plus": Broken()}
    try:
        r = client.post("/ingestion/run", json={"period": "2026-10"}, headers=h("root", Role.ADMIN))
        assert r.json()[0]["status"] == "failed"
    finally:
        app.dependency_overrides.pop(get_extractors)
    assert [a.kind for a in db.scalars(select(Alert))] == ["ingestion_failed"]
