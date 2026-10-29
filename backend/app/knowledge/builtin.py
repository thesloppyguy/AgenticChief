"""Reference documents generated from the code, so they cannot drift from what the engine does.

The KPI formula wording is the PRD's Appendix A.6 ("Scoring notes").
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, Role
from app.db.models import Document
from app.ingestion.sources import SOURCE_KPIS, SOURCE_LABELS
from app.kpi_registry.seed import KPIS, PILLAR_LABELS, PILLAR_WEIGHTS
from app.services.manual_inputs import MANUAL_KPIS

from . import store
from .chunking import chunk_text

SYSTEM = Principal("system", Role.ADMIN, None)

FORMULAS = {
    "offer_to_joining": "Candidates who joined / total offers released x 100.",
    "time_to_fill": "Average of (offer acceptance date minus requisition approval date) across positions closed in the period. Lower is better.",
    "new_hire_retention_12m": "New hires still employed at 12 months / total new hires in the same cohort x 100.",
    "cost_per_hire": "Total recruitment cost / total hires in the period. Lower is better. At Group level: total cost / total hires (never an average of company ratios).",
    "ppw_on_time": "Performance Planning Workshop organised, with goals cascaded from IC level, before 1 April (1 = yes, 0 = no).",
    "kra_submission": "Employees who submitted their KRA on or before 30 June / total eligible employees x 100. Scored from June.",
    "mid_term_review": "Employees who completed the Mid-Term Review on or before 31 December / total eligible x 100. Scored from December.",
    "continuous_feedback": "Minimum two feedback entries per employee in addition to the mid-term review (target 2).",
    "tni_employees": "Employees who completed the Training Needs Identification / total eligible employees x 100.",
    "training_calendar": "Half-yearly training calendar published on time: 0, 1 or 2. Target 1 from April (Apr-Sep calendar), 2 from October (Oct-Mar calendar).",
    "tni_fulfilment": "Training needs fulfilled / total training needs identified x 100.",
    "l1_feedback": "Level 1 feedback on training programmes, given on a 1 to 5 scale and expressed as a percentage of 5 (target 80).",
    "role_skill_coverage": "Employees with skills and proficiency mapped to their role / total employees in scope x 100.",
    "top_talent_review": "Talent Council top-talent review held before 31 December (yes/no and date). Scored from December.",
    "idps_top_talent": "Count of Individual Development Plans created for top talent, year to date (target 25 for the year).",
    "pli_assessment": "M3C and M4A employees who completed the assessment and received the PLI report / total M3C and M4A employees x 100.",
    "idp_creation_rate": "Target employees who developed an IDP / total target employees x 100.",
    "ahc_completion": "Employees who completed the Annual Health Check-up / total eligible x 100.",
    "platform_adoption": "Unique employees who logged in during the period / total active employees x 100.",
    "gptw_score": "Trust Index score as published in the annual Great Place To Work survey report.",
    "overall_retention": "Total retentions in the year / average headcount in the period x 100.",
    "top_talent_retention": "100% minus (regrettable exits at CPR 7 and above / average headcount at CPR 7 and above x 100).",
    "trainee_retention": "Trainees remaining after three years / total trainees onboarded x 100.",
}


def kpi_definitions(kpis=None) -> str:
    out = ["# Group HR Scorecard: KPI definitions", "",
           "The scorecard has 7 pillars and 23 sub-KPIs. Each sub-KPI has a weight inside its pillar (each pillar adds up to 100%), "
           "a target, a direction and a formula. Pillar weights in the overall score: "
           + ", ".join(f"{PILLAR_LABELS[p]} {round(w * 100)}%" for p, w in PILLAR_WEIGHTS.items()) + ".", ""]
    source_of = {k: SOURCE_LABELS[s] for s, ks in SOURCE_KPIS.items() for k in ks}
    for pillar in PILLAR_WEIGHTS:
        out += [f"## {PILLAR_LABELS[pillar]}", ""]
        for k in (k for k in (kpis or KPIS) if k.pillar == pillar):
            src = "entered manually by editors" if k.key in MANUAL_KPIS else f"data from {source_of.get(k.key, 'a source system')}"
            direction = "lower is better" if k.direction.value == "lower" else "higher is better"
            title = k.key.replace("_", " ").title()
            out += [f"### {title}", f"Weight in pillar: {round(k.weight * 100)}%. Target: {k.target:g}. {direction.capitalize()}. Source: {src}.",
                    FORMULAS.get(k.key, ""), ""]
    return "\n".join(out)


SCORING_RULES = """\
# Group HR Scorecard: how scores are calculated

## Sub-KPI score
Achievement / target x 100. For lower-is-better KPIs (Time to Fill, Cost per Hire) it is target / achievement x 100.
The Copilot never calculates scores: they come from the deterministic scoring engine.

## Pillar score
The weighted average of the pillar's sub-KPI scores. A sub-KPI with no value, not yet due, or with no data source is
left out and the remaining weights are rescaled. It is never counted as zero.

## Company (IC) overall score
The weighted average of the pillar scores using the pillar weights. A pillar with nothing scoreable is left out and
the remaining pillar weights are rescaled. Coverage is the share of pillar weight that could be scored.

## Group score
For each sub-KPI the Group achievement is the simple average of the company achievements (Cost per Hire is total
cost / total hires), and that is then scored the same way.

## Status
Green (on track), amber (needs attention) and red (off track), by thresholds that administrators set (defaults: 90
and 75). An administrator can also withhold the status when too little of the scorecard could be scored.

## Why a KPI can be excluded
Missing: the source had no value for that company. Not due: it is scored only from its due month in the April to
March year (KRA submission from June; mid-term review and top-talent review from December; the training calendar
target is 1 from April and 2 from October). No source: no integration supplies that KPI, which is a connection gap
and not a company's failure.
"""


def scoring_rules() -> str:
    return SCORING_RULES


BUILTIN = {"scorecard-kpi-definitions.md": ("Scorecard KPI definitions", kpi_definitions),
           "scorecard-scoring-rules.md": ("How scorecard scores are calculated", scoring_rules)}


def seed_builtin(db: Session, commit: bool = True) -> int:
    """Idempotent: add what is missing, refresh what changed in the code. Returns documents written."""
    from app.services.scorecard import active_kpis  # lazy: scorecard imports the ingestion registry

    written = 0
    for filename, (title, make) in BUILTIN.items():
        body = (make(active_kpis(db)) if make is kpi_definitions else make()).encode()
        existing = db.scalar(select(Document).where(Document.builtin.is_(True), Document.filename == filename))
        if existing is not None:
            text = store.extract_text(filename, body)
            fresh = store.hashlib.sha256(text.encode()).hexdigest()
            # Refresh when the text changed OR the way it is split changed (so retrieval improvements reach old installs).
            if existing.content_hash == fresh and existing.chunk_count == len(chunk_text(text)):
                continue
            store.delete_document(db, SYSTEM, existing, commit=commit)
        store.add_document(db, SYSTEM, title, filename, body, domain="scorecard", builtin=True, commit=commit)
        written += 1
    return written
