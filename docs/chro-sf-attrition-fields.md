# CHRO SuccessFactors fields — Attrition / Retention

---

## 1. Must-have — scorecard math (17)

| # | SF sheet (portlet) | Field name | Role in attrition | Tier |
| --- | --- | --- | --- | --- |
| 1 | Job Info | `IC` | Primary IC slice for all retention / attrition KPIs | Must-have |
| 2 | Job Info | `Legal Entity` | Fallback org key when IC is missing | Must-have |
| 3 | Job Info | `Grade / Cadre` | Top-talent (CPR 7+) set for top-talent attrition | Must-have |
| 4 | Job Info | `Band` | Alternate talent banding for CPR 7+ mapping | Must-have |
| 5 | Job Info | `Employment Type` | Trainee vs regular eligibility | Must-have |
| 6 | Job Info | `Appointment Type` | Trainee / FTC / regular identification | Must-have |
| 7 | Job Info | `Employee Group` | Eligibility filter for trainee cohort | Must-have |
| 8 | Job Info | `Contract/Training End Date` | Trainee / FTC cohort window | Must-have |
| 9 | Employment Info | `Hire Date` | Active-population start; retention denominator | Must-have |
| 10 | Employment Info | `Joining Date` | Hire cohort fallback when Hire Date incomplete | Must-have |
| 11 | Employment Info | `Trainee Experience in YY/MM` | Trainee retention / attrition cohort | Must-have |
| 12 | Employment Info | `Separation Date` | Exit numerator (period bucketing) | Must-have |
| 13 | Employment Info | `Payroll End Date` | Alternate exit boundary if Separation Date missing | Must-have |
| 14 | Resignation Request | `Approved Last Working Date` | Preferred period date for exits | Must-have |
| 15 | Resignation Request | `Resignation Reason` | Regrettable vs non-regrettable (top-talent KPI) | Must-have |
| 16 | Cadre History | `Current Cadre` | CPR 7+ population for top-talent attrition | Must-have |
| 17 | Biographic info | `P.S. Number` | Stable employee join key (required on all sheets) | Must-have |

---

## 2. Drill-down — where / who (16)

| # | SF sheet (portlet) | Field name | Role in attrition | Tier |
| --- | --- | --- | --- | --- |
| 18 | Job Info | `Country` | Geo cut of exits | Drill-down |
| 19 | Job Info | `Strategic Business Group` | SBG cut below IC | Drill-down |
| 20 | Job Info | `Business Unit` | BU-level attrition | Drill-down |
| 21 | Job Info | `Department / Projects` | Department attrition hotspots | Drill-down |
| 22 | Job Info | `Base Location` | Site / location concentration | Drill-down |
| 23 | Job Info | `Immediate Supervisor` | Manager-linked attrition | Drill-down |
| 24 | Job Info | `Job Function` | Function-level attrition | Drill-down |
| 25 | Job Info | `Time in Company` | Tenure bands at risk | Drill-down |
| 26 | Job Info | `Notice Period (Months)` | Notice policy vs actual exit timing | Drill-down |
| 27 | Resignation Request | `Date Of Resignation` | Leading indicator (when exit started) | Drill-down |
| 28 | Resignation Request | `Requested Relieving Date` | Early-exit / notice-shortening patterns | Drill-down |
| 29 | Resignation Request | `Notice Period Last Date as Per Policy` | Policy vs actual relieving gap | Drill-down |
| 30 | Resignation Request | `Grade` | Exit grade mix (CPR 7+ check) | Drill-down |
| 31 | Resignation Request | `Department` | Attrition by department (resignation row) | Drill-down |
| 32 | Resignation Request | `Location` | Attrition by location (resignation row) | Drill-down |
| 33 | Resignation Request | `Date of Joining` | Tenure at exit without joining Employment | Drill-down |

---

## 3. Copilot “why” — narrative, not scorecard math (15)

| # | SF sheet (portlet) | Field name | Role in attrition | Tier |
| --- | --- | --- | --- | --- |
| 34 | Employment Info | `OK to Rehire` | Soft exit-quality / regrettable aid | Copilot |
| 35 | Resignation Request | `Exit Interview Required` | Exit-interview coverage pulse | Copilot |
| 36 | Exit Interview New | `Business Unit / Department` | Exit mix by BU / department | Copilot |
| 37 | Exit Interview New | `Designation` | Exit mix by designation | Copilot |
| 38 | Exit Interview New | `Date of Joining` | Tenure-at-exit start | Copilot |
| 39 | Exit Interview New | `Date of Separation` | Tenure-at-exit end | Copilot |
| 40 | Exit Interview New | `Tenure in L&T` | Precomputed tenure at exit | Copilot |
| 41 | Exit Interview New | `What triggered your decision to leave L&T (HR Input)` | Exit root-cause (HR) | Copilot |
| 42 | Exit Interview New | `What was the trigger for your decision to leave L&T` | Exit root-cause (employee) | Copilot |
| 43 | Exit Interview New | `Compensation` | Exit reason flag: compensation | Copilot |
| 44 | Exit Interview New | `Brand` | Exit reason flag: brand | Copilot |
| 45 | Exit Interview New | `Role` | Exit reason flag: role | Copilot |
| 46 | Exit Interview New | `Work Culture` | Exit reason flag: culture | Copilot |
| 47 | Exit Interview New | `Would you recommend your friends to join L&T` | Exit eNPS-like signal | Copilot |
| 48 | Exit Interview New | `Given an opportunity, would you like to rejoin L&T in future?` | Boomerang / brand health | Copilot |
