import pytest

from app.core.security import Role, make_token
from app.db.models import ApprovalRequest, ChatMessage, ChatSession
from app.db.session import get_db
from app.main import app
from tests.api.conftest import client  # noqa: F401


def h(user, role=Role.VIEWER, companies=None):
    return {"Authorization": f"Bearer {make_token(user, role, companies)}"}


ALICE, BOB = h("alice", Role.ADMIN), h("bob", Role.ADMIN)


@pytest.fixture()
def db(client):
    d = next(app.dependency_overrides[get_db]())
    yield d
    d.close()


def session(db, user, title, *texts):
    s = ChatSession(user_id=user, title=title)
    db.add(s)
    db.flush()
    for i, t in enumerate(texts):
        db.add(ChatMessage(session_id=s.id, role="user" if i % 2 == 0 else "assistant", content=t))
    db.commit()
    return s.id


# --- pins ---

def test_pin_list_unpin_and_idempotent(client, db):
    sid = session(db, "alice", "Pillar review", "hello")
    r = client.post("/pins", json={"kind": "session", "ref": str(sid)}, headers=ALICE)
    assert r.status_code == 201 and r.json()["label"] == "Pillar review" and r.json()["href"] == f"/copilot?session={sid}"
    again = client.post("/pins", json={"kind": "session", "ref": str(sid), "label": "ignored"}, headers=ALICE)
    assert again.json()["id"] == r.json()["id"]                                  # pinning twice is not an error
    assert [p["id"] for p in client.get("/pins", headers=ALICE).json()] == [r.json()["id"]]
    assert client.get("/pins", headers=BOB).json() == []                         # pins are personal
    assert client.delete(f"/pins/{r.json()['id']}", headers=BOB).status_code == 404
    assert client.delete(f"/pins/{r.json()['id']}", headers=ALICE).status_code == 204
    assert client.get("/pins", headers=ALICE).json() == []


def test_you_can_only_pin_what_you_can_open(client, db):
    other = session(db, "bob", "Private", "secret")
    assert client.post("/pins", json={"kind": "session", "ref": str(other)}, headers=ALICE).status_code == 404
    assert client.post("/pins", json={"kind": "session", "ref": "abc"}, headers=ALICE).status_code == 404
    assert client.post("/pins", json={"kind": "run", "ref": "1"}, headers=h("sam", Role.ADMIN, [1])).status_code == 403
    assert client.post("/pins", json={"kind": "snapshot", "ref": "999"}, headers=ALICE).status_code == 404
    assert client.post("/pins", json={"kind": "skill", "ref": "nope"}, headers=ALICE).status_code == 404
    assert client.post("/pins", json={"kind": "bogus", "ref": "1"}, headers=ALICE).status_code == 422


@pytest.mark.parametrize("ref", ["https://evil.example/x", "//evil.example", "/ok\nnewline", "javascript:alert(1)", "relative/path"])
def test_a_pinned_view_can_never_be_a_link_to_another_site(client, ref):
    assert client.post("/pins", json={"kind": "view", "ref": ref}, headers=ALICE).status_code == 422


def test_dashboard_views_can_be_pinned(client):
    r = client.post("/pins", json={"kind": "view", "ref": "/?period=2026-10&status=red&q=IC07", "label": "Red in October"}, headers=ALICE)
    assert r.status_code == 201 and r.json()["href"] == "/?period=2026-10&status=red&q=IC07" and r.json()["label"] == "Red in October"


# --- sessions ---

def test_sessions_are_searchable_by_title_and_by_what_was_said(client, db):
    a = session(db, "alice", "Retention deep dive", "Why did retention fall?", "Regrettable exits rose.")
    b = session(db, "alice", "Monthly review prep", "Prepare the review", "Done.")
    session(db, "bob", "Retention (bob's)", "bob only")
    ids = lambda q: [s["id"] for s in client.get("/copilot/sessions", params={"q": q}, headers=ALICE).json()["items"]]
    assert sorted(ids("")) == sorted([a, b])
    assert ids("retention") == [a]                                               # title and message text; never bob's
    assert ids("REGRETTABLE") == [a] and ids("prepare") == [b] and ids("nonsense") == []
    row = next(s for s in client.get("/copilot/sessions", headers=ALICE).json()["items"] if s["id"] == a)
    assert row["message_count"] == 2 and row["last_at"] is not None


def test_sessions_paginate_newest_first(client, db):
    ids = [session(db, "alice", f"S{i}", f"msg {i}") for i in range(5)]
    page = client.get("/copilot/sessions", params={"limit": 2}, headers=ALICE).json()
    assert [s["id"] for s in page["items"]] == [ids[4], ids[3]] and page["next_cursor"] == str(ids[3])
    page2 = client.get("/copilot/sessions", params={"limit": 2, "cursor": page["next_cursor"]}, headers=ALICE).json()
    assert [s["id"] for s in page2["items"]] == [ids[2], ids[1]] and page2["next_cursor"] == str(ids[1])
    last = client.get("/copilot/sessions", params={"limit": 2, "cursor": page2["next_cursor"]}, headers=ALICE).json()
    assert [s["id"] for s in last["items"]] == [ids[0]] and last["next_cursor"] is None


def test_session_detail_lists_the_approvals_filed_from_it_and_stays_private(client, db):
    sid = session(db, "alice", "Reminders", "Remind IC1", "Proposed.")
    db.add(ApprovalRequest(action="send_kpi_reminder", risk="external_message", summary="Remind 1 company",
                           args={}, requested_by="alice", via="copilot", session_id=sid, status="pending"))
    db.commit()
    d = client.get(f"/copilot/sessions/{sid}", headers=ALICE).json()
    assert d["title"] == "Reminders" and [m["role"] for m in d["messages"]] == ["user", "assistant"]
    assert d["approvals"] == [{"id": 1, "action": "send_kpi_reminder", "summary": "Remind 1 company", "status": "pending"}]
    assert client.get(f"/copilot/sessions/{sid}", headers=BOB).status_code == 404
