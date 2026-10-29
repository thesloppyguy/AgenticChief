"""Which system supplies which of the 19 sourced KPIs (PRD Appendix A.6).

ASSUMPTION: the sheet lists Talent Acquisition as "PeopleStrong / Skima AI / SuccessFactors". Until the
real mapping per KPI is confirmed, all three TA KPIs are assigned to "peoplestrong". Moving one is a
one-line change here; nothing else depends on it.
"""
from __future__ import annotations

SOURCE_KPIS: dict[str, tuple[str, ...]] = {
    "successfactors": (
        "ppw_on_time", "kra_submission", "mid_term_review", "continuous_feedback",
        "tni_employees", "training_calendar", "tni_fulfilment", "l1_feedback",
        "role_skill_coverage", "pli_assessment", "idp_creation_rate",
        "overall_retention", "top_talent_retention", "trainee_retention",
    ),
    "peoplestrong": ("offer_to_joining", "time_to_fill", "new_hire_retention_12m"),
    "myhealth": ("ahc_completion",),
    "hi5plus": ("platform_adoption",),
}

SOURCE_LABELS = {
    "successfactors": "SAP SuccessFactors",
    "peoplestrong": "PeopleStrong / Skima AI",
    "myhealth": "MyHealth",
    "hi5plus": "Hi5Plus / HeeraPlus",
    "registry": "Capability registry",
}
