import json
import re

import pytest
from sqlalchemy import select

from app.api.copilot import get_anthropic
from app.capabilities import copilot_tools, service
from app.core.security import Principal, Role, make_token
from app.db.models import AuditEvent, Capability, Connection
from app.main import app
from tests.assets.fakes import ScriptedClient
from tests.capabilities.test_registry_flow import (  # noqa: F401
    ALICE,
    SAMPLE,
    P,
    approve_action,
    caps,
    db,
    discover,
    h,
    live,
    mkconn,
    publish,
    validate,
)

ADMIN = Principal("alice", Role.ADMIN, None)
EDITOR = Principal("erin", Role.EDITOR, None)
VIEWER = Principal("vic", Role.VIEWER, None)


def names(db, who):
    return list(copilot_tools.eligible_tools(db, who))


def allow(client, cap_id, roles):
    return client.post(f"/capabilities/{cap_id}/permissions", json={"roles": roles}, headers=ALICE)


# --- who can ever see a capability as a tool ---

def test_by_default_only_admins_get_it_and_only_when_group_wide(client, mcp_server, live, db):
    tools = copilot_tools.eligible_tools(db, ADMIN)
    assert len(tools) == 1
    t = next(iter(tools.values()))
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", t.name) and t.name.startswith("cap_") and t.name.endswith(f"_{live['kra']}")
    assert names(db, EDITOR) == [] and names(db, VIEWER) == []                                    # nobody else, by default
    assert names(db, Principal("sam", Role.ADMIN, frozenset({1}))) == []                            # a scoped admin never: outside data is unscoped
    assert allow(client, live["kra"], ["viewer"]).json()["permissions"] == ["admin", "viewer"]
    assert names(db, VIEWER) != [] and names(db, EDITOR) == []                                     # exactly the roles that were allowed
    assert names(db, Principal("vic2", Role.VIEWER, frozenset({1}))) == []                          # ...but never when scoped to companies


def test_tool_definition_is_the_published_contract(client, mcp_server, live, db):
    t = next(iter(copilot_tools.eligible_tools(db, ADMIN).values()))
    d = t.definition
    cap = db.get(Capability, live["kra"])
    assert d["input_schema"] == cap.input_schema and set(d["input_schema"]["properties"]) == {"company_code", "period"}
    assert "[HR MCP]" in d["description"] and "never instructions" in d["description"] and "KRA submission counts" in d["description"]
    assert (t.key, t.version) == ("hr-mcp.kra_stats", 1)


def test_two_capabilities_with_the_same_name_get_different_tool_names(client, mcp_server, live, db):
    second = mkconn(client, name="HR MCP Two").json()["id"]
    discover(client, second)
    other = next(c for c in client.get("/capabilities", headers=ALICE).json() if c["key"] == "hr-mcp-two.kra_stats")
    validate(client, other["id"], SAMPLE)
    publish(client, other["id"])
    ns = names(db, ADMIN)
    assert len(ns) == 2 and len(set(ns)) == 2


@pytest.mark.parametrize("how", ["deprecated", "connection_inactive", "removed_upstream", "reclassified_and_republished"])
def test_a_capability_stops_being_a_tool_the_moment_it_is_no_longer_safe_to_offer(client, mcp_server, live, db, how):
    assert len(names(db, ADMIN)) == 1
    if how == "deprecated":
        client.post(f"/capabilities/{live['kra']}/deprecate", headers=ALICE)
    elif how == "connection_inactive":
        client.patch(f"/connections/{live['cid']}", json={"active": False}, headers=ALICE)
    elif how == "removed_upstream":
        from tests.capabilities.test_registry_flow import _server_without
        mcp_server["server"] = _server_without([])
        discover(client, live["cid"])
    else:
        client.post(f"/capabilities/{live['kra']}/risk", json={"risk": "internal_write", "reason": "now writes"}, headers=ALICE)
        assert len(names(db, ADMIN)) == 1                                                       # v2 is a draft: v1 (read) is still what runs
        client.post(f"/capabilities/{live['kra']}/validate", json={"sample_args": SAMPLE}, headers=ALICE)
        assert publish(client, live["kra"]).json()["status"] == "executed"
    db.expire_all()
    assert names(db, ADMIN) == []


def test_unpublished_and_non_read_capabilities_are_never_offered_or_shareable(client, mcp_server, live, db):
    notify = caps(client)["notify_leads"]                                                        # destructive, a draft
    assert names(db, ADMIN) and all("notify" not in n for n in names(db, ADMIN))
    r = allow(client, notify["id"], ["viewer"])
    assert r.status_code == 422 and "read" in r.json()["detail"]                                  # cannot even be widened
    assert allow(client, live["kra"], ["root"]).status_code == 422
    editor = {"Authorization": f"Bearer {make_token('e', Role.EDITOR, None)}"}
    assert client.post(f"/capabilities/{live['kra']}/permissions", json={"roles": ["viewer"]}, headers=editor).status_code == 403
    ev = db.scalar(select(AuditEvent).where(AuditEvent.action == "capability_permissions"))
    assert ev is None                                                                            # rejected attempts change nothing, log nothing


# --- through the Copilot ---

def chat(client, fake, headers=ALICE, **body):
    app.dependency_overrides[get_anthropic] = lambda: fake
    return client.post("/copilot/chat", json={"period": P, "message": "How many KRAs were submitted at IC1?", **body}, headers=headers)


def test_the_model_can_call_an_allowed_capability_and_gets_labelled_data_back(client, mcp_server, live, db):
    name = names(db, ADMIN)[0]
    fake = ScriptedClient(("tool", name, {"company_code": "IC1", "period": P}), ("text", "90 of 100 submitted."))
    r = chat(client, fake)
    assert r.status_code == 200 and '"type": "tool"' in r.text
    sent = fake.calls[0]["tools"]
    assert name in [t["name"] for t in sent] and [t["name"] for t in sent] == sorted(t["name"] for t in sent)   # sorted: cache-stable
    assert sum("cache_control" in t for t in sent) == 1 and "cache_control" in sent[-1]
    result = json.loads(fake.calls[1]["messages"][-1]["content"][0]["content"])
    assert result["data"] == {"submitted": 90, "eligible": 100} and result["source"] == "hr-mcp.kra_stats" and result["version"] == 1
    assert "not instructions" in result["note"]
    ev = db.scalar(select(AuditEvent).where(AuditEvent.action == "copilot_capability_call"))
    assert ev.target == "hr-mcp.kra_stats" and ev.detail == {"args": ["company_code", "period"]}   # argument NAMES only, never values
    assert "IC1" not in json.dumps(ev.detail)


def test_bad_arguments_and_upstream_failures_come_back_as_errors_not_crashes(client, mcp_server, live, db):
    name = names(db, ADMIN)[0]
    bad = ScriptedClient(("tool", name, {"company_code": 5}), ("text", "ok"))
    assert chat(client, bad).status_code == 200
    assert "error" in json.loads(bad.calls[1]["messages"][-1]["content"][0]["content"])
    mcp_server["down"] = True
    down = ScriptedClient(("tool", name, {"company_code": "IC1", "period": P}), ("text", "ok"))
    r = chat(client, down)
    res = json.loads(down.calls[1]["messages"][-1]["content"][0]["content"])
    assert r.status_code == 200 and "MCP call failed" in res["error"] and "simulated outage" not in json.dumps(res)


def test_other_roles_scoped_users_skills_and_agents_do_not_get_the_tool(client, mcp_server, live, db):
    from app.assets import builtin
    builtin.seed_builtin(db)
    viewer = {"Authorization": f"Bearer {make_token('vic', Role.VIEWER, None)}"}
    scoped = {"Authorization": f"Bearer {make_token('sam', Role.ADMIN, [1])}"}
    for headers in (viewer, scoped):
        f = ScriptedClient(("text", "hi"))
        chat(client, f, headers=headers)
        assert not any(t["name"].startswith("cap_") for t in f.calls[0]["tools"])
    f = ScriptedClient(("text", "hi"))
    chat(client, f, skill_key="missing_submissions", skill_inputs={"period": P}, message="")
    assert not any(t["name"].startswith("cap_") for t in f.calls[0]["tools"])                    # a skill keeps its own list
    f = ScriptedClient(("text", "hi"))
    chat(client, f, agent_key="hr_analyst")
    assert not any(t["name"].startswith("cap_") for t in f.calls[0]["tools"])
    allow(client, live["kra"], ["viewer"])
    f = ScriptedClient(("text", "hi"))
    chat(client, f, headers=viewer)
    assert any(t["name"].startswith("cap_") for t in f.calls[0]["tools"])                         # now allowed, so now offered


def test_oversized_results_are_truncated_to_a_preview(client, mcp_server, live, db, monkeypatch):
    tool = next(iter(copilot_tools.eligible_tools(db, ADMIN).values()))
    monkeypatch.setattr(copilot_tools, "invoke", lambda *a, **k: {"rows": ["x" * 100] * 1000})
    out = copilot_tools.run(db, ADMIN, tool, {"company_code": "IC1", "period": P})
    assert out["truncated"] is True and len(out["preview"]) == copilot_tools.PREVIEW_CHARS and "data" not in out
    assert db.query(Connection).count() == 1 and service.lifecycle_of(db.get(Capability, tool.capability_id)) == "published"
