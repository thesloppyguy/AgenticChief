"""Seed the integrations: write the stub-company fixture, ingest the fiscal year to date, and seed
the 4 manual KPIs (which have no source system).

Usage: uv run python -m scripts.seed_integrations [--through 2026-10] [--ai] [--count 88]

Default is the deterministic generator (free, offline, reproducible). --ai uses Claude instead
(Anthropic credentials needed; costs tokens). Live integrations stay off unless their flags are set.
"""
import argparse

from app.alerts import engine as alerts_engine
from app.core.config import settings
from app.db.migrate import upgrade_head
from app.db.session import SessionLocal
from app.ingestion import registry
from app.ingestion.ai_generator import (
    deterministic_fixture,
    generate_fixture,
    load_fixture,
    write_fixture,
)
from app.ingestion.manual_seed import seed_manual
from app.ingestion.runner import ingest
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--through", default=current_period())
    ap.add_argument("--count", type=int, default=88)
    ap.add_argument("--ai", action="store_true")
    ap.add_argument("--no-manual", action="store_true", help="skip seeding the 4 manual (no-source) KPIs")
    a = ap.parse_args()

    codes = [f"IC{i:03d}" for i in range(1, a.count + 1)]
    if a.ai:
        import anthropic

        client = (anthropic.Anthropic(api_key=settings.anthropic_api_key)
                  if settings.anthropic_api_key else anthropic.Anthropic())
        fixture = generate_fixture(client, settings.stub_generator_model, codes)
    else:
        fixture = deterministic_fixture(codes)
    write_fixture(settings.stub_data_path, fixture)
    m = fixture["meta"]
    print(f"fixture {settings.stub_data_path}: {m['ai_generated']}/{m['count']} AI-generated")
    for n in m["notes"]:
        print("  note:", n)

    upgrade_head()
    with SessionLocal() as db:
        from app.assets.builtin import seed_builtin as seed_assets
        from app.knowledge.builtin import seed_builtin as seed_docs

        seed_docs(db)
        seed_assets(db)
        ensure_companies(db)
        extractors = registry.build_extractors(db=db)
        for period in fiscal_periods(a.through):
            for s in ingest(db, period, extractors):
                print(f"{period} {s.source:15} {s.mode:5} {s.status:8} records={s.records_written}")
            if not a.no_manual:
                # Prefer the AI-generated company profiles so manual KPIs tell the same story as the sourced ones.
                from app.mock_sources.store import profiles

                n = seed_manual(db, period, profiles(db) or load_fixture(settings.stub_data_path))
                print(f"{period} {'manual (seed)':15} {'seed':5} {'success':8} records={n}")
            new = alerts_engine.evaluate_period(db, period)  # in order, so month-to-month changes are real
            print(f"{period} alerts raised: {len(new)}")


if __name__ == "__main__":
    main()
