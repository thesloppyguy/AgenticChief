"""Seed the integrations: write the stub-company fixture, ingest the fiscal year to date, and seed
the 4 manual KPIs (which have no source system).

Usage: uv run python -m scripts.seed_integrations [--through 2026-10] [--ai] [--reset]

Default is the deterministic generator for the 5 L&T ICs (free, offline, reproducible).
--ai uses Claude instead (Anthropic credentials needed; costs tokens). Live integrations stay
off unless their flags are set.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime

from app.alerts import engine as alerts_engine
from app.core.config import settings
from app.db.migrate import upgrade_head
from app.db.session import SessionLocal
from app.ingestion import registry
from app.ingestion.ai_generator import generate_batch, load_fixture, write_fixture
from app.ingestion.manual_seed import seed_manual
from app.ingestion.runner import ingest
from app.ingestion.stubgen import synthetic_company
from app.org.companies import LNT_BY_CODE, LNT_CODES
from app.services.scorecard import current_period
from scripts.seed import ensure_companies


def fiscal_periods(through: str) -> list[str]:
    """April of the fiscal year containing `through`, up to and including `through`."""
    year, month = map(int, through.split("-"))
    start_year = year if month >= 4 else year - 1
    out, y, m = [], start_year, 4
    while (y, m) <= (year, month):
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def lnt_fixture(*, ai: bool) -> dict:
    codes = list(LNT_CODES)
    assignments = [(c, LNT_BY_CODE[c][1]) for c in codes]
    if not ai:
        companies = {
            c: {"origin": "deterministic", "raw": synthetic_company(c, arch).model_dump()}
            for c, arch in assignments
        }
        return {
            "meta": {
                "generated_at": datetime.now(UTC).isoformat(),
                "model": None,
                "count": len(codes),
                "ai_generated": 0,
                "notes": ["lnt_archetypes"],
            },
            "companies": companies,
        }

    import anthropic

    client = (
        anthropic.Anthropic(api_key=settings.anthropic_api_key)
        if settings.anthropic_api_key
        else anthropic.Anthropic()
    )
    companies: dict = {}
    notes: list[str] = []
    good, err = generate_batch(client, settings.stub_generator_model, assignments)
    if err:
        notes.append(err)
    for code, arch in assignments:
        if code in good:
            companies[code] = {"origin": "ai", "raw": good[code].model_dump()}
        else:
            companies[code] = {
                "origin": "synthetic_fallback",
                "raw": synthetic_company(code, arch).model_dump(),
            }
    return {
        "meta": {
            "generated_at": datetime.now(UTC).isoformat(),
            "model": settings.stub_generator_model,
            "count": len(codes),
            "ai_generated": sum(c["origin"] == "ai" for c in companies.values()),
            "notes": notes,
        },
        "companies": companies,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--through", default=current_period())
    ap.add_argument("--ai", action="store_true")
    ap.add_argument("--reset", action="store_true", help="wipe existing org data before seeding companies")
    ap.add_argument("--no-manual", action="store_true", help="skip seeding the 4 manual (no-source) KPIs")
    a = ap.parse_args()

    fixture = lnt_fixture(ai=a.ai)
    write_fixture(settings.stub_data_path, fixture)
    m = fixture["meta"]
    print(f"fixture {settings.stub_data_path}: {m['ai_generated']}/{m['count']} AI-generated")
    for n in m["notes"]:
        print("  note:", n)

    upgrade_head()
    with SessionLocal() as db:
        from app.knowledge.builtin import seed_builtin as seed_docs

        seed_docs(db)
        ensure_companies(db, reset=a.reset)
        extractors = registry.build_extractors(db=db)
        for period in fiscal_periods(a.through):
            for s in ingest(db, period, extractors):
                print(f"{period} {s.source:15} {s.mode:5} {s.status:8} records={s.records_written}")
            if not a.no_manual:
                from app.mock_sources.store import profiles

                n = seed_manual(db, period, profiles(db) or load_fixture(settings.stub_data_path))
                print(f"{period} {'manual (seed)':15} {'seed':5} {'success':8} records={n}")
            new = alerts_engine.evaluate_period(db, period)
            print(f"{period} alerts raised: {len(new)}")


if __name__ == "__main__":
    main()
