# The CHRO Copilot for an L&T-shaped group

*A guide for the Group CHRO and the HR leadership team. No code. The companion document,
[backend.md](./backend.md), explains how it is built.*

---

## 1. The problem this solves

L&T is not one company. It is a holding structure over many independent companies — LTIMindtree, L&T
Technology Services, L&T Finance, L&T Realty, L&T Metro Rail and dozens more — each with its own HR
function, its own hiring market, its own HRIS tenant and its own definition of a "good" quarter. The
reference configuration in this system is **88 independent companies (ICs)**.

Today a Group CHRO's view of HR across that estate is assembled by hand: a workbook per IC, a monthly
chase for submissions, a consolidation that is stale the day it lands, and no way to ask a follow-up
question without starting the chase again.

This platform replaces that cycle with a system of record:

- **One Group HR score**, built from the same 7 pillars and 23 sub-KPIs for every IC.
- **Computed, not estimated.** Every number comes from deterministic code against stored data. The AI
  explains the numbers; it never produces them.
- **Drillable to the source.** Group → pillar → sub-KPI → IC → the raw counts it was calculated from and
  which system they came from.
- **Governed.** Anything with a consequence — publishing a report, emailing an IC, changing the scoring
  rules — needs a second named human to approve it.

## 2. What the score actually is

### The 7 pillars

| Pillar | Weight in the Group score |
|---|---|
| Talent Management | 20% |
| Talent Acquisition | 15% |
| Performance Management | 15% |
| Learning & Development | 15% |
| Retention | 15% |
| Organizational Effectiveness | 10% |
| Engagement / Wellness | 10% |

23 sub-KPIs sit under those pillars, each weighted within its pillar.

### How a number becomes a score

Each sub-KPI is scored as a percentage of its target:

- Normally: **achievement ÷ target × 100**.
- For the two where lower is better — Time to Fill and Cost per Hire — it flips: **target ÷ achievement
  × 100**.

A pillar is the weighted average of its sub-KPI scores. The IC's overall score is the weighted average of
its 7 pillars. The Group score is built the same way, from Group-level achievements.

**Status:** 90 and above is green (on track), 75 to just under 90 is amber (needs attention), below 75 is
red (off track). The band is applied to the unrounded score, so an IC showing "90.0" can legitimately be
amber at 89.96 — and the drill-down will show you that.

### Worked example — Talent Acquisition at one IC

| Sub-KPI | Target | Achieved | Score |
|---|---|---|---|
| Offer to joining ratio | 100% | 88% | 88.0 |
| Time to fill *(lower is better)* | 60 days | 72 days | 83.3 |
| New hire retention (12m) | 100% | 91% | 91.0 |
| Cost per hire *(lower is better)* | ₹60,000 | ₹54,000 | 111.1 |

All four carry equal weight within the pillar, so the pillar scores **93.4 — green**.

Note Cost per Hire scoring 111: by default scores are **not capped at 100**, so genuine outperformance
offsets a weak KPI elsewhere. If you would rather it didn't, a score cap is one of the rules you can
change (§7).

### Why "missing" never means zero

This is the single most important design decision in the product, and the one that most often differs
from a hand-built workbook.

If an IC has no value for a KPI, that KPI is **left out and the remaining weights are rescaled**. It is
never scored as zero. Scoring a blank as zero punishes an IC for a broken integration, and once that is
in a Group average it is almost impossible to see.

Take the same pillar, but Cost per Hire never arrived:

| | |
|---|---|
| Scored on | 3 of 4 KPIs (75% of the pillar's weight) |
| Pillar score | **87.4 — amber** |

The score moved because the evidence changed, and the screen tells you that it was computed on 75%
coverage. You are never shown a confident number without being shown what it rests on.

Three different things can keep a KPI out, and the system keeps them strictly apart:

| Shown as | What it means | Whose problem it is |
|---|---|---|
| **Not yet due** | It isn't due this point in the fiscal year | Nobody's. Everything is on schedule. |
| **No source** | No connected system supplies this KPI at all, so nobody *can* submit it | Group IT / platform admin — a connection gap |
| **Missing** | A connected system should have it and returned nothing | That IC's HR lead |

That distinction is enforced right through to the Copilot's language: it will not tell you an IC failed
to submit something that no system in the estate is capable of producing.

### Fiscal year and due dates

The year runs **April to March**. Deadline KPIs are only scored from their due month:

- KRA submission — from **June**
- Mid-term review and Top Talent Review — from **December**
- Training calendar — target of 1 from **April**, rising to 2 from **October**

So a December Group score is built on more KPIs than a July one, and the coverage figure moves with it.

### The Group number, and one exception

For almost every KPI, the Group achievement is the **simple average of the IC achievements** — each IC
counts once, matching the original Excel prototype.

The exception is **Cost per Hire**, which is computed as *total recruitment cost ÷ total hires* across the
group. Averaging per-IC ratios would let an IC that made 8 hires move the Group number as much as one
that made 2,000.

## 3. Where the data comes from

**19 of the 23 sub-KPIs are pulled from source systems:**

| System | KPIs it supplies |
|---|---|
| SAP SuccessFactors | 14 — performance, L&D, org effectiveness, talent management, retention |
| PeopleStrong / Skima AI | 3 — offer-to-joining, time to fill, new-hire retention |
| MyHealth | 1 — annual health check completion |
| Hi5Plus / HeeraPlus | 1 — platform adoption |

**4 are entered by hand**, monthly, by an IC's HR editor on the Manual Inputs page: Cost per Hire (cost
and hires), Top Talent Review (yes/no plus date), IDPs created year-to-date, and GPTW score. Every manual
edit is kept with its old value, its new value, who made it and when.

Two guarantees worth knowing:

1. **An automated pull never overwrites a number a person entered.** If HR at an IC corrected a figure,
   the next nightly sync leaves it alone.
2. **Every stored value keeps its raw counts.** The system doesn't store "88%" — it stores 44 joined of
   50 offers, which system said so, and when. That is why a drill-down can always answer "why?".

### Right now, the data is synthetic

Until real tenants are connected, the platform generates realistic HR data for each IC and serves it over
HTTP endpoints shaped exactly like the real systems — so the entire pipeline is genuinely exercised, not
faked at the top. **Anything synthetic is flagged as such on screen and in every report.** You will never
mistake a demo number for a real one.

## 4. A month in the life

**Overnight, automatically.** Scheduled jobs pull each source for the current period, convert raw counts
into KPI values with full lineage, then re-evaluate every IC's status.

**When something turns red.** An alert is raised for any IC — or the Group — that *changed* to red this
month, and for any source whose ingestion failed. An IC that was already red last month doesn't re-alert;
this is a list of what changed, not a wall of noise. You set your own minimum severity, mute categories,
and set quiet hours in your timezone. Alerts arrive live in the app.

**During the month.** You open the dashboard: the Group score with its status, every IC ranked, and the
7 pillars. Click a pillar to see its sub-KPIs, each IC's achievement, the target in force this month,
and exactly who was excluded and why. Click an IC for its own scorecard. Export to Excel or CSV at any
point.

**Ask instead of hunt.** The Copilot sits beside the dashboard (§5).

**Month end.** The monthly leadership review runs as a four-step job: collect this month's and last
month's scorecards → gather source lineage and a census of where every value came from → build the
comparisons, movers and exceptions → draft commentary.

That last step has a safeguard: **the AI's narrative is checked number by number against the computed
report, and is only kept if every figure matches.** An invented statistic doesn't get softened — it gets
dropped.

**Publishing.** You review the draft and propose publication. **A second admin approves it.** On
approval, it becomes an immutable snapshot — content-hashed, impossible to edit or delete, exportable as
PDF or Markdown. If the scoring rules change next quarter, that snapshot still shows exactly the numbers
and the rule version it was published under.

## 5. Asking the Copilot

The Copilot answers from the scoring service, from published reports and from documents you have
uploaded. It has no independent knowledge of your numbers and cannot compute any.

Things it answers well:

- *"What is the Group score this month, and what moved since last month?"*
- *"Why is L&T Realty amber?"*
- *"Show me the 10 weakest ICs on Retention and what's dragging them."*
- *"Which ICs are missing Learning & Development data for this period?"*
- *"What did last month's leadership review say about Talent Acquisition?"*
- *"What does our mobility policy say about internal transfers?"* (searching uploaded documents, with the
  document cited)

What it will always do: state the coverage behind a number, name what was excluded and why, distinguish
fact from inference, and cite the source of every figure.

What it will **never** do: calculate a number itself, call a missing value zero, describe a `no_source`
gap as an IC's failure, show you an IC you aren't authorised for, or follow an instruction buried inside
an uploaded document.

It also remembers, per user, what you have decided or asked for in earlier sessions — private to you,
expiring, visible on a Memories page, individually deletable, and switchable off entirely. Those memories
are treated as possibly-stale context; it will not quote a figure from them as current.

### It proposes; it does not act

The Copilot can draft an action — "remind these 4 ICs to submit GPTW for this month" — but all that does
is **file an approval request**. It will say "proposed", give you the request ID, and stop. A human
approves it, and the backend, not the model, decides whether the action is even permissible.

## 6. Governance: who can do what

**Roles**

| Role | Can |
|---|---|
| Viewer | See scorecards, reports, drill-downs and the Copilot, within their scope |
| Editor | The above, plus enter the 4 manual KPIs and upload documents |
| Admin | The above, plus connections, schedules, scoring rules, and approval decisions |

**Scope.** A sign-in can be restricted to specific ICs. An L&T Finance HR head sees L&T Finance; a Group
HR director sees everything. Restriction is enforced in the backend — not hidden in the UI, and not left
to the AI. A scoped user's "Group" view is explicitly marked as restricted so a divisional number is
never mistaken for the Group number.

**The approval rules.** Every consequential action goes through one policy:

1. Destructive actions are **always denied**. There is no override.
2. An action touching more than 5 ICs at once is denied as a bulk action.
3. An action touching an IC outside your scope is denied — and the message is deliberately vague about
   which ICs exist.
4. Group-wide actions (publishing, changing rules) require group-wide access to request *and* to approve.
5. **Nobody can approve their own request.**

The seven actions that exist: send a KPI reminder, save a scorecard snapshot, publish a monthly report,
publish a capability, publish a skill or agent, approve a KPI mapping, activate a new set of scoring
rules. That is the whole list. There is no eighth path.

Approvers see a prepared briefing before they decide — what changes, what depends on it, whether it is a
rollback — and requests that could never succeed are rejected before anyone is asked. Every decision is
recorded permanently, alongside a full audit log of who did what.

## 7. Changing the rules

Pillar weights, individual KPI weights and targets, the green/amber/red thresholds, whether scores cap at
100, how ICs with no data are treated in a Group average, and whether year-to-date KPIs are pro-rated —
all of these are **editable by an admin, not hard-coded**.

The flow is deliberately slow:

1. An admin drafts the change.
2. **Preview it against real data.** The whole scorecard is recomputed under the draft and diffed against
   the live rules — you see which ICs would change status *before* anything happens.
3. A **second** admin approves activation.

Invalid rule sets are refused outright: pillar weights that don't total 100%, a pillar whose KPI weights
no longer total 100%, an amber threshold above green, a score cap that would make green unreachable.

Every score and every report records which rule version produced it. **Changing the rules never
retroactively changes a published report.**

## 8. What it would take to run this on L&T's real data

The platform is built and tested; what remains is a connection and configuration exercise.

| # | Step | Owner |
|---|---|---|
| 1 | Replace the 88 placeholder ICs with the real L&T entity list and codes | Group HR + platform admin |
| 2 | Point the SuccessFactors integration at the real tenant — base URL, credentials by environment-variable name, and a mapping file per KPI | Group IT |
| 3 | Same for PeopleStrong/Skima, MyHealth and Hi5Plus | Group IT |
| 4 | Confirm the Talent Acquisition source split. The prototype sheet lists "PeopleStrong / Skima AI / SuccessFactors" together; all three TA KPIs currently sit on PeopleStrong. Moving one is a one-line change | Group HR |
| 5 | Confirm targets per KPI, and whether targets are uniform across ICs or should differ | Group HR |
| 6 | Decide: score cap on or off; minimum coverage before a status is shown; pro-rating for year-to-date KPIs | Group CHRO |
| 7 | Nominate editors per IC for the 4 manual KPIs, and at least two Group admins (four-eyes needs two) | Group HR |
| 8 | Choose an email or chat channel for approved reminders — approved messages currently queue, as no delivery channel is wired up | Group IT |
| 9 | Replace pasted sign-in tokens with L&T SSO | Group IT |
| 10 | Run one month in parallel against the existing workbook and reconcile | Group HR |

Two platform constraints worth flagging to IT before step 2: the system runs as a **single process on
SQLite**, which is sized for this workload but not horizontally scalable as-is; and the live adapters have
been verified against generated endpoints and mocks, **not yet against a real tenant** — step 2 is where
that gets proven.

## 9. The short version

> One Group HR score across every L&T independent company, computed by auditable code from the same 7
> pillars and 23 KPIs — never estimated by an AI. Missing data is excluded and declared, never silently
> scored as zero. You can drill from the Group number to the raw counts behind it, ask follow-up
> questions in plain English and get cited answers, and nothing consequential happens without a second
> named human approving it.
