"""Workforce fixtures, APIs, tools, and governed directive actions."""
from __future__ import annotations

from sqlalchemy import select

from app.approvals import service as approvals
from app.core.security import Principal, Role, make_token
from app.db.models import JobSchedule, OutboundMessage, Person, Watch
from app.db.session import get_db
from app.main import app
from app.workforce import loader
from app.workforce import tools as workforce_tools
from tests.api.conftest import client  # noqa: F401


def h(user="admin", role=Role.ADMIN):
    return {"Authorization": f"Bearer {make_token(user, role)}"}


def test_workforce_yaml_loads_and_artifacts():
    loader.clear_cache()
    pulse = loader.pulse()
    assert pulse.get("cells") and len(pulse["cells"]) == 5
    skills = loader.skills()
    assert skills.get("domains") and skills["headline"]["capability_gap"] == 1300
    succ = loader.succession()
    assert succ["headline"]["weak_or_no_successor"] == 34
    drafts = loader.draft_actions()["drafts"]
    assert {d["key"] for d in drafts} >= {"capability_green_h2", "retention_semi"}
    art = loader.artifact_for("skills", skills)
    assert art and art["kind"] == "skills_demand_supply"


def test_workforce_http_endpoints(client):
    for path in ("/workforce/pulse", "/workforce/skills", "/workforce/succession", "/workforce/actions"):
        r = client.get(path, headers=h())
        assert r.status_code == 200, path
        body = r.json()
        assert "artifact" in body
    exp = client.get("/workforce/export/skills", headers=h())
    assert exp.status_code == 200
    assert "text/csv" in exp.headers.get("content-type", "")
    assert b"Demand" in exp.content or b"demand" in exp.content.lower() or b"Green" in exp.content


def test_workforce_tools_dispatch(client):
    db = next(app.dependency_overrides[get_db]())
    who = Principal("admin", Role.ADMIN, None)
    out = workforce_tools.dispatch("get_workforce_pulse", {}, db, who)
    assert out["artifact"]["kind"] == "kpi_bars"
    out = workforce_tools.dispatch("list_draft_actions", {"key": "capability_green_h2"}, db, who)
    assert len(out["drafts"]) == 1
    assert out["drafts"][0]["action"] == "launch_capability_program"


def test_send_directive_queues_to_named_people(client):
    db = next(app.dependency_overrides[get_db]())
    p = Person(
        full_name="Demo HR Lead",
        role="CHRO, Demo",
        email="demo.hr@example.com",
        company_code="IC1",
        department_slugs=["people"],
    )
    db.add(p)
    db.commit()
    db.refresh(p)

    requester = Principal("alice", Role.ADMIN, None)
    approver = Principal("bob", Role.ADMIN, None)
    res = approvals.submit(
        db,
        requester,
        "send_directive",
        {
            "subject": "Group direction: confirm retention actions",
            "body": "Please confirm the semi retention plan this week.",
            "channel": "email",
            "person_ids": [p.id],
            "company_codes": ["IC1"],
        },
        via="api",
        context={"reason": "test"},
    )
    assert res.verdict == "require_approval"
    aid = res.approval.id
    out = approvals.decide(db, approver, aid, "approve", None)
    assert out.status == "executed"
    assert out.result["queued"] == 1
    msg = db.scalar(select(OutboundMessage).where(OutboundMessage.approval_id == aid))
    assert msg is not None
    assert msg.person_id == p.id
    assert msg.to_email == "demo.hr@example.com"
    assert msg.subject.startswith("Group direction")


def test_schedule_report_creates_job(client):
    db = next(app.dependency_overrides[get_db]())
    requester = Principal("alice", Role.ADMIN, None)
    approver = Principal("bob", Role.ADMIN, None)
    res = approvals.submit(
        db,
        requester,
        "schedule_report",
        {
            "report_key": "workforce_brief",
            "name": "Test weekly workforce brief",
            "cadence": {"type": "weekly", "weekday": 0, "time": "07:00"},
            "period": "current",
        },
        via="api",
    )
    assert res.verdict == "require_approval"
    out = approvals.decide(db, approver, res.approval.id, "approve", None)
    assert out.status == "executed"
    sid = out.result["schedule_id"]
    s = db.get(JobSchedule, sid)
    assert s is not None and s.name == "Test weekly workforce brief"


def test_launch_retention_arms_watch(client):
    db = next(app.dependency_overrides[get_db]())
    p = Person(
        full_name="Demo IC CHRO",
        role="CHRO, IC1",
        email="chro.ic1@example.com",
        company_code="IC1",
        department_slugs=["people"],
    )
    db.add(p)
    db.commit()

    requester = Principal("alice", Role.ADMIN, None)
    approver = Principal("bob", Role.ADMIN, None)
    res = approvals.submit(
        db,
        requester,
        "launch_retention_corrective",
        {
            "program_key": "retention_test",
            "at_risk_count": 10,
            "company_code": "IC1",
            "company_codes": ["IC1"],
            "recipient_emails": ["chro.ic1@example.com"],
            "subject": "Retention corrective approved",
            "body": "Activate pathways for at-risk cohort.",
            "channel": "email",
        },
        via="api",
        context={"reason": "test retention"},
    )
    assert res.verdict == "require_approval", res.reason
    out = approvals.decide(db, approver, res.approval.id, "approve", None)
    assert out.status == "executed"
    assert out.result.get("watch_id")
    w = db.get(Watch, out.result["watch_id"])
    assert w is not None and "Retention" in w.name
    assert db.scalar(select(OutboundMessage).where(OutboundMessage.approval_id == res.approval.id))
