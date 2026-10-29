"""The 7 pillars / 23 sub-KPIs from PRD Appendix A.6."""
from __future__ import annotations

from app.scoring.models import Direction, KpiDef, ScoringConfig

H, L = Direction.HIGHER, Direction.LOWER

PILLAR_WEIGHTS = {
    "talent_acquisition": 0.15,
    "performance_management": 0.15,
    "learning_development": 0.15,
    "organizational_effectiveness": 0.10,
    "talent_management": 0.20,
    "engagement_wellness": 0.10,
    "retention": 0.15,
}

PILLAR_LABELS = {
    "talent_acquisition": "Talent Acquisition",
    "performance_management": "Performance Management",
    "learning_development": "Learning & Development",
    "organizational_effectiveness": "Organizational Effectiveness",
    "talent_management": "Talent Management",
    "engagement_wellness": "Engagement / Wellness",
    "retention": "Retention",
}

KPIS: list[KpiDef] = [
    KpiDef("offer_to_joining", "talent_acquisition", 0.25, H, 100),
    KpiDef("time_to_fill", "talent_acquisition", 0.25, L, 60),
    KpiDef("new_hire_retention_12m", "talent_acquisition", 0.25, H, 100),
    KpiDef("cost_per_hire", "talent_acquisition", 0.25, L, 60000,
           group_sum_of=("recruitment_cost", "hires")),
    KpiDef("ppw_on_time", "performance_management", 0.25, H, 1),
    KpiDef("kra_submission", "performance_management", 0.25, H, 100, due_from_month=6),
    KpiDef("mid_term_review", "performance_management", 0.25, H, 100, due_from_month=12),
    KpiDef("continuous_feedback", "performance_management", 0.25, H, 2),
    KpiDef("tni_employees", "learning_development", 0.25, H, 100),
    KpiDef("training_calendar", "learning_development", 0.25, H, 1,
           target_steps=((4, 1), (10, 2))),
    KpiDef("tni_fulfilment", "learning_development", 0.25, H, 100),
    KpiDef("l1_feedback", "learning_development", 0.25, H, 80),
    KpiDef("role_skill_coverage", "organizational_effectiveness", 1.0, H, 100),
    KpiDef("top_talent_review", "talent_management", 0.25, H, 1, due_from_month=12),
    KpiDef("idps_top_talent", "talent_management", 0.25, H, 25, cumulative=True),
    KpiDef("pli_assessment", "talent_management", 0.25, H, 100),
    KpiDef("idp_creation_rate", "talent_management", 0.25, H, 100),
    KpiDef("ahc_completion", "engagement_wellness", 0.25, H, 100),
    KpiDef("platform_adoption", "engagement_wellness", 0.25, H, 80),
    KpiDef("gptw_score", "engagement_wellness", 0.50, H, 80),
    KpiDef("overall_retention", "retention", 0.30, H, 100),
    KpiDef("top_talent_retention", "retention", 0.40, H, 100),
    KpiDef("trainee_retention", "retention", 0.30, H, 80),
]

DEFAULT_CONFIG = ScoringConfig(pillar_weights=PILLAR_WEIGHTS)
