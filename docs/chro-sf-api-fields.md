# CHRO SuccessFactors API field list

**Scope:** Only fields that exist in `SuccessFactor Fields List.xlsx`.
These are the fields required to power the Group CHRO dashboard scorecard
(14 SF-owned KPIs via direct calculation or documented proxies), workforce pulse,
and Copilot drill-down.

**Total fields requested:** 188

**Employee key:** Include `P.S. Number` (or the tenant’s user/person ID equivalent)
on every employee-scoped API response so sheets can be joined.

**IC + period:** Every aggregate or row used for scorecard ingestion should be
filterable by `IC` and a period (or dated so the CHRO platform can bucket by `YYYY-MM`).

---



## Field list


| #   | SF sheet (portlet)              | Field name                                                      | Use for CHRO                                                          |
| --- | ------------------------------- | --------------------------------------------------------------- | --------------------------------------------------------------------- |
| 1   | Job Info                        | `IC`                                                            | Slice all scorecard KPIs and dashboard filters by Independent Company |
| 2   | Job Info                        | `Legal Entity`                                                  | Org / headcount scope when IC needs a legal-entity fallback           |
| 3   | Job Info                        | `L&T Group of Companies`                                        | Group-level attribution and holding-structure filters                 |
| 4   | Job Info                        | `Country`                                                       | Geo breakdown of headcount, exits, and L&D                            |
| 5   | Job Info                        | `Strategic Business Group`                                      | Drill-down below IC (SBG views)                                       |
| 6   | Job Info                        | `Business Unit`                                                 | BU-level scorecard and workforce breakdown                            |
| 7   | Job Info                        | `Segment`                                                       | Segment-level workforce views                                         |
| 8   | Job Info                        | `Cluster`                                                       | Cluster-level workforce views                                         |
| 9   | Job Info                        | `Department / Projects`                                         | Department headcount, attrition, and skill coverage                   |
| 10  | Job Info                        | `Base Location`                                                 | Location concentration, mobility, and site risk                       |
| 11  | Job Info                        | `Position`                                                      | Role inventory and critical-role context                              |
| 12  | Job Info                        | `Position Entry Date`                                           | Time-in-role / stagnation signals                                     |
| 13  | Job Info                        | `Time In Position`                                              | Precomputed time-in-role for pulse views                              |
| 14  | Job Info                        | `Immediate Supervisor`                                          | Manager span, manager-linked attrition, feedback proxies              |
| 15  | Job Info                        | `Job Function`                                                  | Function-level retention and skill cuts                               |
| 16  | Job Info                        | `Job Sub Function`                                              | Finer function taxonomy for role–skill coverage                       |
| 17  | Job Info                        | `Job Code`                                                      | Join key to job taxonomy; denominator for role–skill coverage         |
| 18  | Job Info                        | `Job Title`                                                     | Human-readable role labels on drill-downs                             |
| 19  | Job Info                        | `Grade / Cadre`                                                 | Top-talent (CPR 7+) set; talent retention; IDP target population      |
| 20  | Job Info                        | `Band`                                                          | Alternate talent banding alongside cadre                              |
| 21  | Job Info                        | `Equivalent Grade`                                              | Normalize grades across ICs for Group compares                        |
| 22  | Job Info                        | `Joining Grade`                                                 | Entry grade vs current grade (progression)                            |
| 23  | Job Info                        | `Employment Type`                                               | Eligible population; trainee vs regular mix                           |
| 24  | Job Info                        | `Appointment Type`                                              | Identify trainees / FTC / regular appointments                        |
| 25  | Job Info                        | `Employee Group`                                                | Eligibility filters for performance and L&D KPIs                      |
| 26  | Job Info                        | `Contract/Training End Date`                                    | Trainee and FTC cohort end dates                                      |
| 27  | Job Info                        | `Time in Company`                                               | Tenure bands for retention and pulse                                  |
| 28  | Job Info                        | `Event Reason`                                                  | Reason for job-info change (promo, transfer, exit)                    |
| 29  | Job Info                        | `Expected Joining Date`                                         | Joining lag / expected start analytics                                |
| 30  | Job Info                        | `Notice Period (Months)`                                        | Notice policy vs actual exit timing                                   |
| 31  | Employment Info                 | `Hire Date`                                                     | Headcount start; cohorts; retention denominators                      |
| 32  | Employment Info                 | `Joining Date`                                                  | Hire cohort / trainee start (fallback to Hire Date)                   |
| 33  | Employment Info                 | `Original Start Date`                                           | Prior service / rehire tenure continuity                              |
| 34  | Employment Info                 | `Service Date`                                                  | Service-based tenure and eligibility                                  |
| 35  | Employment Info                 | `Number of Years in Company`                                    | Tenure bands without recomputing from dates                           |
| 36  | Employment Info                 | `Current L&T Experience YY/MM`                                  | L&T-specific tenure for Group views                                   |
| 37  | Employment Info                 | `In Cadre Experience YY/MM`                                     | Time in current cadre (top-talent stability)                          |
| 38  | Employment Info                 | `Trainee Experience in YY/MM`                                   | Trainee retention KPI                                                 |
| 39  | Employment Info                 | `Last Promotion Date`                                           | Promotion velocity / talent movement                                  |
| 40  | Employment Info                 | `Confirmation Date`                                             | Probation-to-confirmed pipeline                                       |
| 41  | Employment Info                 | `Date of Retirement`                                            | Retirement risk and succession exposure                               |
| 42  | Employment Info                 | `Separation Date`                                               | Overall and top-talent retention numerators                           |
| 43  | Employment Info                 | `Payroll End Date`                                              | Alternate exit boundary if Separation Date missing                    |
| 44  | Employment Info                 | `OK to Rehire`                                                  | Exit-quality signal (regrettable vs non-regrettable aid)              |
| 45  | Resignation Request             | `Date Of Resignation`                                           | When resignation started (leading exit indicator)                     |
| 46  | Resignation Request             | `Approved Last Working Date`                                    | Period bucketing for retention KPIs                                   |
| 47  | Resignation Request             | `Requested Relieving Date`                                      | Early-exit / notice-shortening patterns                               |
| 48  | Resignation Request             | `Notice Period Last Date as Per Policy`                         | Policy vs actual relieving gap                                        |
| 49  | Resignation Request             | `Resignation Reason`                                            | Regrettable-exit classification for top-talent retention              |
| 50  | Resignation Request             | `Grade`                                                         | Exit grade mix (CPR 7+ check)                                         |
| 51  | Resignation Request             | `Department`                                                    | Attrition by department                                               |
| 52  | Resignation Request             | `Location`                                                      | Attrition by location                                                 |
| 53  | Resignation Request             | `Date of Joining`                                               | Tenure at exit                                                        |
| 54  | Resignation Request             | `Exit Interview Required`                                       | Exit-interview coverage pulse                                         |
| 55  | Cadre History                   | `Event Date`                                                    | When cadre changed (talent movement timeline)                         |
| 56  | Cadre History                   | `Event Reason`                                                  | Why cadre changed                                                     |
| 57  | Cadre History                   | `Previous Cadre`                                                | Inflow/outflow of CPR bands                                           |
| 58  | Cadre History                   | `Current Cadre`                                                 | CPR 7+ population for top-talent retention and IDP targets            |
| 59  | Cadre History                   | `Job Title`                                                     | Role at cadre event for succession narratives                         |
| 60  | Performance History Portlet     | `AssessmentYear`                                                | Tie ratings to FY for KRA / mid-term / PPW proxies                    |
| 61  | Performance History Portlet     | `MVGRating`                                                     | Performance evidence; KRA-submission proxy when dated                 |
| 62  | Performance History Portlet     | `RatingDescription`                                             | Rating band labels on drill-downs                                     |
| 63  | Performance History Portlet     | `CPRating`                                                      | Potential/CP axis; mid-term review proxy                              |
| 64  | Performance History Portlet     | `PDRRating`                                                     | PDR completion; mid-term review proxy                                 |
| 65  | Performance History Portlet     | `RemarksSuccession`                                             | Succession remarks for Copilot                                        |
| 66  | Performance History Portlet     | `Remarks`                                                       | Free-text performance context                                         |
| 67  | Rating PLR Dataupdate           | `effectiveStartDate`                                            | Date gate for KRA (≤30 Jun), mid-term (≤31 Dec), PPW (before 1 Apr)   |
| 68  | Rating PLR Dataupdate           | `MVG Actual Rating`                                             | Dated performance rating for cycle proxies                            |
| 69  | Rating PLR Dataupdate           | `Letter MVG rating`                                             | Published rating letter (stronger cycle-completed signal)             |
| 70  | Rating PLR Dataupdate           | `CP Rating`                                                     | CP rating on dated PLR row                                            |
| 71  | Rating PLR Dataupdate           | `PDR Rating (if applicable)`                                    | PDR rating on dated PLR row                                           |
| 72  | Development Centre              | `Year of Attending`                                             | FY filter for PLI assessment proxy                                    |
| 73  | Development Centre              | `From Date`                                                     | DC attendance period start                                            |
| 74  | Development Centre              | `To Date`                                                       | DC attendance period end                                              |
| 75  | Development Centre              | `DC Type`                                                       | Distinguish PLI-like assessments from other DC events                 |
| 76  | Development Centre              | `DC Score`                                                      | PLI completion/outcome; weak L1 score input                           |
| 77  | Development Centre              | `DC Category`                                                   | Segment assessment types on drill-down                                |
| 78  | Development Centre              | `Name`                                                          | Competency name covered in DC (child rows)                            |
| 79  | Development Centre              | `Score`                                                         | Per-competency score; weak L1 feedback proxy                          |
| 80  | Development Centre              | `Category`                                                      | Competency category grouping                                          |
| 81  | Job Classification              | `Job Code`                                                      | Role master key for skill-coverage denominator                        |
| 82  | Job Classification              | `Job Title`                                                     | Role display name                                                     |
| 83  | Job Classification              | `Pay Grade`                                                     | Grade on role taxonomy                                                |
| 84  | Job Classification              | `Job Function`                                                  | Function rollup for org effectiveness                                 |
| 85  | Job Classification              | `Employee Class`                                                | Include/exclude classes from in-scope population                      |
| 86  | Job Classification              | `Is Full Time Employee`                                         | Optional FTE-only skill coverage                                      |
| 87  | Job Classification              | `Regular/Temporary`                                             | Scope filter for temporary staff                                      |
| 88  | Job Classification              | `defaultJobLevel`                                               | Level-based skill expectations                                        |
| 89  | Job Function                    | `Job Function ID`                                               | Function master ID                                                    |
| 90  | Job Function                    | `Name`                                                          | Function display name                                                 |
| 91  | Job Function                    | `Description`                                                   | Function description                                                  |
| 92  | Job Function                    | `Status`                                                        | Active function filter                                                |
| 93  | Job Function                    | `Parent Job Function`                                           | Function hierarchy rollups                                            |
| 94  | Job Function                    | `Job Function Type`                                             | Function type classification                                          |
| 95  | Job Subfunction New             | `Job Sub Family Code`                                           | Sub-family code for finer role taxonomy                               |
| 96  | Job Subfunction New             | `Job Sub Family Name`                                           | Sub-family name                                                       |
| 97  | Job Subfunction New             | `Status`                                                        | Active sub-family filter                                              |
| 98  | Job Subfunction New             | `Description`                                                   | Sub-family description                                                |
| 99  | Language Skills                 | `Language`                                                      | Role–skill coverage (language mapped)                                 |
| 100 | Language Skills                 | `Speaking Proficiency`                                          | Proficiency depth for mapping quality                                 |
| 101 | Language Skills                 | `Reading Proficiency`                                           | Proficiency depth for mapping quality                                 |
| 102 | Language Skills                 | `Writing Proficiency`                                           | Proficiency depth for mapping quality                                 |
| 103 | Certifications                  | `Certification/Licence`                                         | Role–skill coverage via credentials                                   |
| 104 | Certifications                  | `Description`                                                   | Credential detail on drill-down                                       |
| 105 | Certifications                  | `Institution`                                                   | Credential provider mix                                               |
| 106 | Certifications                  | `Certified Date`                                                | Mapping freshness in period                                           |
| 107 | Certifications                  | `Certificate Valid Upto`                                        | Exclude expired credentials from coverage                             |
| 108 | Certifications                  | `Certification Type`                                            | Filter credential types in scope                                      |
| 109 | Certifications                  | `Company Sponsored`                                             | Company-sponsored vs self-driven skills                               |
| 110 | Courses                         | `Course Name`                                                   | Training catalogue; TNI fulfilment detail                             |
| 111 | Courses                         | `Institution Name`                                              | Training provider                                                     |
| 112 | Courses                         | `Type`                                                          | Classify training needs / fulfilment                                  |
| 113 | Courses                         | `Length`                                                        | Training volume proxy                                                 |
| 114 | Courses                         | `Date Completed`                                                | TNI fulfilment; training-calendar evidence; feedback touchpoints      |
| 115 | Seven Step Leadership Developme | `name`                                                          | Leadership program name (TNI / IDP proxy)                             |
| 116 | Seven Step Leadership Developme | `institution`                                                   | Leadership program institution                                        |
| 117 | Seven Step Leadership Developme | `year`                                                          | Leadership program year (period filter)                               |
| 118 | Core Development Program        | `name`                                                          | Core development program name                                         |
| 119 | Core Development Program        | `institution`                                                   | Core development institution                                          |
| 120 | Core Development Program        | `year`                                                          | Core development year                                                 |
| 121 | Project Management Program      | `name`                                                          | PM program name                                                       |
| 122 | Project Management Program      | `institution`                                                   | PM program institution                                                |
| 123 | Project Management Program      | `year`                                                          | PM program year                                                       |
| 124 | Special Assignments Projects    | `startDate`                                                     | Assignment start (IDP / continuous-feedback proxy)                    |
| 125 | Special Assignments Projects    | `endDate`                                                       | Assignment end                                                        |
| 126 | Special Assignments Projects    | `project`                                                       | Assignment project name                                               |
| 127 | Special Assignments Projects    | `description`                                                   | Assignment detail for Copilot                                         |
| 128 | Work Experience Within Company  | `startDate`                                                     | Internal move start                                                   |
| 129 | Work Experience Within Company  | `endDate`                                                       | Internal move end                                                     |
| 130 | Work Experience Within Company  | `job-title`                                                     | Internal role title history                                           |
| 131 | Work Experience Within Company  | `jobFunction`                                                   | Internal function history                                             |
| 132 | Work Experience Within Company  | `departmentProject`                                             | Internal department/project history                                   |
| 133 | Geographic Mobility             | `Willing to Relocate`                                           | Mobility pool for succession pulse                                    |
| 134 | Geographic Mobility             | `Region Desired`                                                | Preferred relocation regions                                          |
| 135 | Designated Employee             | `Designated Employee Flag`                                      | Critical-role / IDP target population                                 |
| 136 | Designated Employee             | `Category`                                                      | Designated-employee category                                          |
| 137 | Designated Employee             | `Date of becoming Designated Employee`                          | When critical-role status started                                     |
| 138 | Designated Employee             | `Date of cessation as Designated Employee`                      | When critical-role status ended                                       |
| 139 | Promotion details               | `effectiveStartDate`                                            | Promotion effective date                                              |
| 140 | Promotion details               | `Promotion ( only July / Jan Promotion )`                       | Promo cycle flag                                                      |
| 141 | Promotion details               | `Promoted Grade (only July / Jan Promotion)`                    | New grade after promotion                                             |
| 142 | Promotion details               | `Promoted Band (only July / Jan Promotion)`                     | New band after promotion                                              |
| 143 | Promotion details               | `Previous Grade (only July / Jan Promotion)`                    | Prior grade before promotion                                          |
| 144 | Transfer request                | `Target IC`                                                     | Cross-IC transfer destination                                         |
| 145 | Transfer request                | `Target SBG`                                                    | Transfer target SBG                                                   |
| 146 | Transfer request                | `Target BU`                                                     | Transfer target BU                                                    |
| 147 | Transfer request                | `Target Location`                                               | Transfer target location                                              |
| 148 | Transfer request                | `Target Position ID`                                            | Transfer target position                                              |
| 149 | Transfer request                | `Date of joining at the new location`                           | Transfer completion date                                              |
| 150 | Transfer request                | `Your Role in the New Assignment`                               | Role after transfer                                                   |
| 151 | Deputation Details              | `Deputation Reason`                                             | Why deputed                                                           |
| 152 | Deputation Details              | `DeputationType`                                                | Deputation type                                                       |
| 153 | Deputation Details              | `Deputation Start Date`                                         | Deputation start                                                      |
| 154 | Deputation Details              | `Deputation End Date`                                           | Deputation end                                                        |
| 155 | Deputation Details              | `Deputed IC`                                                    | IC where headcount should count during deputation                     |
| 156 | Deputation Details              | `Deputed SBG`                                                   | Deputed SBG                                                           |
| 157 | Deputation Details              | `Deputed Department/Project`                                    | Deputed department/project                                            |
| 158 | FTC Assesment process           | `IC`                                                            | FTC employee IC                                                       |
| 159 | FTC Assesment process           | `Business Unit`                                                 | FTC business unit                                                     |
| 160 | FTC Assesment process           | `Joining Date`                                                  | FTC join date                                                         |
| 161 | FTC Assesment process           | `Band`                                                          | FTC band                                                              |
| 162 | FTC Assesment process           | `Pay Grade`                                                     | FTC pay grade                                                         |
| 163 | FTC Assesment process           | `Contract End Date`                                             | FTC runway / extension risk                                           |
| 164 | FTC Assesment process           | `IS Overall Rating`                                             | FTC rating; weak L1 / quality proxy                                   |
| 165 | FTC Assesment process           | `Recommended for - by IS`                                       | IS renewal/conversion recommendation                                  |
| 166 | FTC Assesment process           | `Recommended for - by DH`                                       | DH renewal/conversion recommendation                                  |
| 167 | Exit Interview New              | `Business Unit / Department`                                    | Exit mix by BU/department                                             |
| 168 | Exit Interview New              | `Designation`                                                   | Exit mix by designation                                               |
| 169 | Exit Interview New              | `Date of Joining`                                               | Tenure-at-exit start                                                  |
| 170 | Exit Interview New              | `Date of Separation`                                            | Tenure-at-exit end                                                    |
| 171 | Exit Interview New              | `Tenure in L&T`                                                 | Precomputed tenure at exit                                            |
| 172 | Exit Interview New              | `What triggered your decision to leave L&T (HR Input)`          | Exit root-cause (HR)                                                  |
| 173 | Exit Interview New              | `What was the trigger for your decision to leave L&T`           | Exit root-cause (employee)                                            |
| 174 | Exit Interview New              | `Compensation`                                                  | Exit reason flag: compensation                                        |
| 175 | Exit Interview New              | `Brand`                                                         | Exit reason flag: brand                                               |
| 176 | Exit Interview New              | `Role`                                                          | Exit reason flag: role                                                |
| 177 | Exit Interview New              | `Work Culture`                                                  | Exit reason flag: culture                                             |
| 178 | Exit Interview New              | `Would you recommend your friends to join L&T`                  | Exit eNPS-like signal                                                 |
| 179 | Exit Interview New              | `Given an opportunity, would you like to rejoin L&T in future?` | Boomerang / brand health                                              |
| 180 | Biographic info                 | `P.S. Number`                                                   | Stable employee key across entities/APIs                              |
| 181 | Personal Info                   | `First Name`                                                    | People directory / drill-down label                                   |
| 182 | Personal Info                   | `Last Name`                                                     | People directory / drill-down label                                   |
| 183 | Personal Info                   | `Name as per Aadhaar / Full Name`                               | Canonical display name                                                |
| 184 | Personal Info                   | `Gender`                                                        | Optional diversity slices                                             |
| 185 | Email Information               | `Email Address`                                                 | Org roster and notifications                                          |
| 186 | Email Information               | `Is Primary`                                                    | Pick primary work email                                               |
| 187 | Annual Health Chek up           | `Date of AHC`                                                   | Optional wellness context only (official AHC KPI is MyHealth)         |
| 188 | Annual Health Chek up           | `Hospital Name`                                                 | Optional AHC delivery footprint (context only)                        |




---



## Suggested API groupings


| API / resource                 | Sheets to cover                                                                                        |
| ------------------------------ | ------------------------------------------------------------------------------------------------------ |
| Employee job assignment        | Job Info                                                                                               |
| Employment dates / status      | Employment Info                                                                                        |
| Resignations                   | Resignation Request                                                                                    |
| Cadre history                  | Cadre History                                                                                          |
| Performance ratings            | Performance History Portlet **or** SM + Rating PLR Dataupdate                                          |
| Development centre / PLI proxy | Development Centre                                                                                     |
| Job taxonomy                   | Job Classification, Job Function, Job Subfunction New                                                  |
| Skills                         | Language Skills, Certifications                                                                        |
| Learning history               | Courses, Seven Step / Core Dev / PM Program                                                            |
| Development evidence           | Special Assignments Projects, Work Experience Within Company, Geographic Mobility, Designated Employee |
| Movement                       | Promotion details, Transfer request, Deputation Details                                                |
| FTC assessments                | FTC Assesment process                                                                                  |
| Exit interviews                | Exit Interview New                                                                                     |
| Identity / roster              | Biographic info (`P.S. Number`), Personal Info, Email Information                                      |
| Optional wellness context      | Annual Health Chek up (AHC KPI itself comes from MyHealth)                                             |


---

