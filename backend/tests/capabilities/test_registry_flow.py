import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import Role, make_token
from app.db.models import Alert, Capability, IngestionRun, KpiRecord
from app.db.session import get_db
from app.main import app
from tests.capabilities.conftest import MCP_URL, SPEC, make_server

P = "2026-10"


def h(user, role, companies=None):
    return {"Authorization": f"Bearer {make_token(user, role, companies)}"}


ALICE, BOB, EDITOR = h("alice", Role.ADMIN), h("bob", Role.ADMIN), h("erin", Role.EDITOR)


@pytest.fixture()
def db(client):
    d = next(app.dependency_overrides[get_db]())
    yield d
    d.close()


def mkconn(client, name="HR MCP", type_="mcp", config=None, headers=ALICE):
    cfg = {"url": MCP_URL} if config is None and type_ == "mcp" else (config or {})
    return client.post("/connections", json={"name": name, "type": type_, "config": cfg}, headers=headers)


def discover(client, cid):
    return client.post(f"/connections/{cid}/discover", headers=ALICE)


def caps(client):
    return {c["name"]: c for c in client.get("/capabilities", headers=ALICE).json()}


def validate(client, cap_id, args=None):
    return client.post(f"/capabilities/{cap_id}/validate", json={"sample_args": args}, headers=ALICE).json()


SAMPLE = {"company_code": "IC1", "period": P}


def approve_action(client, action, args):
    r = client.post("/approvals", json={"action": action, "args": args}, headers=ALICE)
    if r.status_code != 201 or r.json()["verdict"] != "require_approval":
        return r
    aid = r.json()["approval"]["id"]
    return client.post(f"/approvals/{aid}/decision", json={"decision": "approve"}, headers=BOB)


def publish(client, cap_id, version=None):
    args = {"capability_id": cap_id, **({"version": version} if version else {})}
    return approve_action(client, "publish_capability", args)


@pytest.fixture()
def live(client, mcp_server):
    """An MCP connection with kra_stats validated and published."""
    cid = mkconn(client).json()["id"]
    discover(client, cid)
    kra = caps(client)["kra_stats"]
    assert validate(client, kra["id"], SAMPLE)["validation"]["ok"]
    assert publish(client, kra["id"]).json()["status"] == "executed"
    return {"cid": cid, "kra": kra["id"]}


# --- discovery, versions, sync ---

def test_discovery_creates_draft_capabilities_with_stable_ids_and_cautious_risk(client, mcp_server):
    conn = mkconn(client, name="HR MCP").json()
    assert conn["slug"] == "hr-mcp" and conn["capability_count"] == 0
    r = discover(client, conn["id"]).json()
    assert sorted(r["added"]) == ["hr-mcp.kra_stats", "hr-mcp.notify_leads"] and r["changed"] == r["removed"] == []
    c = caps(client)
    assert c["kra_stats"]["key"] == "hr-mcp.kra_stats" and c["kra_stats"]["risk"] == "read"
    assert c["notify_leads"]["risk"] == "destructive"                      # untagged tools are treated as dangerous
    assert {x["lifecycle"] for x in c.values()} == {"draft"} and c["kra_stats"]["version"] == 1
    assert c["kra_stats"]["permissions"] == ["admin"]
    assert client.get("/connections", headers=ALICE).json()[0]["capability_count"] == 2


def test_rediscovery_is_stable_and_a_wording_change_does_not_create_a_version(client, mcp_server):
    cid = mkconn(client).json()["id"]
    discover(client, cid)
    again = discover(client, cid).json()
    assert again["added"] == again["changed"] == again["removed"] == [] and len(again["unchanged"]) == 2
    mcp_server["server"] = make_server(1, wording="Counts of KRAs submitted.")
    r = discover(client, cid).json()
    assert r["changed"] == []
    detail = client.get(f"/capabilities/{caps(client)['kra_stats']['id']}", headers=ALICE).json()
    assert detail["description"] == "Counts of KRAs submitted." and detail["version"] == 1 and len(detail["versions"]) == 1


def test_upstream_change_bumps_the_version_but_production_keeps_running_the_published_one(client, mcp_server, live, db):
    mcp_server["server"] = make_server(2)
    r = discover(client, live["cid"]).json()
    assert r["changed"] == ["hr-mcp.kra_stats"] and r["removed"] == ["hr-mcp.notify_leads"]
    assert r["added"] == ["hr-mcp.mid_term_stats"]
    k = client.get(f"/capabilities/{live['kra']}", headers=ALICE).json()
    assert k["version"] == 2 and k["published_version"] == 1 and k["lifecycle"] == "update_pending"
    assert [(v["version"], v["published"]) for v in k["versions"]] == [(2, False), (1, True)]
    assert "include_contractors" in k["input_schema"]["properties"]
    assert caps(client)["notify_leads"]["lifecycle"] == "removed"
    assert {i["capability"] for i in r["impacts"]} == {"hr-mcp.kra_stats"}      # the published one is flagged
    assert [a.kind for a in db.scalars(select(Alert))] == ["capability_changed"]


def test_risk_override_is_a_new_version_survives_rediscovery_and_needs_a_reason(client, mcp_server):
    cid = mkconn(client).json()["id"]
    discover(client, cid)
    nid = caps(client)["notify_leads"]["id"]
    assert client.post(f"/capabilities/{nid}/risk", json={"risk": "read", "reason": ""}, headers=ALICE).status_code == 422
    assert client.post(f"/capabilities/{nid}/risk", json={"risk": "bogus", "reason": "x"}, headers=ALICE).status_code == 422
    r = client.post(f"/capabilities/{nid}/risk", json={"risk": "internal_write", "reason": "only writes our own notes"},
                    headers=ALICE).json()
    assert r["risk"] == "internal_write" and r["risk_overridden"] and r["version"] == 2 and r["lifecycle"] == "draft"
    again = discover(client, cid).json()                                       # upstream unchanged
    after = caps(client)["notify_leads"]
    assert "hr-mcp.notify_leads" in again["unchanged"] and after["risk"] == "internal_write" and after["version"] == 2


# --- validation and publishing ---

def test_validation_runs_checks_and_only_a_passing_version_is_marked_validated(client, mcp_server):
    cid = mkconn(client).json()["id"]
    discover(client, cid)
    kid = caps(client)["kra_stats"]["id"]
    v = validate(client, kid, SAMPLE)
    assert v["validation"]["ok"] and {c["name"] for c in v["validation"]["checks"]} == {
        "schema_is_valid", "implementation_is_resolvable", "connection_is_healthy", "sample_call"}
    assert v["capability"]["lifecycle"] == "validated" and v["capability"]["validated_version"] == 1
    bad = validate(client, kid, {"company_code": 5})                           # fails its own input schema
    assert not bad["validation"]["ok"] and next(c for c in bad["validation"]["checks"] if c["name"] == "sample_call")["ok"] is False
    nid = caps(client)["notify_leads"]["id"]
    skipped = validate(client, nid, {"message": "hi"})["validation"]["checks"][-1]
    assert skipped["skipped"] and "only read" in skipped["detail"]             # a write capability is never called


def test_validation_fails_when_the_connection_is_down_and_marks_it_unhealthy(client, mcp_server):
    cid = mkconn(client).json()["id"]
    discover(client, cid)
    kid = caps(client)["kra_stats"]["id"]
    mcp_server["down"] = True
    v = validate(client, kid, SAMPLE)
    assert not v["validation"]["ok"] and v["capability"]["validated_version"] is None
    conn = client.get("/connections", headers=ALICE).json()[0]
    assert conn["health_status"] == "unhealthy" and "ConnectionError" in conn["health_detail"]
    assert "simulated outage" not in str(conn)


def test_publishing_needs_validation_a_second_admin_and_shows_the_approver_what_they_approve(client, mcp_server):
    cid = mkconn(client).json()["id"]
    discover(client, cid)
    kid = caps(client)["kra_stats"]["id"]
    assert approve_action(client, "publish_capability", {"capability_id": kid}).status_code == 422   # not validated
    validate(client, kid, SAMPLE)
    prop = client.post("/approvals", json={"action": "publish_capability", "args": {"capability_id": kid}}, headers=ALICE).json()
    ctx = prop["approval"]["context"]
    assert ctx["capability"] == "hr-mcp.kra_stats" and ctx["risk"] == "read" and ctx["version"] == 1
    assert client.get(f"/capabilities/{kid}", headers=ALICE).json()["published_version"] is None      # not live yet
    aid = prop["approval"]["id"]
    assert client.post(f"/approvals/{aid}/decision", json={"decision": "approve"}, headers=ALICE).status_code == 403
    assert client.post(f"/approvals/{aid}/decision", json={"decision": "approve"}, headers=BOB).json()["status"] == "executed"
    k = client.get(f"/capabilities/{kid}", headers=ALICE).json()
    assert k["published_version"] == 1 and k["lifecycle"] == "published"
    assert publish(client, kid).status_code == 422                              # already published


def test_rollback_is_publishing_an_older_validated_version(client, mcp_server, live):
    mcp_server["server"] = make_server(2)
    discover(client, live["cid"])
    assert validate(client, live["kra"], SAMPLE)["validation"]["ok"]            # v2 validated
    assert publish(client, live["kra"]).json()["result"]["published_version"] == 2
    prop = client.post("/approvals", json={"action": "publish_capability", "args": {"capability_id": live["kra"], "version": 1}},
                       headers=ALICE).json()
    assert prop["approval"]["context"]["is_rollback"] is True
    client.post(f"/approvals/{prop['approval']['id']}/decision", json={"decision": "approve"}, headers=BOB)
    k = client.get(f"/capabilities/{live['kra']}", headers=ALICE).json()
    assert k["published_version"] == 1 and k["lifecycle"] == "update_pending"
    assert approve_action(client, "publish_capability", {"capability_id": live["kra"], "version": 9}).status_code == 422


def test_deprecated_capability_cannot_be_published_and_reports_its_dependents(client, mcp_server):
    cid = mkconn(client).json()["id"]
    discover(client, cid)
    kid = caps(client)["kra_stats"]["id"]
    validate(client, kid, SAMPLE)
    d = client.post(f"/capabilities/{kid}/deprecate", headers=ALICE).json()
    assert d["lifecycle"] == "deprecated" and d["kpis_using_it"] == []
    assert publish(client, kid).status_code == 422


def test_search_and_filters(client, mcp_server):
    discover(client, mkconn(client).json()["id"])
    s = lambda **p: [c["name"] for c in client.get("/capabilities", params=p, headers=ALICE).json()]
    assert s(q="kra") == ["kra_stats"] and s(q="MESSAGE") == ["notify_leads"]      # case-insensitive, searches text
    assert s(risk="read") == ["kra_stats"] and s(risk="destructive") == ["notify_leads"]
    assert sorted(s(lifecycle="draft")) == ["kra_stats", "notify_leads"] and s(lifecycle="published") == []


# --- KPI mappings ---

def test_recommendations_match_fields_fill_arguments_and_skip_unsuitable_tools(client, mcp_server, live):
    r = client.post("/kpi-mappings/recommend", headers=ALICE).json()
    by_kpi = {m["kpi_key"]: m for m in r["mappings"]}
    m = by_kpi["kra_submission"]
    assert m["capability_key"] == "hr-mcp.kra_stats"
    assert m["field_map"] == {"submitted": "submitted", "eligible": "eligible"}
    assert m["arg_template"] == {"company_code": "{company_code}", "period": "{period}"} and m["status"] == "recommended"
    assert m["score"] >= 0.35 and any("fields found" in x for x in m["reasons"])
    assert all(x["capability_id"] != caps(client)["notify_leads"]["id"] for x in r["mappings"])  # not a read tool
    assert not set(by_kpi) & {"cost_per_hire", "gptw_score", "idps_top_talent", "top_talent_review"}  # manual KPIs
    assert client.post("/kpi-mappings/recommend", headers=ALICE).json()["recommended"] == len(r["mappings"])  # idempotent
    assert len(client.get("/kpi-mappings", params={"status": "recommended"}, headers=ALICE).json()) == len(r["mappings"])


def test_approving_a_mapping_requires_a_published_read_capability_and_complete_fields(client, mcp_server):
    cid = mkconn(client).json()["id"]
    discover(client, cid)
    kid = caps(client)["kra_stats"]["id"]
    mid = next(m["id"] for m in client.post("/kpi-mappings/recommend", headers=ALICE).json()["mappings"]
               if m["kpi_key"] == "kra_submission")
    assert approve_action(client, "approve_kpi_mapping", {"mapping_id": mid}).status_code == 422   # not published
    validate(client, kid, SAMPLE)
    publish(client, kid)
    client.patch(f"/kpi-mappings/{mid}", json={"field_map": {"submitted": "submitted"}}, headers=ALICE)
    r = approve_action(client, "approve_kpi_mapping", {"mapping_id": mid})
    assert r.status_code == 422 and "eligible" in r.json()["detail"]                                # incomplete
    client.patch(f"/kpi-mappings/{mid}", json={"field_map": {"submitted": "submitted", "eligible": "eligible"},
                                              "arg_template": {"company_code": "{company_code}"}}, headers=ALICE)
    assert "period" in approve_action(client, "approve_kpi_mapping", {"mapping_id": mid}).json()["detail"]
    client.patch(f"/kpi-mappings/{mid}", json={"arg_template": {"company_code": "{company_code}", "period": "{period}"}},
                 headers=ALICE)
    ok = approve_action(client, "approve_kpi_mapping", {"mapping_id": mid}).json()
    assert ok["status"] == "executed" and ok["result"]["kpi"] == "kra_submission"
    assert client.patch(f"/kpi-mappings/{mid}", json={"field_map": {}}, headers=ALICE).status_code == 409   # now reviewed
    assert approve_action(client, "approve_kpi_mapping", {"mapping_id": mid}).status_code == 422             # not recommended


def test_a_non_read_capability_can_never_supply_kpi_data(client, mcp_server, db):
    cid = mkconn(client).json()["id"]
    discover(client, cid)
    kid = caps(client)["kra_stats"]["id"]
    validate(client, kid, SAMPLE)
    publish(client, kid)
    mid = next(m["id"] for m in client.post("/kpi-mappings/recommend", headers=ALICE).json()["mappings"] if m["kpi_key"] == "kra_submission")
    client.post(f"/capabilities/{kid}/risk", json={"risk": "internal_write", "reason": "demo"}, headers=ALICE)
    validate(client, kid, SAMPLE)
    assert publish(client, kid).json()["status"] == "executed"                 # a write tool may be published...
    r = approve_action(client, "approve_kpi_mapping", {"mapping_id": mid})
    assert r.status_code == 422 and "read" in r.json()["detail"]               # ...but not feed a score


def test_a_newer_approved_mapping_supersedes_the_old_one_and_rejection_works(client, mcp_server, live):
    ms = client.post("/kpi-mappings/recommend", headers=ALICE).json()["mappings"]
    m1 = next(m["id"] for m in ms if m["kpi_key"] == "kra_submission")
    assert approve_action(client, "approve_kpi_mapping", {"mapping_id": m1}).json()["status"] == "executed"
    assert client.post(f"/kpi-mappings/{m1}/reject", json={"reason": ""}, headers=ALICE).status_code == 422
    r = client.post(f"/kpi-mappings/{m1}/reject", json={"reason": "wrong source"}, headers=ALICE).json()
    assert r["status"] == "rejected"
    assert client.post(f"/kpi-mappings/{m1}/reject", json={"reason": "again"}, headers=ALICE).status_code == 409


# --- end to end: configure once, data flows, KPI stops being "no source" ---

def approved_kra(client, live):
    mid = next(m["id"] for m in client.post("/kpi-mappings/recommend", headers=ALICE).json()["mappings"]
               if m["kpi_key"] == "kra_submission")
    assert approve_action(client, "approve_kpi_mapping", {"mapping_id": mid}).json()["status"] == "executed"


def test_approved_mapping_feeds_ingestion_with_lineage_and_clears_no_source(client, mcp_server, live, db, monkeypatch):
    monkeypatch.setattr(settings, "stub_data_enabled", False)                    # nothing else supplies data
    before = client.get("/scorecard", params={"period": P}, headers=ALICE).json()
    assert "kra_submission" in before["no_source_kpis"] and len(before["no_source_kpis"]) == 19
    approved_kra(client, live)
    after = client.get("/scorecard", params={"period": P}, headers=ALICE).json()
    assert "kra_submission" not in after["no_source_kpis"] and len(after["no_source_kpis"]) == 18
    status = {s["source"]: s for s in client.get("/ingestion/status", headers=ALICE).json()}
    assert status["registry"]["mode"] == "registry" and status["registry"]["kpis"] == ["kra_submission"]
    assert "kra_submission" in status["successfactors"]["taken_over_by_registry"]

    run = client.post("/ingestion/run", json={"period": P, "sources": ["registry"]}, headers=ALICE).json()
    assert [(r["source"], r["status"], r["companies_ok"]) for r in run] == [("registry", "success", 3)]
    rec = db.scalar(select(KpiRecord).where(KpiRecord.kpi_key == "kra_submission", KpiRecord.period == P))
    assert (rec.source, rec.numerator, rec.denominator, rec.achievement) == ("registry", 90.0, 100.0, 90.0)
    assert rec.detail["mode"] == "registry" and rec.detail["capability"] == "hr-mcp.kra_stats"
    assert rec.detail["capability_version"] == 1 and rec.detail["raw"] == {"submitted": 90.0, "eligible": 100.0}
    sc = client.get("/scorecard", params={"period": P}, headers=ALICE).json()
    assert sc["synthetic_data"] is False                                          # registry data is real data
    assert db.scalar(select(IngestionRun.source).order_by(IngestionRun.id.desc()).limit(1)) == "registry"


def test_registry_takes_a_kpi_over_from_stub_data_without_double_writing(client, mcp_server, live, db):
    approved_kra(client, live)
    run = client.post("/ingestion/run", json={"period": P}, headers=ALICE).json()
    assert {r["source"] for r in run} == {"successfactors", "peoplestrong", "myhealth", "hi5plus", "registry"}
    rows = db.scalars(select(KpiRecord).where(KpiRecord.kpi_key == "kra_submission")).all()
    assert len(rows) == 3 and {r.source for r in rows} == {"registry"}            # one writer per KPI
    sf = next(r for r in run if r["source"] == "successfactors")
    assert sf["records_written"] == 3 * 13                                        # 14 KPIs minus the one taken over


def test_unpublishing_by_deprecation_or_removal_returns_the_kpi_to_its_old_source(client, mcp_server, live, db, monkeypatch):
    monkeypatch.setattr(settings, "stub_data_enabled", False)
    approved_kra(client, live)
    assert "kra_submission" not in client.get("/scorecard", params={"period": P}, headers=ALICE).json()["no_source_kpis"]
    d = client.post(f"/capabilities/{live['kra']}/deprecate", headers=ALICE).json()
    assert d["kpis_using_it"] == ["kra_submission"]                               # the impact is shown up front
    assert "kra_submission" in client.get("/scorecard", params={"period": P}, headers=ALICE).json()["no_source_kpis"]


def test_a_failing_capability_is_recorded_per_company_and_raises_an_alert(client, mcp_server, live, db):
    approved_kra(client, live)
    mcp_server["down"] = True
    run = client.post("/ingestion/run", json={"period": P, "sources": ["registry"]}, headers=ALICE).json()
    assert run[0]["status"] == "failed" and run[0]["companies_failed"] == 3
    assert {e["error"] for e in run[0]["errors"]} == {"InvocationError"}
    assert "simulated outage" not in str(run)
    assert "ingestion_failed" in {a.kind for a in db.scalars(select(Alert))}


# --- API surface: permissions, secrets, input checks ---

def test_everything_is_admin_and_group_wide_only(client, mcp_server):
    cid = mkconn(client).json()["id"]
    discover(client, cid)
    kid = caps(client)["kra_stats"]["id"]
    scoped = h("sam", Role.ADMIN, [1])
    reqs = [("get", "/connections", None), ("post", "/connections", {"name": "x", "type": "function", "config": {}}),
            ("post", f"/connections/{cid}/discover", None), ("post", f"/connections/{cid}/health", None),
            ("get", "/capabilities", None), ("get", f"/capabilities/{kid}", None),
            ("post", f"/capabilities/{kid}/validate", {}), ("post", f"/capabilities/{kid}/test", {"args": {}}),
            ("post", f"/capabilities/{kid}/risk", {"risk": "read", "reason": "x"}),
            ("post", f"/capabilities/{kid}/deprecate", None), ("get", "/kpi-mappings", None),
            ("post", "/kpi-mappings/recommend", None)]
    for who in (EDITOR, h("vic", Role.VIEWER), scoped):
        for method, url, body in reqs:
            r = getattr(client, method)(url, headers=who, **({"json": body} if body is not None else {}))
            assert r.status_code == 403, (who, method, url)
    assert client.get("/connections").status_code in (401, 403)


def test_secrets_are_referenced_by_name_and_never_stored_or_returned(client, mcp_server, db):
    r = mkconn(client, config={"url": MCP_URL, "auth": {"type": "bearer", "token_env": "HR_MCP_TOKEN", "token": "s3cret-value"}})
    assert r.status_code == 201 and r.json()["config"]["auth"] == {"type": "bearer", "token_env": "HR_MCP_TOKEN"}
    from app.db.models import Connection
    assert "s3cret-value" not in str(db.scalars(select(Connection.config)).all())
    assert "s3cret-value" not in client.get("/connections", headers=ALICE).text
    discover_resp = discover(client, r.json()["id"])                              # env var not set: a clear error, no value
    assert discover_resp.status_code == 422 and "HR_MCP_TOKEN" in discover_resp.json()["detail"]


def test_bad_connections_are_refused_with_clear_messages(client, mcp_server):
    assert mkconn(client, config={"url": "http://169.254.169.254/mcp"}).status_code == 422
    assert mkconn(client, config={"url": "ftp://localhost/x"}).status_code == 422
    assert mkconn(client, config={}).status_code == 422                            # mcp needs a url
    assert mkconn(client, name="Bad", type_="api", config={}).status_code == 422   # api needs a spec
    assert mkconn(client, name="Bad2", type_="grpc", config={}).status_code == 422
    assert mkconn(client).status_code == 201 and mkconn(client).status_code == 422  # duplicate name
    assert client.post("/connections/999/discover", headers=ALICE).status_code == 404


def test_discovery_failure_is_a_502_without_upstream_detail(client, mcp_server):
    cid = mkconn(client).json()["id"]
    mcp_server["down"] = True
    r = discover(client, cid)
    assert r.status_code == 502 and "simulated outage" not in r.text and "DiscoveryError" not in r.text
    client.patch(f"/connections/{cid}", json={"active": False}, headers=ALICE)
    mcp_server["down"] = False
    assert discover(client, cid).status_code == 409                                # inactive connections are not polled


def test_openapi_connection_and_function_connection_end_to_end(client, db):
    api = mkconn(client, name="People API", type_="api", config={"spec": SPEC}).json()
    assert api["config"]["server_url"] == "http://localhost:8099/v1" and api["config"]["spec"].startswith("<OpenAPI")
    assert sorted(discover(client, api["id"]).json()["added"]) == ["people-api.addNote", "people-api.delete_notes_id",
                                                                    "people-api.getPli"]
    pli = caps(client)["getPli"]
    assert pli["risk"] == "read" and pli["implementation"]["type"] == "http"
    fn = mkconn(client, name="Platform", type_="function", config={}).json()
    assert sorted(discover(client, fn["id"]).json()["added"]) == ["platform.group_score", "platform.list_companies"]
    gs = caps(client)["group_score"]
    assert validate(client, gs["id"], {"period": P})["validation"]["ok"]           # output validated against its schema
    t = client.post(f"/capabilities/{gs['id']}/test", json={"args": {"period": P}}, headers=ALICE).json()
    assert t["output"]["companies_in_scope"] == 3
    assert client.post(f"/capabilities/{gs['id']}/test", json={"args": {"period": "nope"}}, headers=ALICE).status_code == 422
    assert client.post(f"/capabilities/{caps(client)['addNote']['id']}/test", json={"args": {"body": {"text": "x"}}},
                       headers=ALICE).status_code == 403                           # a write is never test-called
    assert db.scalar(select(Capability.id).where(Capability.key == "people-api.getPli")) is not None


def test_upstream_change_to_a_capability_feeding_a_kpi_names_the_kpi_and_production_keeps_running_v1(
        client, mcp_server, live, db, monkeypatch):
    monkeypatch.setattr(settings, "stub_data_enabled", False)
    approved_kra(client, live)
    mcp_server["server"] = make_server(2)                                       # kra_stats gains a parameter
    r = discover(client, live["cid"]).json()
    impact = next(i for i in r["impacts"] if i["capability"] == "hr-mcp.kra_stats")
    assert impact["kpis"] == ["kra_submission"] and "changed upstream" in impact["change"]
    alert = next(a for a in db.scalars(select(Alert)) if a.kind == "capability_changed")
    assert "kra_submission" in alert.title and alert.severity == "medium"       # a dependent raises severity
    # v2 is not live: the KPI is still fed by the published v1 and the run succeeds
    run = client.post("/ingestion/run", json={"period": P, "sources": ["registry"]}, headers=ALICE).json()
    assert run[0]["status"] == "success"
    rec = db.scalar(select(KpiRecord).where(KpiRecord.kpi_key == "kra_submission"))
    assert rec.detail["capability_version"] == 1
    assert "kra_submission" not in client.get("/scorecard", params={"period": P}, headers=ALICE).json()["no_source_kpis"]


def test_a_capability_removed_upstream_stops_feeding_its_kpi(client, mcp_server, live, monkeypatch):
    monkeypatch.setattr(settings, "stub_data_enabled", False)
    approved_kra(client, live)
    mcp_server["server"] = _server_without(["kra_stats"])
    r = discover(client, live["cid"]).json()
    assert "hr-mcp.kra_stats" in r["removed"]
    assert next(i for i in r["impacts"] if i["capability"] == "hr-mcp.kra_stats")["kpis"] == ["kra_submission"]
    assert client.get(f"/capabilities/{live['kra']}", headers=ALICE).json()["lifecycle"] == "removed"
    assert "kra_submission" in client.get("/scorecard", params={"period": P}, headers=ALICE).json()["no_source_kpis"]


def _server_without(names):
    """An MCP server offering only a harmless tool, so the named ones vanish upstream."""
    from mcp.server import MCPServer
    from mcp.types import ToolAnnotations
    srv = MCPServer("hr")

    @srv.tool(name="ping", description="Liveness check.", annotations=ToolAnnotations(read_only_hint=True))
    def ping() -> dict:
        return {"ok": True}
    return srv
