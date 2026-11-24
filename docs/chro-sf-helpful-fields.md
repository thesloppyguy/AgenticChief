# CHRO dashboard — helpful SuccessFactors fields

Exhaustive list of fields from `SuccessFactor Fields List.xlsx` that help the Group CHRO
dashboard (scorecard, IC drill-down, workforce pulse, Copilot). Production SF access is
**only** this field list; scorecard KPIs are computed or extrapolated from these.

Duplicate portlets (e.g. Certifications vs Certifications Licenses, Performance History
Portlet vs SM) are listed once. Development Centre child `Name` / `Score` / `Category`
rows are listed once (they repeat per competency in the source sheet).

---

## 1. Org slice & population (Job Info)

| Field | Use on CHRO dashboard |
|---|---|
| `IC` | Primary slice for every IC scorecard tile, Group vs IC comparison, filters |
| `Legal Entity` | Fallback org key when IC is missing; legal-entity headcount views |
| `L&T Group of Companies` | Group-level attribution / holding structure filters |
| `Country` | Geo breakdown of headcount, exits, training |
| `Strategic Business Group` | Drill below IC (SBG heatmaps) |
| `Business Unit` | BU-level scorecard / pulse breakdown |
| `Segment` | Segment-level workforce views |
| `Cluster` | Cluster-level workforce views |
| `Department / Projects` | Department headcount, attrition, skill coverage |
| `Base Location` | Location risk / mobility / site concentration |
| `Position` | Role inventory; critical-role and vacancy context |
| `Position Entry Date` | Time-in-role; flight-risk / stagnation signals |
| `Time In Position` | Same as above (precomputed tenure in role) |
| `Immediate Supervisor` | Manager span, manager-linked attrition, feedback proxies |
| `Job Function` | Function-level skill and retention cuts |
| `Job Sub Function` | Finer function taxonomy for skill coverage |
| `Job Code` | Join key to Job Classification; role–skill denominator |
| `Job Title` | Human-readable role labels on drill-downs |
| `Grade / Cadre` | Top-talent (CPR 7+) set; talent retention; IDP target pop |
| `Band` | Alternate / parallel talent banding |
| `Equivalent Grade` | Normalize cadres across ICs for Group compares |
| `Joining Grade` | Entry-level vs promoted talent analysis |
| `Employment Type` | Eligible population; trainee vs regular; FTE mix |
| `Appointment Type` | Trainee / FTC / regular identification |
| `Employee Group` | Eligibility filters for performance / L&D KPIs |
| `Contract/Training End Date` | Trainee & FTC cohort windows |
| `Time in Company` | Tenure bands on retention and pulse |
| `Event Reason` | Why job-info changed (promo, transfer, exit) — movement analytics |
| `Expected Joining Date` | Pipeline / joining lag (TA context if SF used) |
| `Notice Period (Months)` | Exit timing / notice compliance narratives |

---

## 2. Hire, tenure, exit (Employment Info)

| Field | Use on CHRO dashboard |
|---|---|
| `Hire Date` | Headcount start; new-hire cohorts; retention denominators |
| `Joining Date` | Same cohort logic (prefer when Hire Date incomplete) |
| `Original Start Date` | Rehire / prior service; tenure continuity |
| `Service Date` | Service-based eligibility and tenure |
| `Number of Years in Company` | Tenure bands without recomputing from dates |
| `Current L&T Experience YY/MM` | L&T-specific tenure for Group views |
| `In Cadre Experience YY/MM` | Time in current cadre (top-talent stability) |
| `Trainee Experience in YY/MM` | Trainee retention KPI |
| `Last Promotion Date` | Promotion velocity; talent movement pulse |
| `Confirmation Date` | Probation → confirmed pipeline |
| `Date of Retirement` | Retirement risk / succession exposure |
| `Separation Date` | Overall & top-talent retention numerators |
| `Payroll End Date` | Alternate exit boundary when Separation Date missing |
| `OK to Rehire` | Soft signal for regrettable vs non-regrettable exit quality |

---

## 3. Resignations & exit reasons (Resignation Request)

| Field | Use on CHRO dashboard |
|---|---|
| `Date Of Resignation` | When exit process started (leading indicator vs LWD) |
| `Approved Last Working Date` | Period bucketing for retention KPIs |
| `Requested Relieving Date` | Early-exit / notice-shortening patterns |
| `Notice Period Last Date as Per Policy` | Policy vs actual relieving gap |
| `Resignation Reason` | Regrettable-exit classification for top-talent retention |
| `Grade` | Exit grade mix (was exit in CPR 7+?) |
| `Department` | Attrition by department |
| `Location` | Attrition by location |
| `Date of Joining` | Tenure at exit without joining Employment join |
| `Exit Interview Required` | Exit-interview coverage pulse |

---

## 4. Cadre / top talent (Cadre History)

| Field | Use on CHRO dashboard |
|---|---|
| `Event Date` | When cadre changed — talent movement timeline |
| `Event Reason` | Why cadre changed (promo, correction) |
| `Previous Cadre` | Inflow/outflow of CPR bands |
| `Current Cadre` | CPR 7+ population for top-talent retention & IDP targets |
| `Job Title` | Role at cadre event for succession narratives |

---

## 5. Performance cycle proxies (Performance History + Rating PLR)

Use either Portlet or SM (same concepts). Rating PLR adds dated rating rows.

| Field | Use on CHRO dashboard |
|---|---|
| `AssessmentYear` / `Assessment Year` | Tie ratings to FY for KRA / mid-term / PPW proxies |
| `MVGRating` / `MVG Rating` / `MVG Actual Rating` | Performance evidence; KRA submitted proxy if dated |
| `Letter MVG rating` | Published rating letter — stronger “cycle completed” signal |
| `RatingDescription` / `Rating Description` | Label bands on talent/performance drill-downs |
| `CPRating` / `CP Rating` | Potential / CP axis for talent views; mid-term proxy |
| `PDRRating` / `PDR Rating` / `PDR Rating (if applicable)` | PDR completion / mid-term proxy |
| `RemarksSuccession` / `Remarks for Succession Planning (Role Enhancements)` | Succession Copilot narratives |
| `Remarks` | Free-text context on performance exceptions |
| `effectiveStartDate` (Rating PLR) | Date gate for KRA (≤30 Jun), mid-term (≤31 Dec), PPW (before 1 Apr) |

---

## 6. PLI / assessment proxy (Development Centre)

| Field | Use on CHRO dashboard |
|---|---|
| `Year of Attending` | FY filter for `pli_assessment` completions |
| `From Date` / `To Date` | Period precision for DC attendance |
| `DC Type` | Distinguish PLI-like assessments from other DC events |
| `DC Score` | Completion + outcome; weak proxy input for L1-like scores |
| `DC Category` | Segment assessment types on drill-down |
| `Name` (competency) | Competency covered — skill / PLI detail |
| `Score` (competency) | Per-competency score; weak `l1_feedback` / quality proxy |
| `Category` (competency) | Group competencies on talent charts |

---

## 7. Role & skills (Job Classification, Job Function, Subfunction, Language, Certs)

| Field | Use on CHRO dashboard |
|---|---|
| `Job Code` | Role key for `role_skill_coverage` denominator |
| `Job Title` | Display name for role coverage tables |
| `Pay Grade` | Grade on role taxonomy; align with cadre maps |
| `Job Function` | Function rollups of skill coverage |
| `Employee Class` | Include/exclude classes from in-scope population |
| `Is Full Time Employee` | FTE-only skill coverage option |
| `Regular/Temporary` | Scope filter (exclude temps if needed) |
| `defaultJobLevel` | Level-based skill expectations |
| `Job Function ID` / `Name` / `Description` / `Status` | Function master for org effectiveness |
| `Parent Job Function` / `Job Function Type` | Hierarchy for rollups |
| `Job Sub Family Code` / `Job Sub Family Name` | Finer role family for coverage |
| `Language` | Skill mapped flag (any language row ⇒ mapped) |
| `Speaking Proficiency` | Proficiency depth for quality of mapping |
| `Reading Proficiency` | Same |
| `Writing Proficiency` | Same |
| `Certification/Licence` | Skill mapped flag via credentials |
| `Description` | Cert detail on employee/role drill-down |
| `Institution` | Quality / vendor mix of credentials |
| `Certified Date` | Mapping freshness in period |
| `Certificate Valid Upto` | Expired cert ⇒ not counted as covered |
| `Certification Type` | Filter professional vs mandatory certs |
| `Company Sponsored` | L&D investment vs self-driven skills |

---

## 8. L&D / TNI / calendar proxies (Courses + leadership programs)

| Field | Use on CHRO dashboard |
|---|---|
| `Course Name` | Distinct training catalogue; TNI fulfilment detail |
| `Institution Name` | Provider mix |
| `Type` | Classify needs identified vs fulfilled |
| `Length` | Training volume / effort proxies |
| `Date Completed` | `tni_fulfilment`, training-calendar half-year evidence, continuous-feedback touchpoints |
| `name` / `institution` / `year` (Seven Step, Core Dev, Project Management programs) | Leadership-dev evidence for TNI, IDP proxy, calendar activity |

---

## 9. IDP / development evidence (assignments, mobility, designated)

| Field | Use on CHRO dashboard |
|---|---|
| `startDate` / `endDate` / `project` / `description` (Special Assignments) | IDP proxy; continuous-feedback touchpoints |
| `startDate` / `endDate` / `job-title` / `jobFunction` / `departmentProject` (Work Experience Within Company) | Internal mobility; touchpoints; succession stories |
| `Willing to Relocate` / `Region Desired` (Geographic Mobility) | Mobility pool for succession pulse |
| `Designated Employee Flag` / `Category` | Critical-role / IDP target population |
| `Date of becoming Designated Employee` / `Date of cessation as Designated Employee` | When critical-role set applies |

---

## 10. Promotions & internal moves

| Field | Use on CHRO dashboard |
|---|---|
| `effectiveStartDate` (Promotion) | Promotion timing in FY |
| `Promotion ( only July / Jan Promotion )` | Promo cycle adherence |
| `Promoted Grade` / `Promoted Band` / `Previous Grade` | Talent progression vs cadre history |
| `Target IC` / `Target SBG` / `Target BU` / `Target Location` / `Target Position ID` (Transfer) | Cross-IC movement; headcount attribution |
| `Date of joining at the new location` / `Your Role in the New Assignment` | Transfer completion; role change narratives |
| `Deputation Reason` / `DeputationType` / `Deputation Start Date` / `Deputation End Date` | Temporary IC moves; headcount caveats |
| `Deputed IC` / `Deputed SBG` / `Deputed Department/Project` | Where headcount should count during deputation |

---

## 11. FTC / contract assessment (optional talent signal)

| Field | Use on CHRO dashboard |
|---|---|
| `IC` / `Business Unit` / `Joining Date` / `Band` / `Pay Grade` | FTC population filters |
| `Contract End Date` | FTC runway / extension risk |
| `IS Overall Rating` | Weak L1 / quality proxy; FTC renewals |
| `Recommended for - by IS` / `Recommended for - by DH` | Conversion / extension decisions |

---

## 12. Exit interview (retention Copilot — not scorecard math)

| Field | Use on CHRO dashboard |
|---|---|
| `Business Unit / Department` / `Designation` | Exit mix charts |
| `Date of Joining` / `Date of Separation` / `Tenure in L&T` | Tenure-at-exit distribution |
| `What triggered your decision to leave L&T (HR Input)` / `What was the trigger for your decision to leave L&T` | Root-cause themes for Copilot |
| `Compensation` / `Brand` / `Role` / `Work Culture` | Reason-code rollups (regrettable insight) |
| `Would you recommend your friends to join L&T` | eNPS-like exit signal |
| `Given an opportunity, would you like to rejoin L&T in future?` | Boomerang / brand health |

---

## 13. Roster / identity (People model — minimal)

| Field | Use on CHRO dashboard |
|---|---|
| `P.S. Number` | Stable employee key across sheets |
| `First Name` / `Last Name` / `Name as per Aadhaar / Full Name` | People / approvals / drill-down labels |
| `Gender` | Diversity slices (if product shows them) |
| `Email Address` / `Is Primary` | Org roster, notifications, People directory |

---

## 14. Wellness context only (AHC KPI is MyHealth)

| Field | Use on CHRO dashboard |
|---|---|
| `Date of AHC` | Optional wellness pulse cross-check (not official AHC KPI) |
| `Hospital Name` | AHC delivery footprint (context only) |

---

## How these feed the 14 SF scorecard KPIs

| KPI | Primary fields |
|---|---|
| `overall_retention` | `IC`, `Hire Date`/`Joining Date`, `Separation Date`, `Approved Last Working Date` |
| `top_talent_retention` | `Grade / Cadre`/`Band`/`Current Cadre`, `Resignation Reason`, separation dates |
| `trainee_retention` | `Employment Type`/`Appointment Type`/`Trainee Experience`/`Contract/Training End Date`, hire/separate |
| `pli_assessment` | `Grade / Cadre` (M3C/M4A), Development Centre dates + `DC Score` |
| `role_skill_coverage` | `Job Code`, Language Skills, Certifications (+ validity) |
| `tni_employees` | Courses / DC / leadership program presence in FY |
| `tni_fulfilment` | Courses `Date Completed` (+ program `year`) vs opened activity |
| `kra_submission` | Performance History / Rating PLR + `effectiveStartDate` ≤ 30 Jun |
| `mid_term_review` | Ratings / CP·PDR + date ≤ 31 Dec |
| `idp_creation_rate` | DC / Courses / Special Assignments / programs for target cadre or Designated Employee |
| `training_calendar` | Course/program activity in Apr–Sep and Oct–Mar (IC-level 0/1/2) |
| `ppw_on_time` | Share with FY Performance History / Rating before 1 Apr (IC-level 0/1) |
| `l1_feedback` | DC competency `Score` or FTC `IS Overall Rating` → 1–5 scale |
| `continuous_feedback` | Count of Courses + assignments + transfers/deputations + rating updates per employee |

---

*Derived from `SuccessFactor Fields List.xlsx` for AgenticChief CHRO dashboard planning. Full include/exclude inventory: [chro-successfactors-fields.md](./chro-successfactors-fields.md).*
