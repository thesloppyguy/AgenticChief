"""Prompt-authored workflows: the spec language, the compiler, the planner and the API.

All AI paths use ScriptedClient, so nothing here calls a real model.
"""
import json

import pytest
from sqlalchemy import select

from app.assets import builtin
from app.assets import service as asset_service
from app.core.security import Role, make_token
from app.db.models import ApprovalRequest, Asset, KpiRecord, WorkflowRun
from app.db.session import get_db
from app.kpi_registry.seed import KPIS
from app.main import app
from app.scheduler import jobs
from app.workflows import planner
from app.workflows.spec import WorkflowSpec
from tests.api.conftest import client  # noqa: F401
from tests.assets.fakes import ScriptedClient

P = "2026-10"


def h(user, role=Role.ADMIN, companies=None):
    return {"Authorization": f"Bearer {make_token(user, role, companies)}"}


ALICE, BOB, EDITOR = h("alice"), h("bob"), h("erin", Role.EDITOR)


@pytest.fixture()
def db(client):
    d = next(app.dependency_overrides[get_db]())
    yield d
    d.close()


def step(step_key, type_, label=None, **args):
    """`step_key`, not `key`: a skill or agent step has its own `key` argument."""
    return {"key": step_key, "label": label or step_key.replace("_", " "), "type": type_, "args": args}


SIMPLE = {"title": "Group snapshot",
          "steps": [step("card", "scorecard", scope="group", period="run")]}


def mk(client, key="snapshot", definition=None, headers=EDITOR):
    return client.post("/workflows/defs", headers=headers,
                       json={"key": key, "name": key, "definition": definition or SIMPLE})


def validate(client, key="snapshot", headers=EDITOR):
    return client.post(f"/workflows/defs/{key}/validate", headers=headers).json()


def publish(client, asset_id):
    r = client.post("/approvals", json={"action": "publish_asset", "args": {"asset_id": asset_id}}, headers=ALICE)
    assert r.status_code == 201, r.text
    return client.post(f"/approvals/{r.json()['approval']['id']}/decision",
                       json={"decision": "approve"}, headers=BOB)


def live(client, key="snapshot", definition=None):
    aid = mk(client, key, definition).json()["id"]
    assert validate(client, key)["validation"]["ok"], validate(client, key)
    assert publish(client, aid).json()["status"] == "executed"
    return aid


# --- the spec language ---------------------------------------------------------------------------

def test_a_forward_reference_is_rejected(client):
    bad = {"title": "t", "steps": [
        step("first", "summarize", inputs=["later"], instructions="Summarise {steps.later.text} please"),
        step("later", "scorecard", scope="group")]}
    mk(client, "fwd", bad)
    checks = {c["name"]: c for c in validate(client, "fwd")["validation"]["checks"]}
    assert checks["references_are_backwards"]["ok"] is False


def test_a_backward_reference_is_accepted(client):
    ok = {"title": "t", "steps": [
        step("card", "scorecard", scope="group"),
        step("note", "summarize", inputs=["card"], instructions="Summarise {steps.card.period} briefly")]}
    mk(client, "bwd", ok)
    assert validate(client, "bwd")["validation"]["ok"] is True


def test_an_unknown_tool_is_rejected(client):
    mk(client, "badtool", {"title": "t", "steps": [step("s", "tool", name="rm_rf", args={})]})
    checks = {c["name"]: c for c in validate(client, "badtool")["validation"]["checks"]}
    assert checks["workflow_tools_exist"]["ok"] is False


def test_a_workflow_cannot_delegate(client):
    mk(client, "deleg", {"title": "t", "steps": [step("s", "tool", name="delegate", args={})]})
    checks = {c["name"]: c for c in validate(client, "deleg")["validation"]["checks"]}
    assert checks["no_delegation_from_a_workflow"]["ok"] is False


def test_an_unknown_action_is_rejected(client):
    mk(client, "badact", {"title": "t", "steps": [step("s", "propose", action="delete_everything")]})
    checks = {c["name"]: c for c in validate(client, "badact")["validation"]["checks"]}
    assert checks["actions_exist"]["ok"] is False


def test_summarize_inputs_must_name_real_steps(client):
    mk(client, "badsum", {"title": "t", "steps": [
        step("s", "summarize", inputs=["nope"], instructions="Say something about it")]})
    checks = {c["name"]: c for c in validate(client, "badsum")["validation"]["checks"]}
    assert checks["summarize_inputs_exist"]["ok"] is False


def test_duplicate_step_keys_are_rejected(client):
    r = mk(client, "dupe", {"title": "t", "steps": [
        step("a", "scorecard", scope="group"), step("a", "scorecard", scope="group")]})
    assert r.status_code == 422 and "unique" in r.json()["detail"]


def test_a_plan_is_capped_at_twelve_steps(client):
    r = mk(client, "long", {"title": "t", "steps": [
        step(f"s{i}", "scorecard", scope="group") for i in range(13)]})
    assert r.status_code == 422


def test_the_uses_list_names_everything_the_plan_can_reach(client, db):
    builtin.seed_builtin(db)
    spec = WorkflowSpec(title="t", steps=[
        step("a", "tool", name="get_group_score"),
        step("b", "skill", key="missing_submissions", inputs={"period": P}),
        step("c", "agent", key="hr_analyst", message="hello there"),
        step("d", "propose", action="create_snapshot", args={"period": P})])
    assert spec.tools == ["agent:hr_analyst", "get_group_score", "propose_action", "skill:missing_submissions"]
    assert "1. a [tool]" in spec.instructions  # what the approver reads


def test_braces_in_a_value_cannot_reinterpret_the_template(client, db):
    """Substitution is a regex swap, never str.format, so a value can never reach attributes."""
    from app.workflows.compiler import resolve
    from app.workflows.engine import StepCtx

    ctx = StepCtx(db, WorkflowRun(workflow="x", period=P, status="running", requested_by="a", role="admin",
                                  state={"s": {"text": "{period} {0.__class__}"}}), None, {"s": {"text": "{period} {0.__class__}"}})
    assert resolve("{steps.s.text}", ctx) == "{period} {0.__class__}"  # returned raw, not re-expanded


def test_a_whole_string_reference_keeps_the_raw_value_and_a_mixed_one_interpolates(client, db):
    from app.workflows.compiler import resolve
    from app.workflows.engine import StepCtx

    state = {"card": {"group": {"score": 87.5}}}
    ctx = StepCtx(db, WorkflowRun(workflow="x", period=P, status="running", requested_by="a",
                                  role="admin", state=state), None, state)
    assert resolve("{steps.card.group}", ctx) == {"score": 87.5}        # raw dict
    assert resolve("score was {steps.card.group.score}", ctx) == "score was 87.5"
    assert resolve("{period}", ctx) == P


# --- the compiler and the engine -----------------------------------------------------------------

def fill(db, code_id=1):
    for k in KPIS:
        db.add(KpiRecord(company_id=code_id, kpi_key=k.key, period=P, achievement=k.target, source="t"))
    db.commit()


def test_a_compiled_spec_runs_through_the_unmodified_engine(client, db):
    fill(db)
    aid = live(client, "snapshot")
    r = client.post("/workflows/defs/snapshot/runs", json={"period": P}, headers=EDITOR)
    assert r.status_code == 202
    run = db.get(WorkflowRun, r.json()["id"])
    db.refresh(run)
    assert run.status == "succeeded" and run.workflow == "def:snapshot"
    assert run.params == {"asset_id": aid, "asset_version": 1}  # the version is pinned
    assert "card" in run.state and run.result["steps"]["card"]["period"] == P


def test_a_resumed_run_uses_the_version_pinned_in_params_not_a_newly_published_one(client, db):
    """Without pinning, republishing mid-run would swap the steps under a run that is resuming."""
    fill(db)
    aid = live(client, "pinned")
    r = client.post("/workflows/defs/pinned/runs", json={"period": P}, headers=EDITOR)
    run_id = r.json()["id"]

    # Publish a v2 with a differently-keyed step.
    v2 = {"title": "v2", "steps": [step("other", "scorecard", scope="group")]}
    client.post("/workflows/defs/pinned/versions", json={"definition": v2}, headers=EDITOR)
    validate(client, "pinned")
    publish(client, aid)

    detail = client.get(f"/workflows/runs/{run_id}", headers=ALICE).json()
    assert [s["key"] for s in detail["steps"]] == ["card"]  # still v1's step, not v2's


def test_a_model_step_is_skipped_cleanly_when_no_llm_is_configured(client, db):
    builtin.seed_builtin(db)
    fill(db)
    live(client, "withskill", {"title": "t", "steps": [
        step("card", "scorecard", scope="group"),
        step("brief", "skill", key="missing_submissions", inputs={"period": P})]})
    r = client.post("/workflows/defs/withskill/runs", json={"period": P}, headers=EDITOR)
    run = db.get(WorkflowRun, r.json()["id"])
    db.refresh(run)
    assert run.status == "succeeded"
    assert run.state["brief"]["skipped"] == "no_llm_configured"
    assert run.result["skipped"] == ["brief"]


def test_a_summarize_step_falls_back_to_the_template_when_the_model_invents_a_number(client, db):
    """The same grounding rule as the monthly review: one invented figure rejects the whole draft."""
    from app.reports import commentary

    class Inventing:
        messages = property(lambda self: self)

        def create(self, **kw):
            from types import SimpleNamespace as NS
            return NS(stop_reason="end_turn",
                      content=[NS(type="text", text="The group scored 99.7 this month.")])

    out = commentary.summarize(Inventing(), {"card": {"score": 87.5}}, "Summarise it")
    assert out["method"] == "template" and out["issues"][0].startswith("rejected_ungrounded_numbers")
    assert "99.7" not in out["text"]


def test_a_summarize_step_keeps_a_grounded_draft(client):
    from types import SimpleNamespace as NS

    from app.reports import commentary

    class Grounded:
        messages = property(lambda self: self)

        def create(self, **kw):
            return NS(stop_reason="end_turn", content=[NS(type="text", text="The group scored 87.5.")])

    out = commentary.summarize(Grounded(), {"card": {"score": 87.5}}, "Summarise it")
    assert out["method"] == "ai" and out["grounded"] is True


def test_a_propose_step_files_a_pending_approval_and_never_executes_it(client, db):
    fill(db)
    live(client, "proposer", {"title": "t", "steps": [
        step("ask", "propose", action="create_snapshot", args={"period": P})]})
    r = client.post("/workflows/defs/proposer/runs", json={"period": P}, headers=ALICE)
    run = db.get(WorkflowRun, r.json()["id"])
    db.refresh(run)
    req = db.scalar(select(ApprovalRequest).where(ApprovalRequest.action == "create_snapshot"))
    assert req.status == "pending" and req.via == "workflow"
    assert req.context["workflow_run_id"] == run.id
    assert run.state["ask"]["note"] == "Filed for approval. Not executed."


def test_a_scheduled_run_proposes_as_scheduler_so_no_admin_can_self_approve(client, db):
    """Autonomy tightens the human gate: the requester is never a person, so four-eyes always applies."""
    fill(db)
    live(client, "nightly", {"title": "t", "steps": [
        step("ask", "propose", action="create_snapshot", args={"period": P})]})
    sched = client.post("/schedules", headers=ALICE, json={
        "job": "workflow", "name": "nightly", "cadence": {"type": "daily", "time": "02:00"},
        "params": {"workflow_key": "nightly", "period": P}}).json()
    client.post(f"/schedules/{sched['id']}/run-now", headers=ALICE)

    req = db.scalar(select(ApprovalRequest).where(ApprovalRequest.action == "create_snapshot"))
    assert req.requested_by == "scheduler" and req.status == "pending"
    # Any admin may approve it, because none of them asked for it.
    assert client.post(f"/approvals/{req.id}/decision", json={"decision": "approve"},
                       headers=ALICE).json()["status"] == "executed"


# --- governance ----------------------------------------------------------------------------------

def test_an_unpublished_workflow_cannot_be_run(client, db):
    mk(client, "draft_only")
    validate(client, "draft_only")
    r = client.post("/workflows/defs/draft_only/runs", json={"period": P}, headers=EDITOR)
    assert r.status_code == 409 and "not published" in r.json()["detail"]


def test_publishing_a_workflow_needs_a_second_admin_and_shows_the_plan(client, db):
    aid = mk(client, "reviewed").json()["id"]
    validate(client, "reviewed")
    prop = client.post("/approvals", json={"action": "publish_asset", "args": {"asset_id": aid}},
                       headers=ALICE).json()
    ctx = prop["approval"]["context"]
    assert ctx["kind"] == "workflow" and "Group snapshot" in ctx["instructions"]
    # The requester cannot wave through their own workflow.
    assert client.post(f"/approvals/{prop['approval']['id']}/decision", json={"decision": "approve"},
                       headers=ALICE).status_code == 403
    assert client.post(f"/approvals/{prop['approval']['id']}/decision", json={"decision": "approve"},
                       headers=BOB).json()["status"] == "executed"


def test_publishing_is_refused_when_a_referenced_skill_was_deprecated(client, db):
    builtin.seed_builtin(db)
    mk(client, "usesskill", {"title": "t", "steps": [
        step("brief", "skill", key="my_skill", inputs={})]})
    checks = {c["name"]: c for c in validate(client, "usesskill")["validation"]["checks"]}
    assert checks["uses:skill:my_skill"]["ok"] is False  # never published


def test_a_scoped_user_cannot_author_run_or_schedule_a_workflow(client, db):
    scoped = h("sam", Role.EDITOR, [1])
    assert mk(client, "nope", headers=scoped).status_code == 403
    assert client.get("/workflows/defs", headers=scoped).status_code == 403
    live(client, "snapshot")
    assert client.post("/workflows/defs/snapshot/runs", json={"period": P}, headers=scoped).status_code == 403


def test_a_workflow_does_not_appear_among_skills_or_agents(client, db):
    live(client, "snapshot")
    assert "snapshot" not in {s["key"] for s in client.get("/skills", headers=ALICE).json()}
    assert "snapshot" not in {a["key"] for a in client.get("/agents", headers=ALICE).json()}
    assert client.get("/agents/snapshot", headers=ALICE).status_code == 404


def test_a_workflow_cannot_be_resolved_as_a_prompt(client, db):
    live(client, "snapshot")
    with pytest.raises(asset_service.AssetError):
        asset_service.resolve(db, None, "workflow", "snapshot")


def test_scheduling_refuses_a_workflow_that_is_not_published(client, db):
    mk(client, "unpub")
    r = client.post("/schedules", headers=ALICE, json={
        "job": "workflow", "name": "x", "cadence": {"type": "daily", "time": "02:00"},
        "params": {"workflow_key": "unpub"}})
    assert r.status_code == 422 and "published workflow" in r.json()["detail"]


def test_the_scheduled_job_stops_when_the_workflow_is_deprecated(client, db):
    from datetime import UTC, datetime

    live(client, "retired")
    asset_service.deprecate(db, None, asset_service.get(db, "workflow", "retired"))
    with pytest.raises(jobs.JobFailed):
        jobs.job_workflow(db, {"workflow_key": "retired", "period": P},
                          datetime(2026, 10, 29, tzinfo=UTC), {"factory": None})


# --- the planner ---------------------------------------------------------------------------------

PLAN = {"title": "Monthly snapshot", "steps": [
    {"key": "card", "label": "Build the group scorecard", "type": "scorecard",
     "args": {"scope": "group", "period": "run"}}]}


async def plan_with(db, *script, description="Give me a monthly snapshot"):
    from app.core.security import Principal
    return await planner.draft(ScriptedClient(*script), db, Principal("alice", Role.ADMIN, None),
                               description, P)


@pytest.mark.asyncio
async def test_a_valid_plan_is_parsed_from_a_fenced_json_block(client, db):
    out = await plan_with(db, ("text", f"```json\n{json.dumps(PLAN)}\n```"))
    assert out["problems"] == [] and out["spec"]["title"] == "Monthly snapshot"
    assert out["raw"] is None


@pytest.mark.asyncio
async def test_an_invalid_plan_gets_exactly_one_repair_round(client, db):
    bad = json.dumps({"title": "t", "steps": [{"key": "s", "label": "l", "type": "tool",
                                               "args": {"name": "rm_rf"}}]})
    fake = ScriptedClient(("text", bad), ("text", json.dumps(PLAN)))
    from app.core.security import Principal
    out = await planner.draft(fake, db, Principal("alice", Role.ADMIN, None), "do a thing", P)
    assert len(fake.calls) == 2 and out["problems"] == []  # corrected on the single retry


@pytest.mark.asyncio
async def test_a_plan_that_stays_invalid_is_handed_back_with_its_problems(client, db):
    bad = json.dumps({"title": "t", "steps": [{"key": "s", "label": "l", "type": "tool",
                                               "args": {"name": "rm_rf"}}]})
    out = await plan_with(db, ("text", bad))
    assert out["spec"] is None and any("workflow_tools_exist" in p for p in out["problems"])
    assert out["raw"]  # the draft comes back so a human can fix it by hand


@pytest.mark.asyncio
async def test_prose_around_the_json_is_tolerated(client, db):
    out = await plan_with(db, ("text", f"Sure! Here you go:\n{json.dumps(PLAN)}\nHope that helps."))
    assert out["spec"]["title"] == "Monthly snapshot"


@pytest.mark.asyncio
async def test_the_dynamic_catalogue_is_in_the_user_turn_not_the_cached_system_block(client, db):
    fake = ScriptedClient(("text", json.dumps(PLAN)))
    from app.core.security import Principal
    await planner.draft(fake, db, Principal("alice", Role.ADMIN, None), "something", P)
    system = json.dumps(fake.calls[0]["system"])
    user = json.dumps(fake.calls[0]["messages"])
    assert "<catalogue>" in user and "<catalogue>" not in system
    assert fake.calls[0]["tools"] == []  # the planner writes a plan; it does not call tools


@pytest.mark.asyncio
async def test_a_drafted_plan_is_not_persisted(client, db):
    await plan_with(db, ("text", json.dumps(PLAN)))
    assert db.scalar(select(Asset).where(Asset.kind == "workflow")) is None
