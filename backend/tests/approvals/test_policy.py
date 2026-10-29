from dataclasses import replace

from app.approvals.actions import ACTIONS, Risk
from app.approvals.policy import Verdict, evaluate
from app.core.security import Principal, Role

REM, SNAP = ACTIONS["send_kpi_reminder"], ACTIONS["create_snapshot"]
GROUP = Principal("a", Role.ADMIN, None)
SCOPED = Principal("s", Role.EDITOR, frozenset({1}))
ALL = {"IC1", "IC2", "IC3"}


def ev(action, targets, who=GROUP, visible=ALL, bulk=5):
    return evaluate(action, targets, visible, who, bulk).verdict


def test_external_message_needs_approval():
    assert ev(REM, ["IC1"]) is Verdict.REQUIRE_APPROVAL


def test_read_risk_is_allowed():
    assert ev(replace(REM, risk=Risk.READ), ["IC1"]) is Verdict.ALLOW


def test_destructive_always_denied_even_for_admin():
    assert ev(replace(REM, risk=Risk.DESTRUCTIVE), ["IC1"]) is Verdict.DENY


def test_bulk_denied_over_threshold_not_at_it():
    codes = [f"IC{i}" for i in range(1, 7)]
    assert ev(REM, codes[:5], visible=set(codes)) is Verdict.REQUIRE_APPROVAL
    assert ev(REM, codes, visible=set(codes)) is Verdict.DENY
    assert ev(REM, codes, visible=set(codes), bulk=10) is Verdict.REQUIRE_APPROVAL


def test_out_of_scope_and_unknown_targets_denied_identically():
    a = evaluate(REM, ["IC2"], {"IC1"}, SCOPED)   # exists, but not yours
    b = evaluate(REM, ["NOPE"], {"IC1"}, SCOPED)  # does not exist
    assert a.verdict is b.verdict is Verdict.DENY and a.reason == b.reason  # nothing to tell them apart


def test_group_wide_only_actions_denied_for_scoped_users():
    assert ev(SNAP, [], who=SCOPED, visible={"IC1"}) is Verdict.DENY
    assert ev(SNAP, []) is Verdict.REQUIRE_APPROVAL
