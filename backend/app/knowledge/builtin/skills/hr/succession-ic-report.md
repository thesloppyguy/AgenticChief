---
name: succession-ic-report
description: Draft an IC or Group succession coverage report from get_succession_coverage — not from Talent Management scorecard KPIs
when_to_use: User asks for a succession report, bench strength, critical-role coverage, ready-now gaps, or single-point-of-failure incumbents for an IC or the Group
category: hr
---

# Succession coverage report

Produce a CHRO-ready succession brief from **succession coverage data only**. Talent Management scorecard KPIs (Top Talent Review completion, IDPs, PLI) are process-compliance signals — cite them only in a short "context" aside if provided, never as succession proof.

## Required inputs

Call or receive from earlier workflow steps:

1. **Scope** — company_code (e.g. LTIM) or Group
2. **Period** — YYYY-MM; check fixture `freshness.as_of` and flag if stale
3. **get_succession_coverage** payload — headline, by_function, bench (with readiness, nine_box, incumbent_flight_risk, vacancy_exposure)

If `available` is false or `missing` is non-empty, stop and state exactly which succession inputs are absent. Do **not** invent coverage from scorecard pillars or document search alone.

## Output structure

### 1. Header (one line)

`{IC or Group} succession coverage — {period}` plus freshness note if `freshness.stale`.

### 2. Coverage snapshot (4–6 bullets, numbers only from the tool)

- Critical roles tracked
- Ready-now coverage % (and delta if present)
- Roles with weak / no successor
- Single-point-of-failure count (if present)
- Internal fill rate vs target

### 3. Gaps that need a decision

Table or bullets of roles where `readiness` is `no_ready` or `status` is `thin` / `no_ready_internal`. For each: role, readiness, 9-box, incumbent flight risk, vacancy exposure, recommended development move.

### 4. Single-point-of-failure / retention exposure

Incumbents with `incumbent_flight_risk: high` or `vacancy_exposure: high`. Name the risk in plain language; do not soften.

### 5. Documents (optional)

If a prior `search_documents` step returned hits, cite title + snippet. If none, write: "No succession documents retrieved — coverage figures above are fixture/HRIS only."

### 6. Ask of the CHRO (2–3 concrete next steps)

Examples: approve external search for a named role; accelerate IDP for a ready_1_2y successor; schedule a 90-day watch on a high flight-risk incumbent. Prefer `propose` actions already in the catalogue when this skill runs inside a workflow.

## What NOT to do

- Do not treat Top Talent Review / IDP / PLI completion as succession coverage
- Do not expand Group totals when the ask was one IC
- Do not invent 9-box, readiness, or flight-risk values
- Do not present a confident "full succession report" when inputs were partial — label the gap
