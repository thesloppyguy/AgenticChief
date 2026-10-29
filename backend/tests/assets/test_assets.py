import json

import pytest
from sqlalchemy import select

from app.api.copilot import get_anthropic
from app.assets import builtin, service
from app.assets.service import AssetError
from app.core.config import settings
from app.core.security import Principal, Role, make_token
from app.db.models import Asset, ChatMessage, ChatSession
from app.db.session import get_db
from app.main import app
from tests.api.conftest import client  # noqa: F401
from tests.assets.fakes import ScriptedClient

P = "2026-10"


def h(user, role=Role.ADMIN, companies=None):
    return {"Authorization": f"Bearer {make_token(user, role, companies)}"}


ALICE, BOB, EDITOR, VIEWER = h("alice"), h("bob"), h("erin", Role.EDITOR), h("vic", Role.VIEWER, [1])


@pytest.fixture()
def db(client):
    d = next(app.dependency_overrides[get_db]())
    yield d
    d.close()


SKILL = {
    "instructions": "Report the group score for {period} and mention the coverage. Note: {note}",
    "inputs": {"type": "object", "properties": {"period": {"type": "string"}, "note": {"type": "string", "default": "none"}},
               "required": ["period"]},
    "tools": ["get_group_score", "rank_ics"],
}


def mk(client, kind="skill", key="score_brief", definition=None, headers=EDITOR, name="Score brief"):
    return client.post(f"/{kind}s", json={"key": key, "name": name, "definition": definition or SKILL}, headers=headers)


def validate(client, key="score_brief", kind="skill"):
    return client.post(f"/{kind}s/{key}/validate", headers=EDITOR).json()


def publish(client, asset_id, version=None):
    args = {"asset_id": asset_id, **({"version": version} if version else {})}
    r = client.post("/approvals", json={"action": "publish_asset", "args": args}, headers=ALICE)
    if r.status_code != 201:
        return r
    return client.post(f"/approvals/{r.json()['approval']['id']}/decision", json={"decision": "approve"}, headers=BOB)


def live(client, kind="skill", key="score_brief", definition=None):
    aid = mk(client, kind, key, definition).json()["id"]
    assert validate(client, key, kind)["validation"]["ok"]
    assert publish(client, aid).json()["status"] == "executed"
    return aid


# --- authoring and validation ---

def test_authoring_is_for_group_wide_editors_and_admins(client):
    assert mk(client, headers=VIEWER).status_code == 403
    assert mk(client, headers=h("sam", Role.EDITOR, [1])).status_code == 403
    r = mk(client)
    assert r.status_code == 201 and r.json()["lifecycle"] == "draft" and r.json()["version"] == 1
    assert mk(client).status_code == 409                                         # duplicate key
    assert mk(client, key="Bad Key").status_code == 422
    assert mk(client, key="short", definition={**SKILL, "instructions": "too short"}).status_code == 422
    assert mk(client, key="r", definition={**SKILL, "permissions": ["root"]}).status_code == 422


def test_static_validation_catches_each_mistake_with_a_reason(client):
    def checks(definition, key):
        mk(client, key=key, definition=definition)
        v = validate(client, key)["validation"]
        return v["ok"], {c["name"]: c for c in v["checks"] if not c["ok"]}

    assert checks(SKILL, "ok_skill")[0]
    assert "unknown tools: shell" in checks({**SKILL, "tools": ["get_group_score", "shell"]}, "bad_tool")[1]["tools_exist"]["detail"]
    assert "has_tools" in checks({**SKILL, "tools": []}, "no_tools")[1]
    bad = checks({**SKILL, "instructions": "Report for {period} using {secret_param} please do so"}, "bad_ph")[1]
    assert "{secret_param}" in bad["placeholders_match_inputs"]["detail"]
    nested = {**SKILL, "inputs": {"type": "object", "properties": {"period": {"type": "object"}}, "required": []}}
    assert "inputs_are_flat" in checks(nested, "nested")[1]
    badeval = {**SKILL, "eval_cases": [{"name": "c1", "inputs": {}, "must_call": ["get_group_score"]}]}   # period is required
    assert "eval_case_inputs:c1" in checks(badeval, "bad_eval")[1]
    unk = {**SKILL, "eval_cases": [{"name": "c2", "inputs": {"period": P}, "must_call": ["nope"]}]}
    assert "eval_case_tools:c2" in checks(unk, "bad_eval2")[1]


def test_lifecycle_versions_and_the_no_op_edit(client):
    aid = mk(client).json()["id"]
    assert validate(client)["lifecycle"] == "validated"
    d = client.get("/skills/score_brief", headers=EDITOR).json()
    assert d["definition"]["tools"] == ["get_group_score", "rank_ics"]
    assert client.post("/skills/score_brief/versions", json={"definition": SKILL}, headers=EDITOR).status_code == 422   # identical
    v2 = client.post("/skills/score_brief/versions", json={"definition": {**SKILL, "tools": ["get_group_score"]}}, headers=EDITOR).json()
    assert v2["version"] == 2 and v2["lifecycle"] == "draft"                       # an edit needs validating again
    assert publish(client, aid).status_code == 422                                 # v2 not validated
    validate(client)
    assert publish(client, aid).json()["status"] == "executed"
    assert client.get("/skills/score_brief", headers=EDITOR).json()["lifecycle"] == "published"
    client.post("/skills/score_brief/versions", json={"definition": {**SKILL, "tools": ["rank_ics"]}}, headers=EDITOR)
    assert client.get("/skills/score_brief", headers=EDITOR).json()["lifecycle"] == "update_pending"   # v2 still serves users


def test_publishing_needs_a_second_admin_and_shows_what_will_go_live(client):
    aid = mk(client).json()["id"]
    validate(client)
    prop = client.post("/approvals", json={"action": "publish_asset", "args": {"asset_id": aid}}, headers=ALICE).json()
    ctx = prop["approval"]["context"]
    assert ctx["key"] == "score_brief" and ctx["tools"] == ["get_group_score", "rank_ics"] and ctx["evals"] == "none defined"
    assert "Report the group score" in ctx["instructions"] and ctx["who_can_use_it"] == ["admin", "editor", "viewer"]
    aid2 = prop["approval"]["id"]
    assert client.post(f"/approvals/{aid2}/decision", json={"decision": "approve"}, headers=ALICE).status_code == 403
    assert client.post(f"/approvals/{aid2}/decision", json={"decision": "approve"}, headers=BOB).json()["status"] == "executed"
    assert publish(client, aid).status_code == 422                                 # already published
    assert publish(client, 999).status_code == 422


def test_a_skill_with_eval_cases_cannot_be_published_until_they_pass(client):
    cases = [{"name": "basic", "inputs": {"period": P}, "must_call": ["get_group_score"], "must_mention": ["unscored"]}]
    aid = mk(client, definition={**SKILL, "eval_cases": cases}).json()["id"]
    validate(client)
    r = publish(client, aid)
    assert r.status_code == 422 and "evals" in r.json()["detail"]


# --- visibility and roles ---

def test_unpublished_work_is_invisible_to_people_who_cannot_author_it(client):
    mk(client)
    assert client.get("/skills", headers=VIEWER).json() == []
    assert client.get("/skills/score_brief", headers=VIEWER).status_code == 404
    assert [s["key"] for s in client.get("/skills", headers=EDITOR).json()] == ["score_brief"]
    live_key = "live_skill"
    aid = mk(client, key=live_key, name="Live").json()["id"]
    validate(client, live_key)
    publish(client, aid)
    assert [s["key"] for s in client.get("/skills", headers=VIEWER).json()] == ["live_skill"]
    pub = client.get("/skills/live_skill", headers=VIEWER).json()
    assert pub["published_version"] == 1 and "definition" not in pub               # users see the contract, not the draft


def test_a_role_list_hides_a_skill_from_everyone_else(client):
    live(client, key="admin_only", definition={**SKILL, "permissions": ["admin"]})
    assert client.get("/skills", headers=VIEWER).json() == [] and client.get("/skills", headers=EDITOR).json() != []
    app.dependency_overrides[get_anthropic] = lambda: ScriptedClient(("text", "ok"))
    r = client.post("/copilot/chat", json={"skill_key": "admin_only", "skill_inputs": {"period": P}}, headers=VIEWER)
    assert r.status_code == 403


# --- running a skill or an agent through the Copilot ---

def events(r):
    return [json.loads(line[5:]) for line in r.text.splitlines() if line.startswith("data:")]


def run(client, fake, headers=VIEWER, **body):
    app.dependency_overrides[get_anthropic] = lambda: fake
    return client.post("/copilot/chat", json={"period": P, **body}, headers=headers)


def test_a_skill_run_sends_its_instructions_a_restricted_sorted_tool_list_and_cached_blocks(client):
    live(client)
    fake = ScriptedClient(("text", "Done."))
    r = run(client, fake, skill_key="score_brief", skill_inputs={"period": P, "note": "board pack"})
    assert [e["type"] for e in events(r)] == ["chunk", "done"]
    call = fake.calls[0]
    persona, skill = call["system"]
    from app.copilot.prompts import COPILOT_PERSONA
    assert persona["text"] == COPILOT_PERSONA and persona["cache_control"] == {"type": "ephemeral"}   # the fixed prefix is untouched
    assert f"Report the group score for {P}" in skill["text"] and "board pack" in skill["text"] and skill["cache_control"]
    assert [t["name"] for t in call["tools"]] == ["get_group_score", "rank_ics"]                  # only its tools, sorted
    assert call["tools"][-1]["cache_control"] and "cache_control" not in call["tools"][0]
    assert call["model"] == settings.default_model
    sid = events(r)[-1]["session_id"]
    sess = client.get(f"/copilot/sessions/{sid}", headers=VIEWER).json()
    assert sess["title"] == "Score brief" and sess["messages"][0]["content"] == 'Run the "Score brief" skill.'


def test_inputs_are_validated_defaults_applied_and_braces_in_values_stay_literal(client):
    live(client)
    fake = ScriptedClient(("text", "ok"))
    run(client, fake, skill_key="score_brief", skill_inputs={"period": P})
    assert "Note: none" in fake.calls[0]["system"][1]["text"]                                      # the default
    fake = ScriptedClient(("text", "ok"))
    run(client, fake, skill_key="score_brief", skill_inputs={"period": P, "note": "{period} {0.__class__} {__import__}"})
    assert "Note: {period} {0.__class__} {__import__}" in fake.calls[0]["system"][1]["text"]      # never re-expanded
    for bad, why in [({}, "period"), ({"period": 5}, "period"), ({"period": P, "color": "red"}, "unknown input")]:
        r = run(client, ScriptedClient(("text", "x")), skill_key="score_brief", skill_inputs=bad)
        assert r.status_code == 422 and why in r.json()["detail"]


def test_which_skill_or_agent_you_may_run(client):
    live(client)
    mk(client, key="draft_only", name="Draft")
    ok = ScriptedClient(("text", "x"))
    assert run(client, ok, skill_key="nope", skill_inputs={}).status_code == 404
    assert run(client, ok, skill_key="draft_only", skill_inputs={"period": P}).status_code == 404            # a viewer cannot see drafts exist
    assert run(client, ok, headers=ALICE, skill_key="draft_only", skill_inputs={"period": P}).status_code == 409
    assert run(client, ScriptedClient(("text", "x")), headers=ALICE, skill_key="draft_only", skill_inputs={"period": P},
               allow_draft=True).status_code == 200                                                          # an admin may try a draft
    assert run(client, ok, headers=VIEWER, skill_key="draft_only", skill_inputs={"period": P}, allow_draft=True).status_code == 404
    assert run(client, ok, skill_key="score_brief", agent_key="x", skill_inputs={"period": P}).status_code == 422
    assert run(client, ok, message="").status_code == 422                                                    # nothing to say or run


def test_a_model_cannot_call_a_tool_the_skill_was_not_given(client):
    live(client, definition={**SKILL, "tools": ["get_group_score"]})
    fake = ScriptedClient(("tool", "rank_ics", {"limit": 3}), ("text", "done"))
    run(client, fake, skill_key="score_brief", skill_inputs={"period": P})
    result = json.loads(fake.calls[1]["messages"][-1]["content"][0]["content"])
    assert result == {"error": "that tool is not available here"}


def test_agents_apply_their_model_tools_and_instructions(client):
    agent = {"instructions": "Answer as a terse analyst. Lead with the number.", "tools": ["get_group_score"], "model": "deep"}
    live(client, kind="agent", key="terse", definition=agent)
    fake = ScriptedClient(("text", "82.3"))
    r = run(client, fake, message="how are we doing?", agent_key="terse")
    assert r.status_code == 200
    call = fake.calls[0]
    assert call["model"] == settings.deep_reasoning_model and [t["name"] for t in call["tools"]] == ["get_group_score"]
    assert 'acting as the specialist "Score brief"' in call["system"][1]["text"] and "terse analyst" in call["system"][1]["text"]
    assert call["messages"][-1]["content"].endswith("how are we doing?")                                       # the user's own words


def test_ordinary_chat_is_unchanged_by_skills(client):
    fake = ScriptedClient(("text", "hi"))
    run(client, fake, message="hello")
    call = fake.calls[0]
    assert len(call["system"]) == 1 and len(call["tools"]) >= 8 and call["model"] == settings.default_model


# --- the built-in skills and agent ---

def test_builtin_assets_are_published_valid_idempotent_and_read_only(client, db):
    assert builtin.seed_builtin(db) == 5 and builtin.seed_builtin(db) == 0
    assert {a.key for a in db.scalars(select(Asset).where(Asset.builtin.is_(True)))} == {
        "missing_submissions", "compare_companies", "pillar_investigation", "monthly_review_brief", "hr_analyst"}
    assert all(a.lifecycle == "published" and a.validated_version == 1 for a in db.scalars(select(Asset)))
    assert {s["key"] for s in client.get("/skills", headers=VIEWER).json()} == {
        "missing_submissions", "compare_companies", "pillar_investigation", "monthly_review_brief"}
    assert [a["key"] for a in client.get("/agents", headers=VIEWER).json()] == ["hr_analyst"]
    assert client.post("/skills/compare_companies/versions", json={"definition": SKILL}, headers=EDITOR).status_code == 403
    assert client.post("/skills/compare_companies/deprecate", headers=ALICE).status_code == 403
    for a in db.scalars(select(Asset)):
        assert "propose_action" not in service.MODELS[a.kind](**service.latest(db, a).definition).tools   # built-ins never file requests


def test_a_builtin_skill_runs_with_its_inputs(client, db):
    builtin.seed_builtin(db)
    fake = ScriptedClient(("text", "ranked"))
    r = run(client, fake, skill_key="compare_companies", skill_inputs={"period": P})
    assert r.status_code == 200
    text = fake.calls[0]["system"][1]["text"]
    assert f"Compare the lowest 10 companies for {P}" in text                                  # defaults filled in
    assert [t["name"] for t in fake.calls[0]["tools"]] == ["get_group_score", "get_ic_score", "rank_ics"]
    assert run(client, ScriptedClient(("text", "x")), skill_key="compare_companies",
               skill_inputs={"period": P, "order": "sideways"}).status_code == 422


# --- evals ---

def test_evals_run_the_cases_against_the_model_and_gate_publication(client):
    cases = [{"name": "uses the tool", "inputs": {"period": P}, "must_call": ["get_group_score"], "must_mention": ["unscored"]}]
    aid = mk(client, definition={**SKILL, "eval_cases": cases}).json()["id"]
    validate(client)
    good = ScriptedClient(("tool", "get_group_score", {"period": P}), ("text", "Group is unscored."))
    app.dependency_overrides[get_anthropic] = lambda: good
    res = client.post("/skills/score_brief/evals", headers=EDITOR).json()
    assert res["cases"] == [{"case": "uses the tool", "passed": True, "problems": []}]
    assert good.calls[0]["system"][1]["text"].count(P) >= 1                                    # the case's inputs were applied
    assert publish(client, aid).json()["status"] == "executed"                                 # now it may go live

    mk(client, key="strict", name="Strict", definition={**SKILL, "eval_cases": [
        {"name": "wrong", "inputs": {"period": P}, "must_call": ["rank_ics"], "must_mention": ["bananas"]}]})
    validate(client, "strict")
    app.dependency_overrides[get_anthropic] = lambda: ScriptedClient(("text", "Nothing useful."))
    bad = client.post("/skills/strict/evals", headers=EDITOR).json()
    assert not bad["cases"][0]["passed"] and set(bad["cases"][0]["problems"]) == {"did not call rank_ics", "answer does not mention 'bananas'"}
    sid = client.get("/skills/strict", headers=EDITOR).json()["id"]
    assert publish(client, sid).status_code == 422


def test_evals_need_a_configured_model_and_cases_and_an_author(client):
    mk(client)
    app.dependency_overrides.pop(get_anthropic, None)
    assert client.post("/skills/score_brief/evals", headers=EDITOR).status_code == 503
    app.dependency_overrides[get_anthropic] = lambda: ScriptedClient(("text", "x"))
    assert client.post("/skills/score_brief/evals", headers=EDITOR).status_code == 422                      # no cases
    assert client.post("/skills/score_brief/evals", headers=VIEWER).status_code == 403


def test_a_skill_can_be_pinned_by_key(client):
    live(client)
    r = client.post("/pins", json={"kind": "skill", "ref": "score_brief"}, headers=VIEWER)
    assert r.status_code == 201 and r.json()["label"] == "Score brief" and r.json()["href"] == "/skills/score_brief"


def test_resolve_refuses_deprecated_assets(client, db):
    aid = live(client)
    service.deprecate(db, Principal("alice", Role.ADMIN, None), db.get(Asset, aid))
    with pytest.raises(AssetError) as e:
        service.resolve(db, Principal("vic", Role.VIEWER, None), "skill", "score_brief", {"period": P})
    assert e.value.status == 409
    assert db.scalar(select(ChatSession.id)) is None and db.scalar(select(ChatMessage.id)) is None


def test_an_author_sees_the_drafts_inputs_and_tools_but_a_published_skill_still_shows_what_users_get(client):
    mk(client)
    d = client.get("/skills/score_brief", headers=EDITOR).json()
    assert d["published_version"] is None and d["tools"] == ["get_group_score", "rank_ics"]          # not an empty shell
    assert d["inputs"]["required"] == ["period"] and "period" in d["inputs"]["properties"]
    aid = d["id"]
    validate(client)
    publish(client, aid)
    client.post("/skills/score_brief/versions", json={"definition": {**SKILL, "tools": ["rank_ics"]}}, headers=EDITOR)
    shown = client.get("/skills/score_brief", headers=EDITOR).json()
    assert shown["tools"] == ["get_group_score", "rank_ics"] and shown["version"] == 2               # users still get v1's contract
    assert client.get("/skills/score_brief", headers=VIEWER).json()["tools"] == ["get_group_score", "rank_ics"]
