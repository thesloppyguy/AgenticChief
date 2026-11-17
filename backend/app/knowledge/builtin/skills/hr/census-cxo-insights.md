---
name: census-cxo-insights
description: Invent CXO workforce insights from the SF-shaped employee census via get_census_metrics — beyond the fixed 23 scorecard KPIs
when_to_use: User asks for attrition drivers, manager span risk, cadre stagnation, mobility, skill coverage, trainee pipeline, regrettable exits, or wants new HR KPIs invented from employee-level data
category: hr
---

# Census-backed CXO insights

Use **get_census_metrics** (optional `company_code`). This is the employee census, not the scorecard engine and not pulse/succession YAML fixtures.

## Rules

1. Call `get_census_metrics` before inventing any KPI. If `available` is false, say the census is not seeded.
2. Prefer numbers from `metrics`. You may **propose new formulas** using `field_dictionary` and `inventable_examples` — label them as **proposed / derived**, not as official scorecard KPIs.
3. Do not conflate with Talent Management scorecard KPIs (Top Talent Review, IDPs YTD target, PLI %) unless the user asks to compare process compliance vs census reality.
4. Keep recommendations actionable for a Group CHRO or IC HR lead.

## Output shape

1. **Scope** — Group or IC + one-line what the census covers (active headcount).
2. **Headline signals** — 3–5 bullets with numbers from `metrics`.
3. **Proposed KPIs** (optional) — name, formula in plain language, current value if computable, why a CXO would care.
4. **Decisions** — 1–3 moves (retain, develop, move, hire) tied to the numbers.
