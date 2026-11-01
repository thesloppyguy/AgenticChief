# Backend reference

FastAPI + SQLAlchemy + Alembic on SQLite, Python 3.12, managed with `uv`. Everything in this document
describes code that exists in `backend/app`.

## 1. The one invariant

**Scores are computed by deterministic Python. The model never does arithmetic.**

`app/scoring/` is pure: no database, no HTTP, no LLM. It takes KPI definitions, values and a config, and
returns scores. Everything else — ingestion, the API, the Copilot, reports — either feeds it or reads its
output. The Copilot's system prompt forbids it from calculating, estimating or rounding any number; every
figure it states must have come back from a tool call that ultimately called the scoring engine.

This is what makes the numbers defensible: two people asking the same question in different ways get the
same answer, and a published report can be recomputed from its inputs years later.

## 2. Process model

`app/main.py` wires one FastAPI app. On startup (`lifespan`):

1. `assert_schema_current()` — if the database is behind the code, **the server refuses to start**. A
   stale schema silently producing wrong numbers is worse than downtime.
2. Seeds built-in reference documents and built-in skills/agents (idempotent).
3. `sweep_stale()` — workflow runs whose worker died without a heartbeat are marked `interrupted` so they
   can be resumed rather than silently lost.
4. Starts the in-process scheduler loop if `SCHEDULER_ENABLED`.

SQLite is single-writer, so **run exactly one API process**. The scheduler, the alert push bus (SSE
fan-out) and workflow execution all assume one process and are written for it.

```
app/
  core/             config (pydantic-settings), security (JWT, Principal, roles)
  db/               models, session, migration guard, SQLite pragmas/types
  scoring/          PURE scoring engine — no I/O
  kpi_registry/     the 7 pillars and 23 sub-KPIs as data
  scorecard_config/ admin-editable, versioned scoring rules
  services/         glue: stored records -> scoring engine -> API payloads
  ingestion/        source adapters, raw->metric formulas, run bookkeeping
  mock_sources/     AI-generated stand-ins for the real source systems
  agents/           code-registered specialists + overrides (OpenExecutive port)
  orchestrator/     Executive loop, skills tools, MCP gateway, saved tools
  mcp_server/       FastMCP/MCPServer mount at /mcp
  integrations/     workspace provider registry (Google/Microsoft via MCP)
  copilot/          orchestrator loop, tools, persona
  memory/           per-user Copilot memory
  knowledge/        document parsing, chunking, FTS5 search
  approvals/        action catalog, policy engine, approval service
  alerts/           rule-based alerting, per-user prefs, live SSE bus
  workflows/        resumable workflow engine
  reports/          monthly review, builder, commentary, markdown/PDF export, hashing
  assets/           workflow definition assets only (skills/agents moved to OE model)
  scheduler/        cadence, jobs, runner
  audit/            append-only audit log
  api/              HTTP routers
```

## 3. Identity, roles and scope

`app/core/security.py`. A bearer JWT carries `sub`, `role` and `companies`. It decodes to a `Principal`:

| Field | Meaning |
|---|---|
| `user_id` | who |
| `role` | `admin` / `editor` / `viewer` |
| `company_ids` | `None` = group-wide; otherwise the only companies this principal may see |

Scope is enforced in the backend, in `visible_companies()` and `Principal.require_company()` — never in
the UI and never by the model. A company-scoped user's Group score is computed over **their** companies
only, and the payload says `"scope": "restricted"` so nothing is passed off as the real Group number.

Roles: `viewer` reads; `editor` additionally enters the 4 manual KPIs and uploads documents; `admin`
configures connections, schedules, scoring rules, and decides approvals.

Sign-in is a pasted dev token (`scripts/dev_token.py`). SSO is deliberately not built.

## 4. The scoring engine (`app/scoring/`)

Pure functions over frozen dataclasses. Readable top to bottom in five minutes.

### Sub-KPI score — `kpi.py`

```
higher-is-better:  achievement / target * 100
lower-is-better:   target / achievement * 100      (Time to Fill, Cost per Hire)
achievement == 0 and lower-is-better: zero_lower_is_better_score (default 100, configurable)
then capped at score_cap if one is set (default: uncapped, so 112% stays 112%)
```

A KPI produces **no score** — and is excluded, not zeroed — for one of three reasons, carried through
every payload as `excluded_reason`:

| reason | meaning | who should act |
|---|---|---|
| `not_due` | not yet due in the April–March year | nobody; it is on schedule |
| `no_source` | no integration in this deployment supplies it, so nobody *can* submit it | group IT / admin, on Connections |
| `missing` | a source that should have it returned nothing | that company's HR lead |

Keeping these apart matters: chasing a company for a KPI that no connected system can produce is a
connection gap being mis-reported as a performance failure. The Copilot persona enforces the distinction
in words too.

### Pillar score — `pillar.py`

Weighted average of the sub-KPIs **that scored**, with the remaining weights rescaled:

```
pillar          = sum(score_i * weight_i) / sum(weight_i)   over scoreable KPIs only
eligible_weight = sum(weight_i)                             reported, so coverage is visible
```

If nothing in the pillar is scoreable, the pillar score is `None` — not zero.

### Company score — `ic.py`

Same shape one level up: weighted average of the pillars that scored, using the 7 pillar weights,
rescaled over eligible weight. `pillar_coverage` = share of total pillar weight that was scoreable.

If coverage is below `min_coverage_for_status`, a score is still produced but **no status is assigned**
(`status_withheld: true`). A green badge resting on 30% of the evidence is a worse answer than no badge.

### Group score — `group.py`

Per KPI, Group achievement is the **simple average of company achievements** (not headcount-weighted;
this matches the Excel prototype). The exception is any KPI with `group_sum_of` — Cost per Hire — where
Group achievement is `total recruitment cost / total hires`, because averaging per-company ratios would
weight a 10-hire company the same as a 2,000-hire one.

`missing_ic_policy` decides whether companies without a value are excluded from that average (default) or
counted as zero.

The Group score is then the ordinary company calculation run over those Group-level achievements.

### Status — `status.py`

`>= 90` green, `75` to `< 90` amber, `< 75` red. Applied to the **unrounded** score, so 89.96 displayed
as "90.0" is still amber and the drill-down shows why.

### Fiscal calendar — `fiscal.py`

April = index 0 ... March = index 11.

- `due_from_month` — the KPI is `not_due` before it. KRA submission from June; mid-term review and top
  talent review from December.
- `target_steps` — a target that changes mid-year. Training calendar: 1 from April, 2 from October.
- `prorate_cumulative` (optional rule) — year-to-date count KPIs are scored against
  `target * months_elapsed / 12`, so "25 IDPs by March" doesn't read red every April.

### The register — `app/kpi_registry/seed.py`

The 7 pillars with their group weights (Talent Acquisition 15%, Performance Management 15%, L&D 15%,
Organizational Effectiveness 10%, Talent Management 20%, Engagement/Wellness 10%, Retention 15%) and all
23 sub-KPIs with within-pillar weight, direction, target and calendar rules. It is plain data; the engine
has no KPI-specific branches except the raw-count formulas in `ingestion/raw.py`.

## 5. Scoring rules are versioned and approved — `app/scorecard_config/`

Thresholds, score cap, pillar weights, per-KPI weight/target overrides, missing-company policy, minimum
coverage and pro-rating are **not constants**. They live in `ScorecardConfigVersion`; exactly one is
active; with none stored, the built-in defaults (version 1) apply.

Flow: an admin creates a **draft** → `GET /scorecard-config/{version}/preview` recomputes the whole
scorecard on **real data** under the draft and diffs it against the active rules → activating it is an
approval action a **second** admin must approve.

`ScorecardRules` validates hard, before anything reaches the engine: the pillar weights must name exactly
those 7 pillars and sum to 100%; each pillar's KPI weights must still sum to 100%; `amber_min <
green_min`; a `score_cap` below `green_min` (which would make green unreachable) is rejected; a target
that follows a calendar rule cannot be overridden.

Every score carries `calc_version`, so a published report always says which rules produced it. Changing
rules never rewrites a published snapshot.

## 6. Data in — `app/ingestion/`

### Raw counts, not percentages — `raw.py`

Every extractor returns **raw counts**; one module applies the formulas. `SPECS` declares each of the 19
sourced KPIs as a `ratio`, a plain `value`, or `exits` (retention expressed as
`100 - exits/headcount*100`).

That design buys three things: the formula lives in exactly one place; every stored value keeps its
numerator and denominator, so a drill-down can show *why*; and impossible data is rejected at the door
(`RawDataError` — 120 joined of 100 offers, a negative count, an L1 rating outside 1–5). A ratio with a
zero denominator is **no value**, never zero.

### Source modes — `registry.py`

Per source, in priority order:

1. **registry** — a KPI with an approved capability mapping is pulled through the capability registry and
   removed from whichever source used to own it.
2. **live** — `INTEGRATIONS__<SOURCE>__ENABLED=true`; a REST extractor driven by a JSON mapping file in
   `backend/integrations/`.
3. **stub** — generated data, if `STUB_DATA_ENABLED` (default on).
4. **disabled** — the source is absent entirely and its KPIs become `no_source`.

Default source ownership (`sources.py`): SuccessFactors 14 KPIs, PeopleStrong/Skima 3, MyHealth 1,
Hi5Plus 1 — 19 sourced. The remaining 4 are manual.

### The run — `runner.py`

Per source per period, an `IngestionRun` row records mode, status, companies OK/failed, records written
and error **type names only** (never raw payloads — source data doesn't leak into the error log). One
company's failure never stops the run. An extractor may only write KPIs it owns, and **a manually entered
value is never overwritten by an automated pull**. Each written `KpiRecord` stores
`{mode, run_id, raw, ...lineage}` in `detail`.

### Manual inputs — `app/services/manual_inputs.py`

Four editor-only KPIs: Cost per Hire (cost + hires), Top Talent Review (yes/no + date), IDPs created
(YTD), GPTW score. Validated per KPI, scoped to companies the editor may see, and every change writes a
`ManualInputHistory` row with the old and new value — so "who changed GPTW to 84, and when" is answerable.

### AI-generated source systems — `app/mock_sources/`

Off by default. When enabled, this app also serves HTTP endpoints *shaped like* each real source (OData,
REST, flat and nested JSON, bearer auth). Claude generates each company's HR profile once and stores it;
the real live adapters then read it over HTTP. The point is that the **entire live ingestion path** —
auth, mapping file, parsing, formulas, lineage — is exercised before a real tenant exists. Responses
carry `X-Data-Origin`, which lands in lineage, and anything AI-made is flagged synthetic in the UI and in
reports. Swapping in a real tenant is a base URL and a mapping file.

## 7. Connectors and MCP — OpenExecutive port

External tools are no longer a DB capability registry. They are configured in `company/mcp_servers.json`
(see `backend/mcp_servers.json.example`) and launched by `app/orchestrator/mcp_gateway.py` over stdio
when `MCP_ENABLED=true`. The Executive discovers them with `search_tools` / `call_tool`. AgenticChief
also **serves** MCP at `/mcp` (`app/mcp_server`) so external clients can consult specialists and skills.

Workspace mail/calendar provider selection lives under `app/integrations/workspace/`. Setup health is
exposed at `GET /setup/status` (UI: `/settings/status`).

KPI ingestion uses live adapters, stub fixtures, or manual entry only — registry KPI mappings were removed.

## 8. The Copilot / Executive — `app/orchestrator/executive.py`

OpenExecutive-style tool-use loop: `consult_specialist`, `search_skills` / `load_skill`, scorecard tools
from `app/copilot/tools.py`, and optional MCP gateway tools. Max 8 tool rounds; specialist fan-out runs
in parallel. Dynamic context (period, memory) stays in the user turn for prompt-cache stability.

Agents are code-registered under `app/agents/` with SQLite overrides (`agent_overrides`). Skills are
Markdown playbooks under `app/knowledge/builtin/skills/` indexed in ChromaDB.

Sessions and messages are persisted and searchable. `app/memory/` extracts durable facts (decisions,
initiatives, advice) from sessions into per-user memories — private, expiring after
`MEMORY_RETENTION_DAYS` unless pinned, capped per user, viewable, editable, deletable, and switchable off
per user. Memories are injected as a `<past_decisions>` block the persona treats as possibly-stale
context, never as current figures.

## 9. Approvals and governance — `app/approvals/`

The only path to a consequential action.

`actions.py` is the complete catalog. Nothing else — including the Copilot — imports an executor; only
`approvals.service` calls one, and only after a human decision.

| Action | Risk | Scope |
|---|---|---|
| `send_kpi_reminder` | external_message | per company |
| `create_snapshot` | internal_write | group-wide only |
| `publish_monthly_report` | internal_write | group-wide only |
| `publish_asset` (skill/agent) | internal_write | group-wide only |
| `approve_kpi_mapping` | internal_write | group-wide only |
| `activate_scorecard_config` | internal_write | group-wide only |

`policy.py` — pure, independently testable, cheapest hard denials first:

1. `destructive` → **deny**, always.
2. group-wide-only action requested by a scoped user → deny.
3. more than `APPROVAL_BULK_MAX_TARGETS` (default 5) targets → deny as bulk.
4. any target outside the requester's scope → deny, with a message that doesn't reveal which companies
   exist.
5. `read` → allow. Anything else → **require approval**.

Four-eyes: `APPROVAL_ALLOW_SELF_APPROVAL=false` by default — nobody approves their own request. A
`precheck` runs before anyone is asked, so requests that can never succeed ("this report is already
published", "that version never passed validation") are rejected up front, and the approver is shown a
rich context block: what changes, what depends on it, whether it is a rollback. Decisions are append-only
(`ApprovalEvent`), and a rejected request can be resubmitted with changes.

Approved reminders queue into `OutboundMessage`; a real email/chat channel is not built yet.

## 10. Alerts — `app/alerts/`

Rule-based, not model-based. `evaluate_period` compares this period's statuses with last month's and
raises an alert on anything that **turned** red — a company already red last month isn't re-alerted.
Ingestion failures raise their own alerts. Dedupe is a unique key per (kind, entity, period), so
re-evaluating a period never duplicates.

Delivery is per-user: minimum severity, muted kinds, quiet hours in the user's timezone, and company
scope. Live push is SSE, fanned out in-process, and alerts publish **only after the transaction that
created them commits** — a client is never told about an alert that then rolls back.

## 11. Workflows and the monthly review — `app/workflows/`, `app/reports/`

The workflow engine persists each step's output into `WorkflowRun.state` and emits `WorkflowEvent` rows.
A run interrupted by a restart resumes **after its last completed step** instead of starting over;
staleness is detected by heartbeat, so another live instance's run is left alone.

The monthly leadership review is four steps: `collect` (this period's scorecard and last period's) →
`lineage` (per-source last run, plus a census of where every value came from: live, stub, registry,
AI-generated, manual) → `build` (comparisons, movers, exceptions) → `commentary`.

The commentary step is the interesting one: the model drafts narrative, then **every number in that
narrative is checked against the computed report, and the commentary is only kept if they all match.**
A model that invents a figure gets its paragraph dropped, not published.

## 12. Reports and integrity

A published report is a `ReportSnapshot`: the full payload, the `calc_version` that produced it, and a
SHA-256 `content_hash` of the canonical payload. SQLAlchemy `before_update` / `before_delete` listeners
raise `ImmutableRecordError` — **a published snapshot cannot be edited or deleted through the ORM at
all**. A `UNIQUE` constraint on `run_id` means a given review run publishes at most once.

Exports: Excel/CSV for the live scorecard, Markdown and PDF for snapshots and review runs.

## 13. Scheduler — `app/scheduler/`

In-process loop, polls every `SCHEDULER_POLL_S`. Jobs: `ingest` and `monthly_review`, with a cadence and
params (`period: current | previous | YYYY-MM`, optional source list). A run is claimed with a timestamp;
a claim older than `SCHEDULER_CLAIM_TIMEOUT_S` is treated as left behind by a crash and retried.
`job_ingest` ingests, then raises ingestion and status alerts. `job_monthly_review` runs the review to
completion — **publishing still needs approval**; the scheduler cannot publish anything.

## 14. Documents and knowledge — `app/knowledge/`

Uploaded reference material is parsed, chunked and indexed in SQLite FTS5. `search_documents` returns
chunks with their document title for citation. Built-in reference documents are re-seeded on startup so
they stay in step with the code. Document text is treated strictly as data (see §8).

## 15. Skills and agents — OpenExecutive model

Skills: filesystem Markdown + YAML (`app/knowledge/skills*.py`), company shadowing, Chroma search.
Agents: `SPECIALIST_REGISTRY` in `app/orchestrator/router.py`, Council API `/agents`, UI `/council`.
Workflow definitions remain versioned SQL assets (`kind=workflow`) under `app/assets/`.

## 15b. (removed) Skills and agents as DB assets — `app/assets/` (historical)

A **skill** is a reusable task (instructions, input schema, allowed tools, output format, permitted
roles); an **agent** is a specialist configuration (instructions, tools, model tier `default|deep|fast`,
permitted roles). Both are versioned and governed exactly like capabilities: `draft → validated →
published`, publication approved by a second admin. Both can carry **eval cases** (`must_call` tools,
`must_mention` phrases); a version with eval cases that have not passed **cannot be published**.

## 16. Data model

| Table | Holds |
|---|---|
| `company` | the companies in the group |
| `kpi_record` | one value per (company, kpi, period), with numerator/denominator/source/lineage |
| `manual_input_history` | every manual edit, old → new, with actor |
| `audit_event` | append-only: who did what to what |
| `report_snapshot` | immutable published report + content hash (+ `run_id`, unique) |
| `workflow_run` / `workflow_event` | resumable runs and their step timeline |
| `chat_session` / `chat_message` | Copilot sessions |
| `ingestion_run` | per-source pull outcome; drives freshness and integration health |
| `approval_request` / `approval_event` | proposals and append-only decision history |
| `outbound_message` | approved messages awaiting a delivery channel |
| `alert` / `alert_read` | alerts and per-user read state |
| `scorecard_config_version` | versioned scoring rules |
| `asset` / `asset_version` | skills and agents |
| `job_schedule` | scheduled jobs |
| `document` / `document_chunk` | searchable reference material |
| `mock_company_data` | AI-generated HR profiles behind the mock sources |
| `user_prefs` / `user_memory` | alert prefs, quiet hours, Copilot memory |

Migrations `0001`–`0008` in `backend/migrations/versions/`.

## 17. API surface

| Area | Endpoints |
|---|---|
| Scorecard | `GET /scorecard`, `/scorecard/companies/{id}`, `/scorecard/pillars/{pillar}`, `/companies`, `/kpis` |
| Manual input | `POST /inputs`, `GET /inputs/history` *(editor)* |
| Reports | `GET /reports/export/scorecard.{xlsx,csv}`, `POST`/`GET /reports/snapshots`, `/snapshots/{id}` + `/pdf`, `/markdown` |
| Copilot | `POST /copilot/chat` (SSE), `GET /copilot/sessions`, `/sessions/{id}` |
| Approvals | `GET /approvals/actions`, `POST /approvals`, `GET /approvals`, `/{id}`, `POST /approvals/{id}/decision`, `/resubmit` |
| Alerts | `GET /alerts`, `/alerts/stream` (SSE), `POST /alerts/{id}/read`, `/alerts/read-all`, `GET`/`PUT /alert-prefs`, `GET /unread/summary` |
| Workflows | `POST /workflows/monthly-review/runs`, `GET /workflows/runs`, `/runs/{id}`, `POST /runs/{id}/resume`, `GET /runs/{id}/markdown`, `/pdf` |
| Connections | `/connections*`, `/capabilities*`, `/kpi-mappings*` *(admin)* |
| Scoring rules | `GET /scorecard-config`, `POST /scorecard-config/drafts`, `GET /scorecard-config/{v}/preview` |
| Skills / agents | `/skills*`, `/agents*` |
| Documents | `GET /documents`, `/documents/search`, `POST /documents`, `DELETE /documents/{id}` |
| Schedules | `/schedules*` *(admin)* |
| Memory | `GET /memories`, `PUT /memories/settings`, `POST /memories/{id}/pin`, `DELETE /memories`, `/{id}` |
| Ops | `GET /health`, `GET /audit` *(admin)*, `GET /ingestion/status`, `POST /ingestion/run` *(admin)* |

OpenAPI at `/docs`.

## 18. Configuration

See `backend/.env.example`. Notable: `DATABASE_URL`, `JWT_SECRET` (32+ chars), `ANTHROPIC_API_KEY`
(Copilot, commentary, evals, stub generation — **everything else works without it**),
`INTEGRATIONS__<SOURCE>__ENABLED`, `STUB_DATA_ENABLED`, `MOCK_SOURCES_ENABLED` + `MOCK_SOURCE_TOKEN`,
`CORS_ORIGINS`, `SCHEDULER_ENABLED`, `APPROVAL_BULK_MAX_TARGETS`, `APPROVAL_ALLOW_SELF_APPROVAL`,
`MEMORY_RETENTION_DAYS`, `CHRO_ENV_FILE`.

Models: `DEFAULT_MODEL` (Copilot), `ROUTING_MODEL`, `DEEP_REASONING_MODEL` (agents set to "deep"),
`STUB_GENERATOR_MODEL`.

## 19. Testing

```bash
cd backend
uv run pytest -q                                      # ~450 tests
uv run ruff check app scripts tests migrations
```

The suite ignores your `.env` (via `CHRO_ENV_FILE`) and **never calls a real model** — AI paths use
scripted fake clients. Coverage includes the scoring rules against the Excel prototype's stated behaviour
(`tests/unit/test_prototype_conformance.py`), policy denials, four-eyes, snapshot immutability, SQLite
concurrency, timestamp handling and migration round-trips.

The Playwright smoke test in `e2e/` is the opposite: it drives the real UI with a real key against a
**copy** of the database.

## 20. Known limits

- **SSO and login hardening** are not built — pasted dev tokens only.
- **One API process.** SQLite is single-writer; the scheduler and SSE bus assume it. The migrations render
  for Postgres, but that path is untested.
- Live source adapters are verified against the AI-generated endpoints and mocks, **not a real tenant**.
- No golden test against the original Excel workbook (only its image is in the repo).
- Approved reminders queue in `outbound_message`; no email/chat delivery channel is wired up.
- Root-level `seed/` and `New Plan.md` are untracked scratch files from a different template — the
  `seed/companies/*/profile.yaml` content describes an unrelated fictional company. Nothing in `backend/`
  reads them.
