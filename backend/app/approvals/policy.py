"""Policy engine: decides allow / require approval / deny. Pure and independently testable."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.core.config import settings
from app.core.security import Principal

from .actions import ActionDef, Risk


class Verdict(StrEnum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    reason: str = ""


def evaluate(
    action: ActionDef,
    targets: list[str],
    visible_codes: set[str],
    who: Principal,
    bulk_max: int | None = None,
) -> Decision:
    """`visible_codes` = company codes `who` may see. Order matters: the cheapest hard denials first."""
    bulk_max = settings.approval_bulk_max_targets if bulk_max is None else bulk_max
    if action.risk is Risk.DESTRUCTIVE:
        return Decision(Verdict.DENY, "destructive actions are denied by policy")
    if action.group_wide_only and who.company_ids is not None:
        return Decision(Verdict.DENY, "this action needs group-wide access")
    if len(targets) > bulk_max:
        return Decision(Verdict.DENY, f"bulk actions over {bulk_max} targets are denied by policy")
    if any(t not in visible_codes for t in targets):
        # unknown and out-of-scope look the same: do not reveal which companies exist
        return Decision(Verdict.DENY, "one or more targets are unknown or out of your scope")
    if action.risk is Risk.READ:
        return Decision(Verdict.ALLOW)
    return Decision(Verdict.REQUIRE_APPROVAL, f"{action.risk.value.replace('_', ' ')} needs human approval")
