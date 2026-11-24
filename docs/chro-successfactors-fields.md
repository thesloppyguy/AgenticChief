# CHRO SuccessFactors field inventory

Source: `SuccessFactor Fields List.xlsx` (62 sheets, ~1,036 fields) cross-checked against
`IC HR Scorecard 2.xlsx` and the AgenticChief SF source ownership (14 scorecard KPIs).

## Production constraint (read this first)

**Production SuccessFactors access is limited to the fields in `SuccessFactor Fields List.xlsx`.**
There is no separate Performance / Goals / Continuous Feedback / Learning / IDP API surface for
live data.

The mock OData KPI endpoints under `/mock-sources/successfactors/...` (and the stub generator)
exist for **simulation only**. Their field names (`Submitted`, `Eligible`, `AvgEntriesPerEmployee`,
etc.) are **not** available in production and must not be treated as a real SF contract.

For production, every SF-owned scorecard KPI must be **computed or extrapolated** from the EC
fields listed in this inventory, then stored as the usual period aggregates
(`companyCode` + `YYYY-MM` → numerator / denominator / value).

Confidence bands used below:

| Band | Meaning |
|---|---|
| **Direct** | Formula can be built from clear EC facts (hire, separate, cadre, trainee). |
| **Proxy** | Closest available EC signal; define the rule in mapping config and label lineage as extrapolated. |
| **Weak proxy** | No close EC analogue; use a documented heuristic or keep the KPI manual until a better signal exists. |

---

## Summary

| Bucket | Fields | Sheets with any |
|---|---:|---:|
| **Needed — must-have** (scorecard / SF KPIs) | 147 | 17 |
| **Needed — useful** (workforce, Copilot, org roster, mobility) | 78 | 18 |
| **Not needed** for CHRO | 811 | 50 |
| **Total in SF field list** | 1036 | 62 |

**Rough cut:** ~225 fields needed (~21%), ~811 not needed (~78%).

---

## SF-owned scorecard KPIs → extrapolation from this field list

| KPI key | Scorecard measure | Confidence | Extrapolate from (sheets / fields) |
|---|---|---|---|
| `overall_retention` | Overall Retention Rate | **Direct** | Job Info `IC` + Employment Info hire/separate + active headcount |
| `top_talent_retention` | Top Talent Retention Rate | **Direct** | Cadre History / `Grade / Cadre` / `Band` (CPR 7+) + Resignation Reason + Separation Date |
| `trainee_retention` | Trainee Retention | **Direct** | `Employment Type` / `Appointment Type` / `Trainee Experience` / `Contract/Training End Date` + hire/separate |
| `pli_assessment` | PLI Assessment (MyPLI) | **Proxy** | Development Centre (`Year of Attending`, `DC Type`, `DC Score`) filtered to M3C/M4A via Grade/Cadre/Band |
| `role_skill_coverage` | Role & skill mapping coverage | **Proxy** | Language Skills + Certifications (+ Job Code / Job Classification as role key) |
| `tni_fulfilment` | TNI Fulfillment Rate | **Proxy** | Courses `Date Completed` + leadership program sheets; “identified” ≈ employees with any course/dev activity opened in period |
| `tni_employees` | TNI for Employees | **Proxy** | Employee has ≥1 Courses / Development Centre / leadership-program row in the FY |
| `kra_submission` | KRA Submission Timeliness | **Proxy** | Performance History / Rating PLR row for `AssessmentYear` with date ≤ 30 Jun |
| `mid_term_review` | Mid-Term Review Timeliness | **Proxy** | Performance History ratings present for year with date ≤ 31 Dec (second touch / CP·PDR update) |
| `idp_creation_rate` | IDP Creation Rate | **Proxy** | Development evidence in period: DC / Courses / Special Assignments / leadership programs (target pop via Cadre or Designated Employee) |
| `training_calendar` | Half-yearly Training Calendar | **Weak proxy** | IC-level: distinct course activity in Apr–Sep ⇒ 1; also Oct–Mar ⇒ 2 (no publish flag exists) |
| `ppw_on_time` | Organising PPW within timelines | **Weak proxy** | IC-level: share of eligible employees with Performance History / Rating for FY dated before 1 Apr ⇒ 1/0 |
| `l1_feedback` | Level 1 Feedback on Training | **Weak proxy** | Development Centre competency `Score` (or FTC `IS Overall Rating`) scaled onto 1–5; no true L1 eval field |
| `continuous_feedback` | Continuous Feedback | **Weak proxy** | Count “manager/employee touchpoints” in period (Course completions + Special Assignments + internal moves + rating updates); treat mean touchpoints as `avg_entries_per_employee` |

KPIs **not** from SuccessFactors (unchanged): Talent Acquisition (PeopleStrong), Cost per Hire /
Top Talent Review / IDPs for top talent / GPTW (manual), AHC (MyHealth), Platform adoption (Hi5Plus).

---

## Fields needed for CHRO

### A. Must-have (scorecard / retention / talent / skills proxies)

#### Development Centre

| Field | Primary use |
|---|---|
| `Year of Attending` | Scorecard population, lineage, or talent/L&D evidence |
| `From Date` | Scorecard population, lineage, or talent/L&D evidence |
| `To Date` | Scorecard population, lineage, or talent/L&D evidence |
| `DC Type` | PLI / assessment proxy |
| `DC Score` | PLI completion / outcome |
| `DC Category` | Scorecard population, lineage, or talent/L&D evidence |
| `Name` | Scorecard population, lineage, or talent/L&D evidence |
| `Score` | Scorecard population, lineage, or talent/L&D evidence |
| `Category` | Scorecard population, lineage, or talent/L&D evidence |
| `Name` | Scorecard population, lineage, or talent/L&D evidence |
| `Score` | Scorecard population, lineage, or talent/L&D evidence |
| `Category` | Scorecard population, lineage, or talent/L&D evidence |
| `Name` | Scorecard population, lineage, or talent/L&D evidence |
| `Score` | Scorecard population, lineage, or talent/L&D evidence |
| `Category` | Scorecard population, lineage, or talent/L&D evidence |
| `Name` | Scorecard population, lineage, or talent/L&D evidence |
| `Score` | Scorecard population, lineage, or talent/L&D evidence |
| `Category` | Scorecard population, lineage, or talent/L&D evidence |
| `Name` | Scorecard population, lineage, or talent/L&D evidence |
| `Score` | Scorecard population, lineage, or talent/L&D evidence |
| `Category` | Scorecard population, lineage, or talent/L&D evidence |
| `Name` | Scorecard population, lineage, or talent/L&D evidence |
| `Score` | Scorecard population, lineage, or talent/L&D evidence |
| `Category` | Scorecard population, lineage, or talent/L&D evidence |
| `Name` | Scorecard population, lineage, or talent/L&D evidence |
| `Score` | Scorecard population, lineage, or talent/L&D evidence |
| `Category` | Scorecard population, lineage, or talent/L&D evidence |
| `Name` | Scorecard population, lineage, or talent/L&D evidence |
| `Score` | Scorecard population, lineage, or talent/L&D evidence |
| `Category` | Scorecard population, lineage, or talent/L&D evidence |

#### Job Info

| Field | Primary use |
|---|---|
| `Position` | Scorecard population, lineage, or talent/L&D evidence |
| `L&T Group of Companies` | Group vs IC attribution |
| `Legal Entity` | Org filter / headcount scope |
| `Country` | Scorecard population, lineage, or talent/L&D evidence |
| `IC` | Slice all KPIs by Independent Company |
| `Strategic Business Group` | Scorecard population, lineage, or talent/L&D evidence |
| `Business Unit` | Scorecard population, lineage, or talent/L&D evidence |
| `Segment` | Scorecard population, lineage, or talent/L&D evidence |
| `Cluster` | Scorecard population, lineage, or talent/L&D evidence |
| `Department / Projects` | Scorecard population, lineage, or talent/L&D evidence |
| `Immediate Supervisor` | Scorecard population, lineage, or talent/L&D evidence |
| `Job Function` | Scorecard population, lineage, or talent/L&D evidence |
| `Job Code` | Scorecard population, lineage, or talent/L&D evidence |
| `Job Sub Function` | Scorecard population, lineage, or talent/L&D evidence |
| `Job Title` | Scorecard population, lineage, or talent/L&D evidence |
| `Grade / Cadre` | Top talent / CPR banding |
| `Employment Type` | Active population; trainee vs regular |
| `Appointment Type` | Trainee / FTC identification |
| `Employee Group` | Eligible population filters |
| `Contract/Training End Date` | Trainee / FTC cohorts |
| `Band` | Top talent banding |
| `Time in Company` | Scorecard population, lineage, or talent/L&D evidence |
| `Joining Grade` | Scorecard population, lineage, or talent/L&D evidence |
| `Event Reason` | Scorecard population, lineage, or talent/L&D evidence |
| `Equivalent Grade` | Scorecard population, lineage, or talent/L&D evidence |

#### Employment Info

| Field | Primary use |
|---|---|
| `Hire Date` | Headcount, tenure, new-hire cohorts |
| `Original Start Date` | Scorecard population, lineage, or talent/L&D evidence |
| `Service Date` | Scorecard population, lineage, or talent/L&D evidence |
| `Number of Years in Company` | Scorecard population, lineage, or talent/L&D evidence |
| `Last Promotion Date` | Scorecard population, lineage, or talent/L&D evidence |
| `Joining Date` | Hire cohort / trainee start |
| `Trainee Experience in YY/MM` | Trainee retention |
| `In Cadre Experience YY/MM` | Scorecard population, lineage, or talent/L&D evidence |
| `Confirmation Date` | Scorecard population, lineage, or talent/L&D evidence |
| `Current L&T Experience YY/MM` | Scorecard population, lineage, or talent/L&D evidence |
| `Separation Date` | Retention numerators |
| `OK to Rehire` | Exit quality / regrettable filter aid |
| `Payroll End Date` | Scorecard population, lineage, or talent/L&D evidence |

#### Resignation Request

| Field | Primary use |
|---|---|
| `Date Of Resignation` | Scorecard population, lineage, or talent/L&D evidence |
| `Resignation Reason` | Regrettable vs non-regrettable exits |
| `Notice Period Last Date as Per Policy` | Scorecard population, lineage, or talent/L&D evidence |
| `Requested Relieving Date` | Scorecard population, lineage, or talent/L&D evidence |
| `Approved Last Working Date` | Exit timing in period |
| `Grade` | Scorecard population, lineage, or talent/L&D evidence |
| `Department` | Scorecard population, lineage, or talent/L&D evidence |
| `Location` | Scorecard population, lineage, or talent/L&D evidence |
| `Date of Joining` | Scorecard population, lineage, or talent/L&D evidence |

#### Job Classification

| Field | Primary use |
|---|---|
| `Job Code` | Scorecard population, lineage, or talent/L&D evidence |
| `Job Title` | Scorecard population, lineage, or talent/L&D evidence |
| `defaultJobLevel` | Scorecard population, lineage, or talent/L&D evidence |
| `Regular/Temporary` | Scorecard population, lineage, or talent/L&D evidence |
| `Employee Class` | Scorecard population, lineage, or talent/L&D evidence |
| `Is Full Time Employee` | Scorecard population, lineage, or talent/L&D evidence |
| `Pay Grade` | Scorecard population, lineage, or talent/L&D evidence |
| `Job Function` | Scorecard population, lineage, or talent/L&D evidence |

#### Certifications

| Field | Primary use |
|---|---|
| `Certification/Licence` | Role–skill coverage |
| `Description` | Scorecard population, lineage, or talent/L&D evidence |
| `Institution` | Scorecard population, lineage, or talent/L&D evidence |
| `Certified Date` | Scorecard population, lineage, or talent/L&D evidence |
| `Certificate Valid Upto` | Scorecard population, lineage, or talent/L&D evidence |
| `Company Sponsored` | Scorecard population, lineage, or talent/L&D evidence |
| `Certification Type` | Scorecard population, lineage, or talent/L&D evidence |

#### Certifications Licenses

| Field | Primary use |
|---|---|
| `Certification/Licence` | Role–skill coverage |
| `Description` | Scorecard population, lineage, or talent/L&D evidence |
| `Institution` | Scorecard population, lineage, or talent/L&D evidence |
| `Certified Date` | Scorecard population, lineage, or talent/L&D evidence |
| `Certificate Valid Upto` | Scorecard population, lineage, or talent/L&D evidence |
| `Company Sponsored` | Scorecard population, lineage, or talent/L&D evidence |
| `Certification Type` | Scorecard population, lineage, or talent/L&D evidence |

#### Performance History Portlet

| Field | Primary use |
|---|---|
| `AssessmentYear` | Scorecard population, lineage, or talent/L&D evidence |
| `MVGRating` | Performance history evidence |
| `RatingDescription` | Scorecard population, lineage, or talent/L&D evidence |
| `CPRating` | Performance / potential |
| `PDRRating` | Scorecard population, lineage, or talent/L&D evidence |
| `RemarksSuccession` | Scorecard population, lineage, or talent/L&D evidence |
| `Remarks` | Scorecard population, lineage, or talent/L&D evidence |

#### Performance History SM

| Field | Primary use |
|---|---|
| `Assessment Year` | Scorecard population, lineage, or talent/L&D evidence |
| `MVG Rating` | Performance history evidence |
| `Rating Description` | Scorecard population, lineage, or talent/L&D evidence |
| `CP Rating` | Performance / potential |
| `PDR Rating` | Scorecard population, lineage, or talent/L&D evidence |
| `Remarks for Succession Planning (Role Enhancements)` | Scorecard population, lineage, or talent/L&D evidence |
| `Remarks` | Scorecard population, lineage, or talent/L&D evidence |

#### Job Function

| Field | Primary use |
|---|---|
| `Job Function ID` | Scorecard population, lineage, or talent/L&D evidence |
| `Name` | Scorecard population, lineage, or talent/L&D evidence |
| `Description` | Scorecard population, lineage, or talent/L&D evidence |
| `Status` | Scorecard population, lineage, or talent/L&D evidence |
| `Parent Job Function` | Scorecard population, lineage, or talent/L&D evidence |
| `Job Function Type` | Scorecard population, lineage, or talent/L&D evidence |

#### Cadre History

| Field | Primary use |
|---|---|
| `Event Date` | Scorecard population, lineage, or talent/L&D evidence |
| `Event Reason` | Scorecard population, lineage, or talent/L&D evidence |
| `Previous Cadre` | Cadre movement / top talent history |
| `Current Cadre` | CPR 7+ population |
| `Job Title` | Scorecard population, lineage, or talent/L&D evidence |

#### Courses

| Field | Primary use |
|---|---|
| `Course Name` | TNI fulfilment / L&D evidence |
| `Institution Name` | Scorecard population, lineage, or talent/L&D evidence |
| `Type` | Scorecard population, lineage, or talent/L&D evidence |
| `Length` | Scorecard population, lineage, or talent/L&D evidence |
| `Date Completed` | Training completion in period |

#### Rating PLR Dataupdate

| Field | Primary use |
|---|---|
| `effectiveStartDate` | Scorecard population, lineage, or talent/L&D evidence |
| `MVG Actual Rating` | Performance ratings |
| `Letter MVG rating` | Scorecard population, lineage, or talent/L&D evidence |
| `CP Rating` | Performance / potential |
| `PDR Rating (if applicable)` | Scorecard population, lineage, or talent/L&D evidence |

#### Language Skills

| Field | Primary use |
|---|---|
| `Language` | Role–skill coverage |
| `Speaking Proficiency` | Skill proficiency mapping |
| `Reading Proficiency` | Scorecard population, lineage, or talent/L&D evidence |
| `Writing Proficiency` | Scorecard population, lineage, or talent/L&D evidence |

#### Core Development Program

| Field | Primary use |
|---|---|
| `name` | Scorecard population, lineage, or talent/L&D evidence |
| `institution` | Scorecard population, lineage, or talent/L&D evidence |
| `year` | Scorecard population, lineage, or talent/L&D evidence |

#### Project Management Program

| Field | Primary use |
|---|---|
| `name` | Scorecard population, lineage, or talent/L&D evidence |
| `institution` | Scorecard population, lineage, or talent/L&D evidence |
| `year` | Scorecard population, lineage, or talent/L&D evidence |

#### Seven Step Leadership Developme

| Field | Primary use |
|---|---|
| `name` | Scorecard population, lineage, or talent/L&D evidence |
| `institution` | Scorecard population, lineage, or talent/L&D evidence |
| `year` | Scorecard population, lineage, or talent/L&D evidence |

### B. Useful (workforce pulse, Copilot narratives, org roster, mobility)

Not required to compute the 14 SF scorecard KPIs today, but valuable for Home pulse,
succession narratives, and seeded People/Departments.

#### Exit Interview New

- `Business Unit / Department`
- `Designation`
- `Date of Joining`
- `Date of Separation`
- `Tenure in L&T`
- `Would you recommend your friends to join L&T`
- `Given an opportunity, would you like to rejoin L&T in future?`
- `What triggered your decision to leave L&T (HR Input)`
- `What was the trigger for your decision to leave L&T`
- `Compensation`
- `Brand`
- `Role`
- `Work Culture`

#### FTC Assesment process

- `IC`
- `Business Unit`
- `Joining Date`
- `Band`
- `Pay Grade`
- `IS Overall Rating`
- `Recommended for - by IS`
- `Recommended for - by DH`
- `Contract End Date`

#### Deputation Details

- `Deputation Reason`
- `DeputationType`
- `Deputation Start Date`
- `Deputation End Date`
- `Deputed IC`
- `Deputed SBG`
- `Deputed Department/Project`

#### Transfer request

- `Target Position ID`
- `Target IC`
- `Target SBG`
- `Target BU`
- `Target Location`
- `Date of joining at the new location`
- `Your Role in the New Assignment`

#### Job Info

- `Position Entry Date`
- `Time In Position`
- `Base Location`
- `Expected Joining Date`
- `Notice Period (Months)`

#### Promotion details

- `effectiveStartDate`
- `Promotion ( only July / Jan Promotion )`
- `Promoted Grade (only July / Jan Promotion)`
- `Promoted Band (only July / Jan Promotion)`
- `Previous Grade (only July / Jan Promotion)`

#### Work Experience Within Company

- `startDate`
- `endDate`
- `job-title`
- `jobFunction`
- `departmentProject`

#### Designated Employee

- `Designated Employee Flag`
- `Category`
- `Date of becoming Designated Employee`
- `Date of cessation as Designated Employee`

#### Job Subfunction New

- `Job Sub Family Code`
- `Job Sub Family Name`
- `Status`
- `Description`

#### Personal Info

- `First Name`
- `Last Name`
- `Name as per Aadhaar / Full Name`
- `Gender`

#### Special Assignments Projects

- `startDate`
- `endDate`
- `project`
- `description`

#### Annual Health Chek up

- `Date of AHC`
- `Hospital Name`

#### Email Information

- `Email Address`
- `Is Primary`

#### Geographic Mobility

- `Willing to Relocate`
- `Region Desired`

#### Job relationships

- `Relationship Type`
- `Name`

#### Biographic info

- `P.S. Number`

#### Employment Info

- `Date of Retirement`

#### Resignation Request

- `Exit Interview Required`

---

## Fields not needed for CHRO

These are HR ops, payroll, benefits, clinical health, PII, documents, or country address
variants. Safe to exclude from CHRO ingestion and mappings.

### Entire sheets — exclude

| Sheet | Field count | Why exclude |
|---|---:|---|
| Sheet9 | 264 | Country-specific address fields |
| Education New | 27 | Recruiting / HR ops education history |
| Previous Employment | 27 | Pre-hire CV history |
| Pay Master Update | 23 | Compensation components / payroll |
| CLCS Request Form | 22 | Internal HR request workflow |
| Dependent Info | 18 | Dependent PII |
| Health details | 18 | Clinical / disability medical detail |
| Dislocation Allowance | 15 | Payroll allowance |
| Bond Details | 14 | Payroll / bond recovery ops |
| Loans | 14 | Payroll loans |
| SOHRA | 14 | Allowance / relocation ops |
| Work Permit | 14 | Immigration / compliance docs |
| Accommodation | 13 | Housing benefits |
| Recurring Deductions | 11 | Payroll deductions |
| Emergency Contact | 8 | Emergency PII |
| Fixed tenure | 7 | Pay component schedule |
| PL Quota 2 | 7 | Leave / quota admin |
| Phone info | 7 | Personal contact PII |
| Safty Incident | 7 | EHS ops (note: sheet spelling) |
| Comp Info, Pay Component | 6 | Compensation structure |
| Hiring Pending Documents | 5 | Onboarding document checklist |
| Insurance master | 5 | Benefits admin |
| National ID Details | 5 | PII / identity docs |
| Professional Membership | 4 | Optional CV data; not scorecard |
| Employee Documents | 3 | Document store |
| Reward Letter | 3 | Letter generation |
| Annual Performance Letter | 2 | Letter generation |
| Education Documents | 2 | Document store |
| Employee Experience Document | 2 | Document store |
| Transfer Letter | 2 | Document generation |

### Partial sheets — fields to exclude

On sheets that also have needed fields, drop the remainder:

#### Exit Interview New (51 not needed)

- `User`
- `Start Date`
- `Name of Immediate Supervisor`
- `Name of Department Head`
- `It was great pride for me being associated with L&T`
- `I have received enough opportunities for career development & enhancement`
- `I have received enough learning opportunities`
- `I was not recognized for my achievements`
- `I was happy with the role which I was handling`
- `I was able to make impactful contributions in my role`
- `I felt I was doing meaningful work`
- `There was no clarity about my career path and growth in the organization`
- `I was clearly informed about my roles and responsibilities`
- `My Superior made me feel inclusive while taking decision related to my work`
- `I was treated respectfully at work`
- `I was discriminated and treated unfairly by my manager`
- `My remuneration was commensurate with my capabilities, experience & performance`
- `My remuneration was in line with Industry Standards`
- `Benefits provided to me were commensurate with my position`
- `I was not rewarded adequately for my achievements`
- `I could learn from my peers as they were equally competent`
- `My colleagues played a pivotal role in my achievements in the organization`
- `I shared healthy relationships with my peers`
- `My colleagues were not supportive at work`
- `Trust & Transparency`
- `Work life balance`
- `Rewards & Recognition`
- `Dignity & Respect`
- `Ownership & Empowerment`
- `Culture of Caring`
- `Learning Opportunities`
- `Leadership / Management support`
- `What do you like the most about L&T(4000 characters limit)`
- `What steps we could have taken to improve employee retention(4000 characters limit)`
- `Please specify`
- `Name of the New Company`
- `CTC in the New Company`
- `Designation in the New Company`
- `Nature of work in the New Company`
- `How was his/ her experience with L&T - Relationship with superiors / peers / subordinates (4000 characters limit)`
- `How was his/ her experience with L&T - Working environment (4000 characters limit)`
- `How was his/ her experience with L&T - Compensation structure / facilities provided / perks (4000 characters limit)`
- `How was his/ her experience with L&T - Any other comment (4000 characters limit)`
- `If he / she were to join back, what would be his / her expectations from L&T? (4000 characters limit)`
- `Name of Interviewer`
- `Designation of Interviewer`
- `PS No of Interviewer`
- `Please share details`
- `INPUTS FILLED BY HR AS ON`
- `Others (please describe in few words)`
- `Name of Reporting Manager`

#### FTC Assesment process (44 not needed)

- `externalCode`
- `effectiveStartDate`
- `Display Name`
- `Job Title`
- `Legal Entity`
- `SBG`
- `Segment`
- `Cluster`
- `Department/Projects`
- `Immediate Supervisor`
- `Department Head`
- `Human Resource`
- `IS Rating`
- `IS Rating`
- `IS Rating`
- `IS Rating`
- `IS Rating`
- `IS Rating`
- `IS Rating`
- `IS Rating`
- `IS Rating`
- `NS Overall Rating`
- `DH Overall Rating`
- `Recommended for - by NS`
- `In case of Extension of Contract period, please enter duration of extension period(in MONTHS) in the Box provided across`
- `IS Comments (4000 characters)`
- `NS Comments (4000 characters)`
- `DH Comments (4000 characters)`
- `IS Comments (4000 characters)`
- `IS Comments (4000 characters)`
- `IS Comments (4000 characters)`
- `IS Comments (4000 characters)`
- `IS Comments (4000 characters)`
- `IS Comments (4000 characters)`
- `IS Comments (4000 characters)`
- `IS Comments (4000 characters)`
- `IS Comments (4000 characters)`
- `HR Action in EC`
- `HR Comments (4000 characters)`
- `New Contract End Date (Only for Extension)`
- `Event Date (Only for Extension)`
- `Backdated (more than 3 days)`
- `Assessment From`
- `Assessment To`

#### Employment Info (23 not needed)

- `At Hire`
- `Previous Employment ID`
- `Employee's First Employment`
- `Offer Letter Number`
- `Reference Number`
- `Offer Letter Date`
- `Offer Letter Currency`
- `Extended Date of Retirement`
- `Interview Rating`
- `Overall Experience YY/MM`
- `YOR`
- `Previous L&T Experience YY/MM`
- `Previous Experience Outside L&T  YY/MM`
- `Previous L&T Experience (Input by HR)`
- `Previous Experience Outside L&T (Input by HR)`
- `Extended Probation Date`
- `Extended Training Date`
- `At Termination`
- `HR Comment for Blacklisting`
- `HR Inputs`
- `Rehire Import`
- `Committed PLR (In Offer Letter)`
- `Last Transfer Date`

#### Job Info (20 not needed)

- `Timezone`
- `Base Cost Center`
- `Deputed Location`
- `Deputed Cost Code`
- `Deputation Paid Overseas`
- `Location Group`
- `Office/Site`
- `Site/Office (NEW)`
- `Family Status`
- `Probationary Period End Date`
- `Extended Date of Retirement`
- `Expat Status`
- `Work Schedule`
- `Transfer Release Date`
- `DLA Exit Date`
- `DLA EXIT`
- `Deputation Flag`
- `Deputation Date`
- `End Date of Deputation`
- `Previous India Location`

#### Personal Info (14 not needed)

- `Title`
- `L&T Initials`
- `Middle Name`
- `Marital  Status`
- `Marital Status Since`
- `Number Of Children`
- `Nationality`
- `Domicile State`
- `Father's Name`
- `Religion`
- `Caste Code`
- `Blood group`
- `Attachment`
- `PQ / NPQ`

#### Transfer request (12 not needed)

- `effectiveStartDate`
- `Transfer Proposal Number`
- `HR Approval`
- `Source Job Code & Description`
- `Target JobCode & Description`
- `Remarks`
- `Target IS`
- `Target DH`
- `Target HR`
- `Target Time Admin`
- `Designation`
- `Attachment`

#### Deputation Details (11 not needed)

- `effectiveStartDate`
- `Deputation Extension Date`
- `Deputed Location`
- `Deputed Cost Code`
- `Deputed Company`
- `Deputed Segment`
- `IS`
- `Type of Posting`
- `SiteAddress`
- `Created By`
- `Last Modified By`

#### Rating PLR Dataupdate (11 not needed)

- `externalCode`
- `Performance Linked Reward (PLR)`
- `Currency`
- `Performance Linked Reward (PLR) - Payable`
- `Currency`
- `Performance Link Reward B`
- `Currency`
- `Performance Link Reward B - Payable`
- `Currency`
- `Promotion Jan`
- `Promoted Grade (only Jan Promotion)`

#### Resignation Request (11 not needed)

- `effectiveStartDate`
- `Notice Period Days Served`
- `Number of Days to be Recovered`
- `Comments`
- `Attachment`
- `Withdrawal of Resignation`
- `BondRecovery`
- `ESOPRecovery`
- `Notice period waived off`
- `Notice Waived off Days`
- `Please provide reason if Exit Interview Required is "No" (600 characters)`

#### Biographic info (8 not needed)

- `Date of Birth`
- `Country of Birth`
- `State of Birth`
- `Place of Birth`
- `Attachment`
- `Age (Years)`
- `Age YY/MM/DD`
- `Mother Tongue`

#### Job Classification (8 not needed)

- `Description`
- `Status`
- `Effective as of`
- `End Date`
- `Workers'Comp Code`
- `Parent Job Classification`
- `Standard Weekly Hours`
- `defaultSupervisorLevel`

#### Promotion details (7 not needed)

- `externalCode`
- `Fuel Reimbursement in Litres`
- `ACLRA`
- `Currency`
- `Promoted Standardization Grade (only July / Jan Promotion)`
- `Promoted Grade (only July / Jan Promotion) Start Date`
- `Previous Standardization Grade (only July / Jan Promotion)`

#### Designated Employee (5 not needed)

- `effectiveStartDate`
- `Declaration Filing Date`
- `Ceased Filing Date`
- `Remarks`
- `Reason For Cessation`

#### Development Centre (5 not needed)

- `Parent`
- `externalCode`
- `externaName`
- `effectiveStartDate`
- `Child`

#### Certifications (3 not needed)

- `Attachment`
- `Validity Duration`
- `Country`

#### Certifications Licenses (3 not needed)

- `Attachment`
- `Validity Duration`
- `Country`

#### Annual Health Chek up (2 not needed)

- `Relationship`
- `City`

#### Job Function (2 not needed)

- `Effective as of`
- `End Date`

#### Email Information (1 not needed)

- `Email Type`

#### Job Subfunction New (1 not needed)

- `Effective as of`

---

## Production extrapolation rules (detail)

Shared population filters for almost every KPI:

- **IC slice:** Job Info `IC` (fallback: `Legal Entity` / `L&T Group of Companies`).
- **Active / eligible:** hired on or before period end (`Hire Date` / `Joining Date`) and not separated before period start (`Separation Date` / Resignation `Approved Last Working Date`).
- **Store lineage** on each `KpiRecord.detail` as `extrapolated_from` + `confidence` (`direct` | `proxy` | `weak_proxy`) so the Copilot never presents a proxy as a native SF process metric.

### Direct (ship first)

#### `overall_retention`

- `avg_headcount` = average active headcount in IC over the period.
- `retentions` = headcount that remained employed through the period (or period-start actives minus separations — pick one definition and keep it stable).

#### `top_talent_retention`

- Top-talent set = employees whose `Grade / Cadre` / `Band` / Cadre History `Current Cadre` maps to **CPR 7+** (mapping table maintained in config).
- `regrettable_exits` = separations in period where Resignation `Resignation Reason` is in the regrettable set.
- `avg_headcount_cpr7` = average headcount of that top-talent set.

#### `trainee_retention`

- Trainee cohort = `Employment Type` / `Appointment Type` / `Employee Group` / `Trainee Experience in YY/MM` / `Contract/Training End Date` per agreed trainee rules.
- `onboarded` = trainees whose hire/joining falls in the cohort window; `remaining` = still active after 3 years.

### Proxy (define rules in mapping config)

#### `pli_assessment`

- `total` = active employees in M3C & M4A (cadre/grade/band map).
- `completed` = subset with a Development Centre row in the FY (`Year of Attending` / `From Date`–`To Date`) and a non-empty `DC Score` (or child `Score`).

#### `role_skill_coverage`

- `in_scope` = active employees with a `Job Code` / Job Classification.
- `mapped` = in-scope employees with ≥1 Language Skills proficiency **or** ≥1 Certification/Licence (optionally require both for a stricter rule).

#### `tni_employees`

- `eligible` = active employees in IC.
- `completed` = eligible with ≥1 of: Courses, Development Centre, Seven Step / Core Dev / PM Program row dated in the FY.

#### `tni_fulfilment`

- `identified` = employees (or course-need rows) with any learning/dev activity opened in the period.
- `fulfilled` = subset with Courses `Date Completed` (or leadership `year`) in the period.
- If only completions exist, set `identified = fulfilled` only when you accept that the ratio collapses to 100% — prefer counting distinct course *types* started vs completed.

#### `kra_submission`

- `eligible` = active employees in scope for performance cycle.
- `submitted` = eligible with Performance History Portlet/SM or Rating PLR row for the FY whose effective / assessment date is **on or before 30 June**.

#### `mid_term_review`

- `eligible` = same performance-cycle population.
- `completed` = eligible with Performance History / Rating evidence updated **on or before 31 December** (prefer a second rating touch, or CP/PDR present, vs the June KRA proxy).

#### `idp_creation_rate`

- `target_employees` = agreed target set (e.g. top-talent cadre, or Designated Employee flag).
- `with_idp` = targets with development evidence in period: Development Centre, Courses, Special Assignments, or leadership program rows (IDP object itself is not in the field list).

### Weak proxy (document heavily; consider manual override)

#### `training_calendar` (IC-level 0 / 1 / 2)

- No calendar publish flag exists.
- Heuristic: `1` if the IC has any Courses / program activity with dates in **Apr–Sep**; `2` if also activity in **Oct–Mar**; else `0`.
- This measures *delivery evidence*, not *publish timeliness*.

#### `ppw_on_time` (IC-level 0 / 1)

- Heuristic: `1` if by **1 April** at least X% of eligible employees already have a Performance History / Rating row for the new FY (goal-cascade proxy); else `0`.
- Threshold `X` lives in config (e.g. 50%).

#### `l1_feedback`

- No 1–5 training eval field.
- Heuristic: average Development Centre competency `Score` (or FTC `IS Overall Rating` if in scope), normalised onto 1–5 → platform stores `avg_rating_5`.
- Mark lineage `weak_proxy`; prefer manual entry if scores are not on a 1–5-like scale.

#### `continuous_feedback`

- No feedback-entry log.
- Heuristic: per eligible employee, count period touchpoints among Course completions, Special Assignments, internal Work Experience / Transfer / Deputation events, and rating updates; IC metric = average touchpoints → `avg_entries_per_employee` (target remains 2).
- This is the weakest SF extrapolation; keep stub/mock behaviour for demos only.

---

## Recommended production ingestion stance

1. **Treat `SuccessFactor Fields List.xlsx` as the only SF contract.** Do not plan on mock KPI entity paths for production.
2. **Ingest must-have EC sheets first** (Job Info, Employment Info, Resignation, Cadre History) and compute the three **direct** retention KPIs.
3. **Add proxy sheets next** (Performance History, Rating PLR, Development Centre, Courses, Certifications, Language Skills, Job Classification) and implement the proxy rules above in a production mapping layer (not the simulation `successfactors.mapping.json` as-is).
4. **Weak-proxy KPIs** (`ppw_on_time`, `training_calendar`, `l1_feedback`, `continuous_feedback`): either ship the documented heuristic with explicit Copilot wording (“estimated from …”) or collect them as **manual editor inputs** like GPTW / Cost per Hire.
5. **Do not sync** the exclude sheets (payroll, PII, addresses, bonds, loans, documents).
6. Keep simulation mocks for local demos, but gate them behind stub/mock flags so they cannot be mistaken for production SF.

---

*Field inventory from `SuccessFactor Fields List.xlsx`. Production rule: extrapolate SF scorecard KPIs from this list only; simulation endpoints are non-production.*
