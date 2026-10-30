import pytest
from sqlalchemy import select

from app.alerts import watches
from app.core.security import Role, make_token
from app.db.models import Alert, Company, JobSchedule, KpiRecord, Watch
from app.db.session import get_db
from app.kpi_registry.seed import KPIS
from app.main import app
from app.scheduler import jobs
from tests.api.conftest import client  # noqa: F401

PERIOD = "2026-10"
DAILY = {"type": "daily", "time": "06:00"}


def h(user, role=Role.ADMIN, companies=None):
    return {"Authorization": f"Bearer {make_token(user, role, companies)}"}


@pytest.fixture()
def db(client):
    d = next(app.dependency_overrides[get_db]())
    yield d
    d.close()


def cid(db, code):
    return db.scalar(select(Company.id).where(Company.code == code))


def fill(db, code, period, factor):
    """Every KPI at `factor` of target (lower-is-better inversely) -> that company scores ~factor*100.
    Idempotent, so a test can re-score the same month to set up a transition."""
    company_id = cid(db, code)
    existing = {r.kpi_key: r for r in db.scalars(select(KpiRecord).where(
        KpiRecord.company_id == company_id, KpiRecord.period == period))}
    for k in KPIS:
        ach = k.target / factor if k.direction.value == "lower" else k.target * factor
        if (rec := existing.get(k.key)) is not None:
            rec.achievement = ach
        else:
            db.add(KpiRecord(company_id=company_id, kpi_key=k.key, period=period,
                             achievement=ach, source="t"))
    db.commit()


def make(client, body, who=None):
    return client.post("/watches", json=body, headers=who or h("alice"))


def below(score=80.0, subject="overall", **kw):
    return {"subject": subject, "comparator": "below", "threshold": score, **kw}


# --- condition validation ----------------------------------------------------------------------

@pytest.mark.parametrize("condition, because", [
    ({"subject": "overall", "comparator": "equals", "threshold": 80}, "equals on a float score"),
    ({"subject": "overall", "comparator": "below"}, "no threshold"),
    ({"subject": "status", "comparator": "below", "threshold": 80}, "below on a status"),
    ({"subject": "status", "comparator": "equals"}, "no value"),
    ({"subject": "status", "comparator": "equals", "value": "red", "threshold": 1}, "threshold on a status"),
    ({"subject": "pillar", "comparator": "below", "threshold": 80}, "no pillar named"),
    ({"subject": "pillar", "comparator": "below", "threshold": 80, "pillar": "nope"}, "unknown pillar"),
    ({"subject": "overall", "comparator": "below", "threshold": 80, "pillar": "retention"}, "stray pillar"),
    ({"subject": "kpi", "comparator": "below", "threshold": 80}, "no kpi named"),
])
def test_an_incoherent_condition_is_refused(client, condition, because):
    r = make(client, {"name": "w", "company_code": "IC1", "condition": condition, "cadence": DAILY})
    assert r.status_code == 422, because


def test_an_unknown_kpi_is_refused(client, db):
    r = make(client, {"name": "w", "company_code": "IC1", "cadence": DAILY,
                      "condition": below(80, "kpi", kpi_key="not_a_kpi")})
    assert r.status_code == 422 and "unknown KPI" in r.json()["detail"]


# --- scope -------------------------------------------------------------------------------------

def test_a_watch_on_a_company_outside_your_scope_is_refused(client, db):
    r = make(client, {"name": "w", "company_code": "IC3", "condition": below(), "cadence": DAILY},
             who=h("bob", Role.VIEWER, [cid(db, "IC1")]))
    assert r.status_code == 403
    # An unknown company answers identically, so a watch cannot be used to enumerate companies.
    assert make(client, {"name": "w", "company_code": "NOPE", "condition": below(), "cadence": DAILY}
                ).status_code == 403


def test_a_scoped_user_cannot_create_a_group_wide_watch(client, db):
    r = make(client, {"name": "w", "company_code": None, "condition": below(), "cadence": DAILY},
             who=h("bob", Role.VIEWER, [cid(db, "IC1")]))
    assert r.status_code == 403


def test_a_scoped_user_may_own_a_watch_on_a_company_they_can_see(client, db):
    r = make(client, {"name": "mine", "company_code": "IC1", "condition": below(), "cadence": DAILY},
             who=h("bob", Role.VIEWER, [cid(db, "IC1")]))
    assert r.status_code == 201 and r.json()["company_code"] == "IC1"


# --- the paired schedule -----------------------------------------------------------------------

def test_creating_a_watch_creates_a_paired_schedule_and_deleting_it_removes_both(client, db):
    w = make(client, {"name": "retention", "company_code": "IC1", "condition": below(), "cadence": DAILY}).json()
    s = db.get(JobSchedule, w["schedule_id"])
    assert s.job == "watch" and s.params == {"watch_id": w["id"], "period": "current"}
    assert w["cadence"] == DAILY and w["next_run_at"]

    assert client.delete(f"/watches/{w['id']}", headers=h("alice")).status_code == 204
    db.expire_all()
    assert db.get(Watch, w["id"]) is None
    assert db.get(JobSchedule, w["schedule_id"]) is None


def test_disabling_a_watch_disables_its_schedule(client, db):
    w = make(client, {"name": "w", "company_code": "IC1", "condition": below(), "cadence": DAILY}).json()
    client.patch(f"/watches/{w['id']}", json={"enabled": False}, headers=h("alice"))
    db.expire_all()
    assert db.get(JobSchedule, w["schedule_id"]).enabled is False


def test_a_watch_schedule_cannot_be_created_by_hand_without_a_real_watch(client):
    r = client.post("/schedules", headers=h("alice"), json={
        "job": "watch", "name": "hand-made", "cadence": DAILY, "params": {"watch_id": 999}})
    assert r.status_code == 422


def test_clean_rejects_params_that_mean_nothing_to_the_job(client):
    r = client.post("/schedules", headers=h("alice"), json={
        "job": "monthly_review", "name": "x", "cadence": DAILY, "params": {"sources": ["successfactors"]}})
    assert r.status_code == 422 and "unknown params for monthly_review" in r.json()["detail"]


# --- firing ------------------------------------------------------------------------------------

def test_a_breached_watch_raises_one_alert_and_re_running_the_period_does_not_repeat_it(client, db):
    fill(db, "IC1", PERIOD, 0.5)  # ~50, well under the threshold
    w = make(client, {"name": "retention", "company_code": "IC1", "condition": below(80), "cadence": DAILY}).json()
    row = db.get(Watch, w["id"])

    first = watches.evaluate(db, row, PERIOD)
    db.commit()
    assert first is not None and first.kind == "watch_fired"
    assert first.audience_user_id == "alice" and first.dedupe_key == f"watch:{row.id}:{PERIOD}"
    assert first.detail["observed"] < 80

    again = watches.evaluate(db, row, PERIOD)
    db.commit()
    assert again is None and db.scalar(select(Alert.id).where(Alert.kind == "watch_fired")) == first.id


def test_a_watch_that_is_not_breached_stays_silent(client, db):
    fill(db, "IC1", PERIOD, 1.0)  # ~100
    w = make(client, {"name": "w", "company_code": "IC1", "condition": below(80), "cadence": DAILY}).json()
    assert watches.evaluate(db, db.get(Watch, w["id"]), PERIOD) is None


def test_a_missing_reading_never_fires(client, db):
    """No data is not a breach: an empty company must not look like a failing one."""
    w = make(client, {"name": "w", "company_code": "IC2", "condition": below(80), "cadence": DAILY}).json()
    seen = watches.observe(db, db.get(Watch, w["id"]), PERIOD)
    assert seen["observed"] is None and seen["would_fire"] is False


def test_changes_to_only_fires_on_the_transition(client, db):
    fill(db, "IC1", "2026-09", 1.0)   # green last month
    fill(db, "IC1", PERIOD, 0.5)      # red this month
    w = make(client, {"name": "turned red", "company_code": "IC1", "cadence": DAILY,
                      "condition": {"subject": "status", "comparator": "changes_to", "value": "red"}}).json()
    row = db.get(Watch, w["id"])
    assert watches.observe(db, row, PERIOD)["would_fire"] is True

    fill(db, "IC1", "2026-09", 0.5)   # already red last month -> no change
    db.commit()
    assert watches.observe(db, row, PERIOD)["would_fire"] is False


def test_changes_to_never_fires_in_april(client, db):
    """April opens a new fiscal year, so there is no previous month to have changed from."""
    fill(db, "IC1", "2026-04", 0.5)
    w = make(client, {"name": "w", "company_code": "IC1", "cadence": DAILY,
                      "condition": {"subject": "status", "comparator": "changes_to", "value": "red"}}).json()
    assert watches.observe(db, db.get(Watch, w["id"]), "2026-04")["would_fire"] is False


def test_a_pillar_watch_reads_that_pillars_score(client, db):
    fill(db, "IC1", PERIOD, 0.5)
    w = make(client, {"name": "retention pillar", "company_code": "IC1", "cadence": DAILY,
                      "condition": below(80, "pillar", pillar="retention")}).json()
    seen = watches.observe(db, db.get(Watch, w["id"]), PERIOD)
    assert seen["would_fire"] is True and 0 < seen["observed"] < 80


def test_a_group_watch_reads_the_group_score(client, db):
    for code in ("IC1", "IC2", "IC3"):
        fill(db, code, PERIOD, 0.5)
    w = make(client, {"name": "group", "company_code": None, "condition": below(80), "cadence": DAILY}).json()
    assert watches.observe(db, db.get(Watch, w["id"]), PERIOD)["would_fire"] is True


# --- audience ----------------------------------------------------------------------------------

def test_only_the_owner_sees_a_watch_alert(client, db):
    fill(db, "IC1", PERIOD, 0.5)
    w = make(client, {"name": "mine", "company_code": "IC1", "condition": below(80), "cadence": DAILY}).json()
    watches.evaluate(db, db.get(Watch, w["id"]), PERIOD)
    db.commit()

    mine = [a for a in client.get("/alerts", headers=h("alice")).json() if a["kind"] == "watch_fired"]
    theirs = [a for a in client.get("/alerts", headers=h("carol")).json() if a["kind"] == "watch_fired"]
    assert len(mine) == 1
    assert theirs == []  # carol is a group-wide admin and still must not see alice's private watch
    assert client.get("/unread/summary", headers=h("carol")).json()["alerts"] == 0


def test_watch_fired_can_be_muted(client, db):
    fill(db, "IC1", PERIOD, 0.5)
    w = make(client, {"name": "w", "company_code": "IC1", "condition": below(80), "cadence": DAILY}).json()
    watches.evaluate(db, db.get(Watch, w["id"]), PERIOD)
    db.commit()
    assert client.put("/alert-prefs", headers=h("alice"),
                      json={"min_severity": "low", "muted_kinds": ["watch_fired"]}).status_code == 200
    assert [a for a in client.get("/alerts", headers=h("alice")).json() if a["kind"] == "watch_fired"] == []


# --- listing, test endpoint, ownership ----------------------------------------------------------

def test_you_see_only_your_own_watches_unless_you_are_an_admin(client, db):
    viewer = h("bob", Role.VIEWER, [cid(db, "IC1")])
    make(client, {"name": "alices", "company_code": "IC1", "condition": below(), "cadence": DAILY})
    make(client, {"name": "bobs", "company_code": "IC1", "condition": below(), "cadence": DAILY}, who=viewer)
    assert [w["name"] for w in client.get("/watches", headers=viewer).json()] == ["bobs"]
    assert {w["name"] for w in client.get("/watches", headers=h("alice")).json()} == {"alices", "bobs"}


def test_another_users_watch_is_not_found_rather_than_forbidden(client, db):
    w = make(client, {"name": "alices", "company_code": "IC1", "condition": below(), "cadence": DAILY}).json()
    viewer = h("bob", Role.VIEWER, [cid(db, "IC1")])
    assert client.delete(f"/watches/{w['id']}", headers=viewer).status_code == 404
    assert client.post(f"/watches/{w['id']}/test", headers=viewer).status_code == 404


def test_the_test_endpoint_reports_what_it_sees_without_raising_an_alert(client, db):
    fill(db, "IC1", PERIOD, 0.5)
    w = make(client, {"name": "w", "company_code": "IC1", "condition": below(80), "cadence": DAILY}).json()
    body = client.post(f"/watches/{w['id']}/test?period={PERIOD}", headers=h("alice")).json()
    assert body["would_fire"] is True and body["observed"] < 80
    assert "overall score below 80" in body["condition"]
    assert db.scalar(select(Alert.id).where(Alert.kind == "watch_fired")) is None  # nothing was raised


# --- the scheduled job -------------------------------------------------------------------------

def test_the_watch_job_fires_and_reports_what_it_did(client, db):
    fill(db, "IC1", PERIOD, 0.5)
    w = make(client, {"name": "w", "company_code": "IC1", "condition": below(80), "cadence": DAILY}).json()
    from datetime import UTC, datetime

    now = datetime(2026, 10, 29, tzinfo=UTC)
    assert "fired" in jobs.job_watch(db, {"watch_id": w["id"], "period": PERIOD}, now, {})
    assert db.scalar(select(Alert.id).where(Alert.kind == "watch_fired")) is not None

    # Deduped, but still breaching: the log must not read as though the condition cleared.
    again = jobs.job_watch(db, {"watch_id": w["id"], "period": PERIOD}, now, {})
    assert "still breaching" in again and "no breach" not in again


def test_the_watch_job_fails_loudly_when_its_watch_is_gone(client, db):
    from datetime import UTC, datetime

    with pytest.raises(jobs.JobFailed):
        jobs.job_watch(db, {"watch_id": 999, "period": PERIOD}, datetime(2026, 10, 29, tzinfo=UTC), {})


def test_a_disabled_watch_is_skipped_without_firing(client, db):
    from datetime import UTC, datetime

    fill(db, "IC1", PERIOD, 0.5)
    w = make(client, {"name": "w", "company_code": "IC1", "condition": below(80), "cadence": DAILY,
                      "enabled": False}).json()
    detail = jobs.job_watch(db, {"watch_id": w["id"], "period": PERIOD}, datetime(2026, 10, 29, tzinfo=UTC), {})
    assert "disabled" in detail
    assert db.scalar(select(Alert.id).where(Alert.kind == "watch_fired")) is None
