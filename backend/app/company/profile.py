"""Workspace company profile — one executive context for the whole install."""
from __future__ import annotations

import contextlib
import os
import secrets
import stat
import threading
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings

PROFILE_EDIT_LOCK = threading.Lock()


class TargetCustomer(BaseModel):
    profile: str = ""
    pain_points: list[str] = Field(default_factory=list)


class CompetitiveLandscape(BaseModel):
    primary_competitors: list[str] = Field(default_factory=list)
    competitive_advantages: list[str] = Field(default_factory=list)


class OrgStructure(BaseModel):
    departments: list[str] = Field(default_factory=list)
    leadership_team: list[str] = Field(default_factory=list)


class StrategicPriorities(BaseModel):
    current_year: list[str] = Field(default_factory=list)
    north_star_metric: str = ""


class Culture(BaseModel):
    values: list[str] = Field(default_factory=list)
    operating_principles: list[str] = Field(default_factory=list)


class Financials(BaseModel):
    burn_rate_monthly: float | None = None
    runway_months: float | None = None
    key_metrics: dict[str, Any] = Field(default_factory=dict)


class CompanyProfile(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = ""
    website: str = ""
    industry: str = ""
    stage: str = ""
    founding_year: int | None = None
    headcount: int | None = None
    annual_revenue_arr: float | None = None
    mission: str = ""
    vision: str = ""
    target_customer: TargetCustomer = Field(default_factory=TargetCustomer)
    competitive_landscape: CompetitiveLandscape = Field(
        default_factory=CompetitiveLandscape
    )
    org_structure: OrgStructure = Field(default_factory=OrgStructure)
    strategic_priorities: StrategicPriorities = Field(
        default_factory=StrategicPriorities
    )
    culture: Culture = Field(default_factory=Culture)
    financials: Financials = Field(default_factory=Financials)
    vendors: list[str] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not bool(self.name.strip())

    @classmethod
    def load_from_yaml(cls, path: Path | str) -> CompanyProfile:
        path = Path(path)
        if not path.exists():
            return cls()
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        company_data = data.get("company", data)
        return cls.model_validate(company_data)

    def save_to_yaml(self, path: Path | str) -> None:
        path = Path(path)
        try:
            path = path.resolve()
        except (OSError, RuntimeError):
            path = path.absolute()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"company": self.model_dump()}
        tmp_path = path.with_name(f".tmp-{os.getpid()}-{secrets.token_hex(4)}-{path.name}")
        existing_mode: int | None = None
        with contextlib.suppress(OSError):
            st = path.lstat()
            if not stat.S_ISLNK(st.st_mode):
                existing_mode = stat.S_IMODE(st.st_mode)

        def _exclusive(p: str, flags: int) -> int:
            return os.open(p, flags | os.O_EXCL, 0o600)

        try:
            with open(tmp_path, "w", encoding="utf-8", opener=_exclusive) as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
                if existing_mode is not None and hasattr(os, "fchmod"):
                    os.fchmod(f.fileno(), existing_mode)
            os.replace(tmp_path, path)
            with contextlib.suppress(OSError):
                dir_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

    def to_prompt_block(self) -> str:
        if not self.name:
            return ""
        lines = ["## Company Context", "", f"**Company**: {self.name}"]
        if self.website:
            lines.append(f"**Website**: {self.website}")
        if self.industry:
            lines.append(f"**Industry**: {self.industry}")
        if self.stage:
            lines.append(f"**Stage**: {self.stage}")
        if self.founding_year:
            lines.append(f"**Founded**: {self.founding_year}")
        if self.headcount:
            lines.append(f"**Headcount**: {self.headcount}")
        if self.annual_revenue_arr:
            lines.append(f"**ARR**: ${self.annual_revenue_arr:,.0f}")
        if self.mission:
            lines.extend(["", f"**Mission**: {self.mission}"])
        if self.vision:
            lines.append(f"**Vision**: {self.vision}")
        if self.target_customer.profile:
            lines.extend(["", "**Target Customer**:", f"  {self.target_customer.profile}"])
            if self.target_customer.pain_points:
                lines.append(
                    "  Pain points: " + "; ".join(self.target_customer.pain_points)
                )
        if self.competitive_landscape.primary_competitors:
            lines.extend(
                [
                    "",
                    "**Competitive Landscape**:",
                    "  Competitors: "
                    + ", ".join(self.competitive_landscape.primary_competitors),
                ]
            )
            if self.competitive_landscape.competitive_advantages:
                lines.append(
                    "  Our advantages: "
                    + "; ".join(self.competitive_landscape.competitive_advantages)
                )
        if self.org_structure.departments or self.org_structure.leadership_team:
            lines.extend(["", "**Organisation**:"])
            if self.org_structure.departments:
                lines.append(
                    "  Departments: " + ", ".join(self.org_structure.departments)
                )
            if self.org_structure.leadership_team:
                lines.append(
                    "  Leadership: " + ", ".join(self.org_structure.leadership_team)
                )
        if self.strategic_priorities.current_year or self.strategic_priorities.north_star_metric:
            lines.extend(["", "**Strategic Priorities**:"])
            if self.strategic_priorities.north_star_metric:
                lines.append(
                    f"  North star: {self.strategic_priorities.north_star_metric}"
                )
            for p in self.strategic_priorities.current_year:
                lines.append(f"  - {p}")
        if self.culture.values or self.culture.operating_principles:
            lines.extend(["", "**Culture**:"])
            if self.culture.values:
                lines.append("  Values: " + "; ".join(self.culture.values))
            if self.culture.operating_principles:
                lines.append(
                    "  Principles: " + "; ".join(self.culture.operating_principles)
                )
        return "\n".join(lines)


def load_profile(path: Path | None = None) -> CompanyProfile:
    return CompanyProfile.load_from_yaml(path or settings.company_profile_path)


def save_profile(profile: CompanyProfile, path: Path | None = None) -> None:
    with PROFILE_EDIT_LOCK:
        profile.save_to_yaml(path or settings.company_profile_path)
