import asyncio
import json
import socket
import threading
import time
from datetime import UTC, datetime

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.alerts import bus, engine
from app.alerts import prefs as P
from app.api.alerts import router as alerts_router
from app.api.workflows import get_session_factory
from app.core.security import Principal, Role, make_token
from app.db import models  # noqa: F401
from app.db.models import Alert, Company
from app.db.session import Base, get_db
from app.db.sqlite import configure_sqlite
from tests.api.conftest import client  # noqa: F401


def dt(h, m=0):
    return datetime(2026, 10, 29, h, m, tzinfo=UTC)


def h(user, role=Role.VIEWER, companies=None):
    return {"Authorization": f"Bearer {make_token(user, role, companies)}"}


# --- quiet hours and visibility: the pure rules ---

@pytest.mark.parametrize("start,end,tz,now,quiet", [
    ("22:00", "07:00", "UTC", dt(23), True), ("22:00", "07:00", "UTC", dt(3), True),          # an overnight window wraps midnight
    ("22:00", "07:00", "UTC", dt(7), False), ("22:00", "07:00", "UTC", dt(12), False),        # the end is exclusive
    ("22:00", "07:00", "UTC", dt(22), True),                                                  # the start is inclusive
    ("09:00", "17:00", "UTC", dt(12), True), ("09:00", "17:00", "UTC", dt(17), False),        # a same-day window
    ("22:00", "07:00", "Asia/Kolkata", dt(17, 30), True),                                     # 17:30 UTC is 23:00 in Kolkata
    ("22:00", "07:00", "Asia/Kolkata", dt(2), False),                                         # 02:00 UTC is 07:30 in Kolkata
    ("22:00", "07:00", "America/New_York", dt(4), True),                                      # 04:00 UTC is midnight in New York
    (None, None, "UTC", dt(3), False),
])
def test_quiet_hours(start, end, tz, now, quiet):
    assert P.is_quiet(P.Prefs(quiet_start=start, quiet_end=end, tz=tz), now) is quiet


def test_visibility_and_push_rules():
    p = P.Prefs(min_severity="medium", muted_kinds=["ingestion_failed"], quiet_start="22:00", quiet_end="07:00")
    assert P.visible(p, "high", "status_red") and P.visible(p, "medium", "status_red")
    assert not P.visible(p, "low", "status_red") and not P.visible(p, "urgent", "ingestion_failed")   # even urgent, if muted
    night, day = dt(23), dt(12)
    assert not P.should_push(p, "high", "status_red", night) and P.should_push(p, "high", "status_red", day)
    assert P.should_push(p, "urgent", "status_red", night)                                       # urgent breaks quiet hours
    assert not P.should_push(p, "urgent", "ingestion_failed", night)                             # but never a muted kind


@pytest.mark.parametrize("bad,msg", [
    (dict(min_severity="loud"), "min_severity"), (dict(muted_kinds=["nonsense"]), "unknown alert kinds"),
    (dict(quiet_start="22:00"), "both"), (dict(quiet_start="25:00", quiet_end="07:00"), "HH:MM"),
    (dict(quiet_start="22:00", quiet_end="22:00"), "same time"), (dict(tz="Mars/Olympus"), "IANA"),
])
def test_invalid_preferences_are_refused(bad, msg):
    with pytest.raises(P.PrefsError, match=msg):
        P.validate(P.Prefs(**bad))


# --- the API and the feed ---

@pytest.fixture()
def db(client):
    d = next(__import__("app.main", fromlist=["app"]).app.dependency_overrides[get_db]())
    yield d
    d.close()


def add_alerts(db):
    for i, (kind, sev) in enumerate([("status_red", "low"), ("status_red", "high"), ("ingestion_failed", "high"),
                                     ("workflow_failed", "medium"), ("status_red", "urgent")]):
        db.add(Alert(kind=kind, severity=sev, company_id=None, entity="g", period="2026-10", title=f"{kind}-{sev}",
                     detail={}, dedupe_key=f"k{i}"))
    db.commit()


def test_preferences_persist_per_user_and_filter_the_feed_and_the_badge(client, db):
    add_alerts(db)
    root, other = h("root", Role.ADMIN), h("other", Role.ADMIN)
    assert client.get("/alert-prefs", headers=root).json()["min_severity"] == "low"
    assert client.get("/unread/summary", headers=root).json()["alerts"] == 5
    r = client.put("/alert-prefs", json={"min_severity": "medium", "muted_kinds": ["ingestion_failed"], "quiet_start": "22:00",
                                         "quiet_end": "07:00", "tz": "Asia/Kolkata"}, headers=root)
    assert r.status_code == 200 and r.json()["muted_kinds"] == ["ingestion_failed"] and r.json()["tz"] == "Asia/Kolkata"
    titles = lambda **p: sorted(a["title"] for a in client.get("/alerts", params=p, headers=root).json())
    assert titles() == ["status_red-high", "status_red-urgent", "workflow_failed-medium"]              # low and muted are hidden
    assert client.get("/unread/summary", headers=root).json()["alerts"] == 3                            # the badge agrees
    assert len(titles(include_hidden=True)) == 5                                                        # nothing is lost, only hidden
    assert client.get("/unread/summary", headers=other).json()["alerts"] == 5                           # other users are unaffected
    assert client.put("/alert-prefs", json={"min_severity": "nope"}, headers=root).status_code == 422
    assert client.get("/alert-prefs", headers=root).json()["min_severity"] == "medium"                   # a rejected save changed nothing


# --- the bus ---

class Loop:
    """A real event loop in a thread, standing in for a connected client's server task."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.t = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.t.start()

    def get(self, sub, timeout=2.0):
        try:
            return asyncio.run_coroutine_threadsafe(asyncio.wait_for(sub.queue.get(), timeout), self.loop).result(timeout + 1)
        except TimeoutError:
            return None

    def stop(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.t.join(timeout=3)


@pytest.fixture()
def loop():
    lp = Loop()
    yield lp
    lp.stop()


def alert(**kw):
    return {"id": 1, "kind": "status_red", "severity": "high", "title": "T", "entity": "IC1", "company_id": None, "period": "2026-10", **kw}


def test_delivery_respects_scope_and_preferences(loop):
    sends = {}
    subs = {"group": Principal("g", Role.VIEWER, None), "mine": Principal("m", Role.VIEWER, frozenset({1})),
            "other": Principal("o", Role.VIEWER, frozenset({2}))}
    live = {k: bus.subscribe(v, P.Prefs(), loop.loop) for k, v in subs.items()}
    try:
        sends["group_alert"] = bus.publish(alert(company_id=None))                                     # group-wide alert
        sends["ic1_alert"] = bus.publish(alert(company_id=1))
        assert loop.get(live["group"])["company_id"] is None and loop.get(live["group"])["company_id"] == 1
        assert loop.get(live["mine"])["company_id"] == 1 and loop.get(live["mine"]) is None            # only their company, never the group one
        assert loop.get(live["other"]) is None                                                         # another company's alert never reaches them
        assert sends == {"group_alert": 1, "ic1_alert": 2}
    finally:
        for s in live.values():
            bus.unsubscribe(s)


def test_muting_severity_quiet_hours_and_live_preference_changes_apply_to_push(loop):
    p = P.Prefs(min_severity="medium", muted_kinds=["workflow_failed"], quiet_start="22:00", quiet_end="07:00")
    s = bus.subscribe(Principal("u", Role.VIEWER, None), p, loop.loop)
    try:
        assert bus.publish(alert(severity="low"), dt(12)) == 0                                         # below the minimum
        assert bus.publish(alert(kind="workflow_failed"), dt(12)) == 0                                  # muted
        assert bus.publish(alert(severity="high"), dt(23)) == 0                                         # quiet hours
        assert bus.publish(alert(severity="urgent"), dt(23)) == 1                                       # urgent breaks through
        assert bus.publish(alert(severity="high"), dt(12)) == 1
        assert loop.get(s)["severity"] == "urgent" and loop.get(s)["severity"] == "high" and loop.get(s) is None
        bus.prefs_changed("u", P.Prefs(min_severity="low"))                                              # saved in the settings page
        assert bus.publish(alert(severity="low"), dt(12)) == 1
        bus.prefs_changed("someone-else", P.Prefs(min_severity="urgent"))
        assert bus.publish(alert(severity="low"), dt(12)) == 1                                           # not applied to the wrong user
    finally:
        bus.unsubscribe(s)
    assert bus.publish(alert(severity="urgent")) == 0                                                    # unsubscribed: nothing


def test_a_client_whose_loop_has_gone_is_dropped_not_fatal():
    lp = Loop()
    s = bus.subscribe(Principal("gone", Role.VIEWER, None), P.Prefs(), lp.loop)
    lp.stop()
    lp.loop.close()
    assert bus.publish(alert()) == 0 and bus.subscriber_count() == 0


# --- alerts are published after the commit, never before, never if rolled back ---

@pytest.fixture()
def factory(tmp_path):
    eng = configure_sqlite(create_engine(f"sqlite:///{tmp_path / 'a.db'}", connect_args={"check_same_thread": False}))
    Base.metadata.create_all(eng)
    f = sessionmaker(eng, expire_on_commit=False)
    with f() as db:
        db.add_all(Company(code=f"IC{i}", name=f"C{i}") for i in range(1, 3))
        db.commit()
    yield f
    eng.dispose()


def raise_one(db, key, company_id=None, severity="high"):
    return engine._raise(db, kind="status_red", severity=severity, company_id=company_id, entity="IC1", period="2026-10",
                         title="Turned red", detail={}, dedupe_key=key)


def test_an_alert_goes_out_only_when_its_transaction_commits(factory, loop):
    s = bus.subscribe(Principal("u", Role.VIEWER, None), P.Prefs(), loop.loop)
    try:
        with factory() as db:
            raise_one(db, "a")
            assert loop.get(s, 0.4) is None                                                              # not yet: nothing is committed
            db.commit()
        got = loop.get(s)
        assert got["title"] == "Turned red" and got["id"] is not None
        with factory() as db:
            raise_one(db, "b")
            db.rollback()                                                                                # the work is undone...
        assert loop.get(s, 0.6) is None                                                                  # ...so nobody is told
        with factory() as db:
            raise_one(db, "c")
            raise_one(db, "c")                                                                           # a duplicate is not raised twice
            db.commit()
        assert loop.get(s)["id"] and loop.get(s, 0.6) is None
    finally:
        bus.unsubscribe(s)


# --- the stream, over real HTTP ---

@pytest.fixture()
def live_server(factory):
    app = FastAPI()
    app.include_router(alerts_router)
    app.dependency_overrides[get_db] = lambda: iter([factory()])
    app.dependency_overrides[get_session_factory] = lambda: factory
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        port = sk.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", factory
    srv.should_exit = True
    t.join(timeout=5)


def collect(url, headers, out, ready, stop):
    try:
        with httpx.stream("GET", f"{url}/alerts/stream", headers=headers, timeout=httpx.Timeout(10, read=10)) as r:
            out.append(("status", r.status_code))
            ev = None
            for line in r.iter_lines():
                if line.startswith("event:"):
                    ev = line[6:].strip()
                    if ev == "ready":
                        ready.set()
                elif line.startswith("data:") and ev == "alert":
                    out.append(json.loads(line[5:]))
                if stop.is_set():
                    break
    except httpx.HTTPError as e:
        out.append(("error", type(e).__name__))


def test_a_connected_client_receives_live_alerts_it_may_see(live_server):
    url, factory = live_server
    group, scoped, denied = [], [], []
    stops = [threading.Event() for _ in range(3)]
    readies = [threading.Event() for _ in range(2)]
    ts = [threading.Thread(target=collect, args=(url, h("g", Role.VIEWER), group, readies[0], stops[0])),
          threading.Thread(target=collect, args=(url, h("s", Role.VIEWER, [1]), scoped, readies[1], stops[1])),
          threading.Thread(target=collect, args=(url, {}, denied, threading.Event(), stops[2]))]
    [t.start() for t in ts]
    assert all(r.wait(10) for r in readies), "the streams did not open"
    with factory() as db:
        raise_one(db, "g1", company_id=None)                                                             # a group-wide alert
        raise_one(db, "c1", company_id=1)                                                                 # one for company 1
        db.commit()
    deadline = time.time() + 8
    while time.time() < deadline and (len([x for x in group if isinstance(x, dict)]) < 2 or not [x for x in scoped if isinstance(x, dict)]):
        time.sleep(0.1)
    [s.set() for s in stops]
    with factory() as db:                                                                                  # one more, to unblock the readers
        raise_one(db, "end", company_id=None, severity="urgent")
        db.commit()
    [t.join(timeout=12) for t in ts]
    assert ("status", 200) in group and sorted(x["company_id"] or 0 for x in group if isinstance(x, dict))[:2] == [0, 1]
    assert [x["company_id"] for x in scoped if isinstance(x, dict)][:1] == [1]                           # scoped: only their company
    assert not any(isinstance(x, dict) and x["company_id"] is None for x in scoped if isinstance(x, dict) and x["id"] != 3)
    assert denied[0][1] in (401, 403)                                                                     # no token, no stream
