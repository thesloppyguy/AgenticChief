"""Planner catalogue + key helpers for succession-aware workflow drafts."""
from __future__ import annotations

from unittest.mock import MagicMock

from app.workflows import planner


def test_suggest_key_strips_parentheticals_and_prefers_ic_code():
    assert planner.suggest_key(
        "LTIMindtree succession report (partial: talent management view)"
    ) == "ltim_succession_report"
    assert planner.suggest_key("Monthly group snapshot") == "monthly_group_snapshot"


def test_catalogue_exposes_succession_coverage_companies_and_skill():
    cat = planner.catalogue(MagicMock())
    assert "get_succession_coverage" in cat["tools"]
    assert any(c["code"] == "LTIM" and "Mindtree" in " ".join(c["aliases"]) for c in cat["companies"])
    assert "succession-ic-report" in cat["skills"]
    assert "succession proxy" in cat["domain_notes"]["scorecard_talent_management"]
