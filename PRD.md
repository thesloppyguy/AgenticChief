## 1. Executive Summary

CHRO Copilot is an AI-powered executive workspace that combines a Group HR Scorecard, conversational assistance, reusable skills, specialized agents, enterprise connections and governed workflow execution.

The platform follows a configure-once architecture: administrators connect an MCP server, API or custom function; CHRO discovers available capabilities, creates normalized tool definitions and recommends reusable skills and agent configurations. Approved capabilities become available to authorized users through one Copilot interface.

The first major business application is the Group HR Scorecard, which measures performance across seven weighted HR pillars and 23 sub-KPIs. It supports individual company (IC) and Group-level reporting, automated source-system integration, editor-only manual inputs and financial-year-aware scoring.

**Core product principle:** Configure connections once, discover capabilities automatically, reuse approved tools across the platform, and maintain deterministic calculations and governed execution.

## 2. Goals and Non-Goals

### Goals

- Calculate individual company and Group HR scores using approved formulas and weights.
- Provide dashboards, drill-downs and reports across seven HR pillars.
- Connect HR systems through MCP, REST APIs and Function Tools.
- Generate tool definitions and parameter forms from supported schemas.
- Recommend skills and agent configurations using discovered capabilities.
- Allow Copilot to answer HR questions using authorized source data and calculated metrics.
- Support manual KPI entry with editor restrictions and change history.
- Maintain audit trails for data retrieval, calculations, configuration changes and approvals.

### Non-goals for the MVP

- Autonomous employment-impacting decisions.
- Automatic approval of every newly discovered tool.
- Replacing the HRIS, ATS or other connected source systems.
- Using an LLM as the authoritative engine for numerical calculations.

## 3. Information Architecture

|Module|Responsibility|
|---|---|
|Dashboard|Group score, pillar performance, IC comparisons, exceptions and pending actions|
|Pinned|Saved reports, sessions, scorecard views, skills and agents|
|Unread|Unread notifications, connector errors and assigned approvals|
|Reports|Group HR Scorecard and generated HR reports|
|Ask Copilot|Conversational questions, analysis and authorized actions|
|Sessions|Searchable conversation and execution history|
|Skills|Reusable task definitions and workflows|
|Agents|Specialized AI workers and their permissions|
|Approvals|Review and authorization of gated operations|
|Connections|Unified integration management|

Connections includes three subsections: APIs, MCP and Function Tools.

The Group HR Scorecard is accessed through Reports, with its most important metrics and exceptions surfaced on the Dashboard.

## 4. Group HR Scorecard

### 4.1 Pillars and overall weights

|Pillar|Overall weight|Number of sub-KPIs|
|---|---|---|
|Talent Acquisition|15%|4|
|Performance Management|15%|4|
|Learning & Development|15%|4|
|Organizational Effectiveness|10%|1|
|Talent Management|20%|4|
|Engagement / Wellness|10%|3|
|Retention|15%|3|
|**Total**|**100%**|**23**|

Each pillar's internal KPI weights sum to 100%.

### 4.2 Complete KPI register

The following definitions, formulas and targets are taken from the supplied scorecard image. Manual/system classifications incorporate the accompanying requirements.

#### A. Talent Acquisition — 15%

|Sub-KPI|KPI weight|Source / input|Unit|Target|
|---|---|---|---|---|
|Offer-to-Joining Ratio|25%|PeopleStrong / AI / SuccessFactors*|%|100|
|Time to Fill|25%|PeopleStrong / AI / SuccessFactors*|Days|60|
|12-Month New Hire Retention|25%|PeopleStrong / AI / SuccessFactors*|%|100|
|Cost per Hire|25%|Manual|₹ / hire|60,000|

Formulas:

- **Offer-to-Joining Ratio:** Candidates who joined ÷ total offers released × 100.
- **Time to Fill:** Average of (date of offer acceptance − date requisition approved) across positions closed during the reporting period.
- **12-Month New Hire Retention:** New hires still employed at 12 months ÷ total new hires in the same cohort × 100.
- **Cost per Hire:** Total recruitment cost during the period ÷ total hires during the period.

Time to Fill and Cost per Hire use lower-is-better scoring.

#### B. Performance Management — 15%

|Sub-KPI|KPI weight|Source|Unit|Target|
|---|---|---|---|---|
|Organising PPW within timelines|25%|SuccessFactors|1/0|1|
|KRA Submission Timeliness|25%|SuccessFactors|%|100|
|Mid-Term Review Timeliness|25%|SuccessFactors|%|100|
|Continuous Feedback|25%|SuccessFactors|% as displayed|2|

Formulas:

- **Organising PPW within timelines:** Organise the Performance Planning Workshop to enable goal cascading from IC level, with a target before 1 April.
- **KRA Submission Timeliness:** Employees who submitted KRA on or before 30 June ÷ total eligible employees × 100.
- **Mid-Term Review Timeliness:** Employees who completed the Mid-Term Review on or before 31 December ÷ total eligible employees × 100.
- **Continuous Feedback:** Minimum two feedback entries per employee in addition to the mid-term review.

#### C. Learning & Development — 15%

|Sub-KPI|KPI weight|Source|Unit|Target|
|---|---|---|---|---|
|TNI for Employees|25%|SuccessFactors|%|100|
|Half Yearly Training Calendar within timelines|25%|SuccessFactors|2, 1, 0 as displayed|2|
|TNI Fulfilment Rate|25%|SuccessFactors|%|100|
|Level 1 Feedback on Training Programs|25%|SuccessFactors|% as displayed|80|

Formulas:

- **TNI for Employees:** Employees who completed the Training Needs Identification (TNI) ÷ total eligible employees × 100.
- **Half Yearly Training Calendar:** Release and publish each half-year training calendar based on TNI, covering April–September and October–March.
- **TNI Fulfilment Rate:** Training needs fulfilled ÷ total training needs identified × 100.
- **Level 1 Feedback on Training Programs:** Level 1 feedback on training programs, described in the prototype as a scale of 1–5.

Training calendar targets follow the supplied business rule: target 1 from April and target 2 from October.

#### D. Organizational Effectiveness — 10%

|Sub-KPI|KPI weight|Source|Unit|Target|
|---|---|---|---|---|
|Percentage of employees covered|100%|SuccessFactors|%|100|

Formula: Employees with skills and proficiency mapped to their roles ÷ total employees in scope × 100.

#### E. Talent Management — 20%

|Sub-KPI|KPI weight|Source / input|Unit|Target|
|---|---|---|---|---|
|Talent Council – Top Talent Review|25%|Manual|1 or 0|1|
|IDPs Created for Top Talent|25%|Manual|Count|25|
|PLI Assessment|25%|SuccessFactors|%|100|
|IDP Creation Rate for Target Employees|25%|SuccessFactors|%|100|

Formulas:

- **Talent Council – Top Talent Review:** Process adherence before 31 December. The manual input records Yes/No and the review date.
- **IDPs Created for Top Talent:** Count of Individual Development Plans created during the reporting period.
- **PLI Assessment:** M3C and M4A employees who completed the assessment and received the PLI report ÷ total M3C and M4A employees × 100.
- **IDP Creation Rate for Target Employees:** Target employees who developed an IDP ÷ total target employees × 100.

#### F. Engagement / Wellness — 10%

|Sub-KPI|KPI weight|Source / input|Unit|Target|
|---|---|---|---|---|
|Annual Health Check-up (AHC) Completion Rate|25%|MyHealth|%|100|
|Platform Adoption Rate|25%|Hi5Plus / HeeraPlus|%|80|
|GPTW Survey Score|50%|Manual — GPTW Score|Score|80|

Formulas:

- **AHC Completion Rate:** Employees who completed the annual health check-up ÷ total eligible employees × 100.
- **Platform Adoption Rate:** Unique employees who logged in during the period ÷ total active employees × 100.
- **GPTW Survey Score:** Trust Index score as published in the annual GPTW survey report.

#### G. Retention — 15%

|Sub-KPI|KPI weight|Source|Unit|Target|
|---|---|---|---|---|
|Overall Retention Rate|30%|SuccessFactors|%|100|
|Top Talent Retention Rate|40%|SuccessFactors|%|100|
|Trainee Retention|30%|SuccessFactors|%|80|

Formulas:

- **Overall Retention Rate:** Total retentions in the year ÷ average headcount during the period × 100.
- **Top Talent Retention Rate:** 100% − [(regrettable exits at CPR 7 and above ÷ average headcount at CPR 7 and above) × 100].
- **Trainee Retention:** Number of trainees remaining after three years ÷ total trainees onboarded.

* The Talent Acquisition source cell is shown as “PeopleStrong / AI / SuccessFactors” in the supplied image. Confirm the exact system names and the mapping of each KPI during implementation.

### 4.3 KPI scoring

For standard higher-is-better KPIs:

`KPI Score = Achievement ÷ Target × 100`

For lower-is-better KPIs:

`KPI Score = Target ÷ Achievement × 100`

The lower-is-better rule applies to Time to Fill and Cost per Hire.

The achievement percentage may exceed 100%; the supplied requirements do not yet specify whether the score is capped. Implement this as a configurable rule, with the default finalized against the Excel prototype.

### 4.4 Pillar scoring

`Pillar Score = Σ(KPI Score × KPI Weight) ÷ Σ(Eligible KPI Weights)`

Exclude KPIs with missing values or KPIs that are not yet due, then rescale the remaining eligible weights.

### 4.5 Individual company overall score

`IC Overall Score = Σ(Pillar Score × Pillar Weight) ÷ Σ(Eligible Pillar Weights)`

The recommended behavior is to exclude pillars without an eligible score and rescale remaining pillar weights. The UI must communicate coverage rather than silently treating missing pillars as zero.

### 4.6 Group score

For each sub-KPI, calculate Group achievement as the simple average of the individual company achievements, then apply the relevant scoring formula.

**Cost per Hire exception:**

`Group Cost per Hire = Total Recruitment Cost ÷ Total Hires`

Cost per Hire must not be calculated by averaging company-level cost-per-hire values.

Display the company coverage used in each Group result. The treatment of ICs with missing values must be explicitly defined in the scorecard configuration.

### 4.7 Status thresholds

|Score|Status|
|---|---|
|90 and above|Green — On track|
|75 to below 90|Amber — Needs attention|
|Below 75|Red — Off track|

Apply thresholds to the underlying score before display rounding.

### 4.8 Financial year and due dates

The scorecard year is April–March.

|KPI|Eligibility / due-date behavior|
|---|---|
|KRA Submission Timeliness|Eligible from June|
|Mid-Term Review Timeliness|Eligible from December|
|Talent Council – Top Talent Review|Eligible from December|
|Half Yearly Training Calendar|Target 1 from April, target 2 from October|

Before the relevant due month, a KPI is excluded from eligible scoring rather than receiving a zero by default.

### 4.9 Manual input workflow

The four manually entered KPIs are:

1. Cost per Hire — recruitment cost and number of hires.
2. Talent Council – Top Talent Review — Yes/No and date.
3. IDPs Created for Top Talent — year-to-date count.
4. GPTW Survey Score — Trust Index score.

Provide a dedicated manual input page restricted to editors.

Every submission must retain the reporting period, submitting user, timestamp, previous value and new value. Input validation must prevent invalid types and clearly identify missing required values.

The GPTW entry is specified as monthly on a separate page even though its formula references the annual survey result. Define whether the annual value is carried across months, re-entered monthly or associated with an annual reporting period before implementation.

## 5. Dashboard and Reports

### Dashboard

Display the current Group score, seven pillar scores, IC comparisons, KPI status distribution, reporting-period comparisons, missing data, stale connections and pending approvals.

Allow drill-down from Group to pillar, sub-KPI and individual company, with the ability to inspect source data, target, formula and calculation period.

### Reports

Reports should support:

- Group and IC scorecards.
- Pillar and sub-KPI breakdowns.
- Period-over-period comparisons.
- Missing-data and exception reports.
- Source freshness and integration health.
- Generated leadership commentary grounded in computed results.

Reports must retain calculation version, report period and source lineage.

## 6. Ask Copilot and Sessions

Ask Copilot provides one natural-language interface for authorized HR analytics, business context and approved workflows.

Example questions include:

- What is the current Group HR score?
- Which HR pillars need attention?
- Which ICs have missing KPI submissions?
- Why did Time to Fill change this quarter?
- Generate the monthly Group HR review.

Copilot must use the score calculation service for numerical answers, and distinguish actual source facts from inferred explanations.

Sessions preserve conversations, tool executions, approval references and reports. Session memory must never bypass access permissions.

## 7. Skills and Agents

Skills define reusable tasks that compose approved tools, such as:

- Generate the monthly Group HR Scorecard.
- Identify missing KPI submissions.
- Compare IC performance.
- Prepare a monthly HR leadership review.
- Investigate a selected pillar's performance trends.

Each skill records its inputs, steps, tool dependencies, output structure, permissions, version and evaluation cases.

Agents specialize in areas such as HR Analytics, Talent Acquisition, Performance Management, L&D and Retention. Start with one Copilot orchestrator and introduce specialist agents only where distinct capabilities or evaluation requirements justify them.

Generated skills and agent configurations begin as drafts and must be validated and published under the workspace's governance rules.

## 8. Connections: Configure Once, Generate the Rest

### Connection workflow

1. Configure MCP, an API or a function tool.
2. Discover server capabilities or import a supported specification.
3. Normalize operations into a shared capability registry.
4. Generate tool definitions, forms and schema validation.
5. Recommend KPI mappings, skills, agents and policy configurations.
6. Validate connection health, schemas and representative operation behavior.
7. Review permissions and publish approved capabilities.
8. Synchronize changes and assess impacts on dependent skills and agents.

### Shared capability registry

Each tool record should contain its stable ID, connection reference, description, input/output schema, implementation reference, permissions, risk category, version and lifecycle status.

The registry is the single source of truth for all integrations. It must support search, categorization, versioning, rollback, dependencies and authorization.

### KPI-to-tool mapping

For the 19 system-integrated KPIs, CHRO should recommend and store explicit mappings between each KPI and the capabilities supplying its data.

Administrators review mappings before production use. Reports, calculations and Copilot then reuse these approved mappings rather than implementing separate retrieval logic.

Discovering an MCP tool does not automatically authorize it or make its output trustworthy. New capabilities and material schema changes remain subject to validation and the configured publication policy.

## 9. Approvals and Governance

The approval service supports review, approval, rejection and requests for changes.

An approval request includes the requested operation, target, initiating user or agent, originating session, proposed arguments, supporting context, approver and decision history.

Read-only retrieval may execute within granted permissions. Numerical calculations and reports can run under the appropriate data-access controls. External record mutations, message sending and other consequential operations follow explicit approval policies.

Destructive or bulk actions are denied by default unless specifically authorized through a controlled policy.

Employment-impacting decisions must retain appropriate human decision-making and review. Approval enforcement must reside in the backend, not solely in model instructions or UI behavior.
### Scorecard data flow

Source systems and manual entries → validated KPI records → score calculation engine → pillar scores → IC overall scores → Group achievement and score → Dashboard, Reports and Ask Copilot.

Score calculations must be deterministic and independently testable. AI may explain the results but must not replace the authoritative formula engine.

Use durable persistence for KPI records, configuration versions, execution state, approvals and audit events. Support safe concurrent scheduling, retry controls, tenant isolation and secret management.
## Appendix A: Group HR Scorecard (flagship Dashboard use case)

The Group HR Scorecard is the first concrete workload for Dashboard, Reports and Connections. A prototype exists as an Excel workbook with formulas and sample data; the workbook is the source of truth for the rules below.

### A.1 Structure

- 7 pillars, weighted in the overall score: Talent Acquisition 15%, Performance Management 15%, L&D 15%, Organizational Effectiveness 10%, Talent Management 20%, Engagement/Wellness 10%, Retention 15% (total 100%).
- 23 sub-KPIs, each weighted within its pillar (see the catalog in A.7).
- 19 sub-KPIs come from data sources (systems listed in A.7); 4 are manual inputs.

### A.2 Calculation rules

- **Sub-KPI score (% achieved):** achievement / target x 100. For lower-is-better KPIs (Time to Fill, Cost per Hire): target / achievement x 100.
- **Pillar score:** weighted average of its sub-KPI scores. A sub-KPI with no value, or not yet due, is left out and the remaining weights are rescaled.
- **IC overall score:** weighted average of the 7 pillar scores using the pillar weights.
- **Group score:** for each sub-KPI, group achievement is the simple average of the IC achievements (Cost per Hire = total cost / total hires), then scored as above.
- **Status:** 90 and above green (on track); 75 to 89.9 amber (needs attention); below 75 red (off track).
- **Due months (April to March year):** KRA submission scored from June; mid-term review and top talent review from December; training calendar target is 1 from April and 2 from October.

### A.3 Manual inputs

Four sub-KPIs are entered monthly on a separate page by editors only: Cost per Hire (recruitment cost and hires), Top Talent Review (Yes/No and date), IDPs created (year to date), and the GPTW score.

### A.4 Platform requirements this creates

1. **Deterministic scoring engine.** All scores, rescaling and status bands are computed by versioned code or configuration, never by the model. The CoPilot explains and drills into the numbers but does not produce them.
2. **KPI definitions as data.** Each sub-KPI is a record: pillar, weight, direction (higher or lower is better), target, due rule, source capability, owner. Pillar weights and thresholds are configuration, editable by admins with change history.
3. **Sources via the Capability Pipeline.** Each of the 19 sourced KPIs declares the capability it needs (for example hris.headcount.read). A KPI whose capability is unmapped shows as No source rather than zero, and is excluded and rescaled like a not-yet-due KPI.
4. **Manual Input as a fourth connection type.** Role-gated forms (editors only) with monthly periods, validation, and audit of who entered or changed a value.
5. **Fiscal calendar.** April to March year, with due-month rules evaluated per period.
6. **Explainability.** From any red or amber tile, Ask CoPilot can show which sub-KPIs drove the score, what was excluded or rescaled, and which source each value came from.
7. **Alerts and reports.** A status change to red raises a feed item; a monthly scorecard report is saved as an immutable snapshot.

### A.5 Acceptance tests

- The engine reproduces the workbook's pillar, IC, Group and status results exactly for the sample data (the workbook is the golden test).
- Edge cases: missing value, not-yet-due KPI, all KPIs in a pillar excluded, zero achievement on a lower-is-better KPI, Cost per Hire at group level, scores above 100.

### A.6 KPI catalog

The 23 sub-KPIs with their weights inside each pillar (each pillar sums to 100%). Source names are as written in the sheet; Manual means entered by editors on the monthly input page. Talent Acquisition draws on three systems, so one pillar can need several connections.

|   |   |   |   |   |   |   |
|---|---|---|---|---|---|---|
|Pillar (weight)|Sub-KPI|Weight in pillar|Source|Unit|Target|Scoring notes|
|Talent Acquisition (15%)|Offer-to-Joining Ratio|25%|PeopleStrong / Skima AI / SuccessFactors|%|100|Candidates joined / total offers released x 100|
|Talent Acquisition (15%)|Time to Fill|25%|PeopleStrong / Skima AI / SuccessFactors|Days|60|Lower is better; average of offer acceptance date minus requisition approval date, positions closed in the period|
|Talent Acquisition (15%)|12-Month New Hire Retention|25%|PeopleStrong / Skima AI / SuccessFactors|%|100|New hires still employed at 12 months / total new hires in the same cohort x 100|
|Talent Acquisition (15%)|Cost per Hire|25%|Manual|₹ per hire|60,000|Lower is better; total recruitment cost / total hires in the period; group value = total cost / total hires|
|Performance Management (15%)|Organising PPW within timelines|25%|SuccessFactors|1/0|1|Performance planning workshop cascaded from IC level before 1 April|
|Performance Management (15%)|KRA Submission Timelines|25%|SuccessFactors|%|100|Submitted on or before 30 June / total eligible; scored from June|
|Performance Management (15%)|Mid-Term Review Timelines|25%|SuccessFactors|%|100|Completed on or before 31 December / total eligible; scored from December|
|Performance Management (15%)|Continuous Feedback|25%|SuccessFactors|% (as shown)|2|Minimum 2 feedbacks per employee in addition to the mid-term review|
|Learning and Development (15%)|TNI for Employees|25%|SuccessFactors|%|100|Employees who completed the TNI / total eligible x 100|
|Learning and Development (15%)|Half-Yearly Training Calendar within timelines|25%|SuccessFactors|2, 1, 0|2|Calendar published before 1 April and 1 October; target 1 from April, 2 from October|
|Learning and Development (15%)|TNI Fulfilment Rate|25%|SuccessFactors|%|100|Training needs fulfilled / total training needs identified x 100|
|Learning and Development (15%)|Level 1 Feedback on Training Programs|25%|SuccessFactors|% (as shown)|80|Level 1 feedback shared on a scale of 1 to 5|
|Organizational Effectiveness (10%)|Percentage of employees covered (role and skill mapping)|100%|SuccessFactors|%|100|Employees with skill and proficiency mapped to role / total employees in scope x 100|
|Talent Management (20%)|Talent Council - Top Talent Review|25%|Manual|1/0|1|Process adherence before 31 December (Yes/No and date); scored from December|
|Talent Management (20%)|IDPs Created for Top Talent|25%|Manual|% (as shown)|25|Count of IDPs created during the period (year to date)|
|Talent Management (20%)|PLI Assessment|25%|SuccessFactors|%|100|M3C and M4A employees who completed and received the PLI report / total M3C and M4A x 100|
|Talent Management (20%)|IDP Creation Rate for Target Employees|25%|SuccessFactors|%|100|Target employees who developed an IDP / total target employees x 100|
|Engagement / Wellness (10%)|Annual Health Check-up (AHC) Completion Rate|25%|MyHealth|%|100|Employees who completed AHC / total eligible x 100|
|Engagement / Wellness (10%)|Platform Adoption Rate|25%|Hi5Plus / HeeraPlus|%|80|Unique employees who logged in during the period / total active employees x 100|
|Engagement / Wellness (10%)|GPTW Survey Score|50%|Manual (GPTW)|Score|80|Trust Index score as published in the annual GPTW survey report|
|Retention (15%)|Overall Retention Rate|30%|SuccessFactors|%|100|Total retentions in the year / average headcount in the period x 100|
|Retention (15%)|Top Talent Retention Rate|40%|SuccessFactors|%|100|100% minus (regrettable exits at CPR 7 and above / average headcount at CPR 7 and above x 100)|
|Retention (15%)|Trainee Retention|30%|SuccessFactors|%|80|Trainees remaining after 3 years / total trainees onboarded|

## Appendix B: Additional reference architecture

### B.1 Should adopting

- **Alerts pipeline** (rate limit, deduplication, triage, severity, channel preferences, quiet hours, live push to the UI): the basis for the Unread feed and scorecard alerts.
- **Workflow engine with persisted runs:** the basis for Reports and multi-step skills, since runs survive restarts and stream progress. The reference ships workflows for performance review, comp refresh and org design, which map to HR skills.
- **Skills registry and agent overrides:** already exposed as API resources; extend them to the data-driven model in Section 6.
- **Audit log with PII redaction:** adopt, and extend with role, tool and approval fields.
- **Recipient gating on outbound email:** a working precedent for the policy engine, where a send is refused unless the recipient is a known person.
- **Act as me drafts:** drafts for human review and send, which matches the Approvals pattern.
- **Conversational onboarding** that drafts the company profile for the user to edit and commit.
- **Roster-driven access control** for chat channels.
- **Prompt caching rules:** no dynamic content in cached blocks, and tool lists sorted by name. With a Tool Registry, each agent's tool list must be stable and sorted per request or caching degrades.