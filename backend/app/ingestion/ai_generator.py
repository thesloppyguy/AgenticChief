"""Generate stub company data with Claude (structured outputs). Writes a reproducible fixture.

Run once (scripts/generate_stub_data.py); ingestion then reads the fixture, so there is no
per-run LLM cost and results are stable. Anything the model gets wrong falls back, per company, to
the deterministic generator and is marked in the fixture.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anthropic

from .stubgen import CompanyBatch, CompanyRaw, assign_archetype, synthetic_company, validate

SYSTEM = """You generate realistic, internally consistent HR statistics for SYNTHETIC test data.
The companies are fictional independent companies inside one large Indian business group, across
manufacturing, services, retail and technology. Values are year-to-date counts for the group's HR scorecard.

Hard rules:
- Every count is a non-negative integer, except avg_days_to_fill, avg_feedback_entries and avg_rating_5.
- Never exceed a parent population: joined <= offers; retained_12m <= hire_cohort; kra_submitted,
  mid_term_completed and tni_completed <= eligible_employees; eligible_employees <= headcount;
  tni_fulfilled <= tni_identified; pli_completed <= pli_total; idps_created <= idp_target_employees;
  ahc_completed <= ahc_eligible; unique_logins <= headcount; retentions <= avg_headcount;
  regrettable_exits <= cpr7_headcount; trainees_remaining <= trainees_onboarded.
- avg_rating_5 is between 1 and 5. avg_days_to_fill is between 20 and 150. avg_feedback_entries is 0 to 6.
- ppw_on_time is 0 or 1. training_calendar is 0, 1 or 2.
- Match each company's stated archetype: strong companies mostly hit targets (completion rates ~90-100%),
  steady ones are mostly fine with some gaps (75-92%), struggling ones miss several targets (40-75%), and
  early_stage ones are small, new to the HR programme, with patchy coverage.
- Make the companies clearly different from each other in size and profile. Do not repeat numbers."""


def _prompt(assignments: list[tuple[str, str]]) -> str:
    lines = "\n".join(f"- {code}: archetype={arch}" for code, arch in assignments)
    return (f"Generate one record for each of these {len(assignments)} companies. "
            f"Use exactly these company_code and archetype values.\n{lines}")


def generate_batch(client: Any, model: str, assignments: list[tuple[str, str]]) -> tuple[dict[str, CompanyRaw], str | None]:
    """Returns (valid companies by code, error note or None)."""
    try:
        resp = client.messages.parse(
            model=model, max_tokens=16000, system=SYSTEM,
            messages=[{"role": "user", "content": _prompt(assignments)}],
            output_format=CompanyBatch,
        )
    except anthropic.APIStatusError as e:
        return {}, f"api_error_{e.status_code}"
    except anthropic.APIConnectionError:
        return {}, "connection_error"
    if resp.stop_reason == "refusal":
        return {}, "refusal"
    if resp.parsed_output is None:
        return {}, f"unparsed_{resp.stop_reason}"
    wanted = dict(assignments)
    good: dict[str, CompanyRaw] = {}
    for c in resp.parsed_output.companies:
        if c.company_code in wanted and c.archetype == wanted[c.company_code] and not validate(c):
            good[c.company_code] = c
    return good, None


def generate_fixture(client: Any, model: str, codes: list[str], batch_size: int = 8) -> dict:
    companies: dict[str, dict] = {}
    notes: list[str] = []
    n = len(codes)
    for start in range(0, n, batch_size):
        chunk = codes[start:start + batch_size]
        assignments = [(c, assign_archetype(start + i, n)) for i, c in enumerate(chunk)]
        good, err = generate_batch(client, model, assignments)
        if err:
            notes.append(f"batch starting {chunk[0]}: {err}")
        for code, arch in assignments:
            if code in good:
                companies[code] = {"origin": "ai", "raw": good[code].model_dump()}
            else:
                companies[code] = {"origin": "synthetic_fallback",
                                   "raw": synthetic_company(code, arch).model_dump()}  # type: ignore[arg-type]
    return {
        "meta": {"generated_at": datetime.now(UTC).isoformat(), "model": model,
                 "count": n, "ai_generated": sum(c["origin"] == "ai" for c in companies.values()),
                 "notes": notes},
        "companies": companies,
    }


def deterministic_fixture(codes: list[str]) -> dict:
    """Same fixture format with no AI call: the seeded generator, archetypes spread 25/45/20/10."""
    n = len(codes)
    companies = {
        c: {"origin": "deterministic",
            "raw": synthetic_company(c, assign_archetype(i, n)).model_dump()}  # type: ignore[arg-type]
        for i, c in enumerate(codes)
    }
    return {
        "meta": {"generated_at": datetime.now(UTC).isoformat(), "model": None, "count": n,
                 "ai_generated": 0, "notes": ["deterministic generator; no AI call"]},
        "companies": companies,
    }


def write_fixture(path: str | Path, fixture: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(fixture, indent=1, sort_keys=True))


def load_fixture(path: str | Path) -> dict[str, CompanyRaw] | None:
    p = Path(path)
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    return {code: CompanyRaw(**v["raw"]) for code, v in data["companies"].items()}
