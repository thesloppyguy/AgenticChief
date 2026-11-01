"""Load L&T Group CHRO fixtures into SQLite (OE-shaped packs under seed/)."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts import watches as watches_mod
from app.approvals import service as approvals
from app.company.profile import CompanyProfile, save_profile
from app.core.config import settings
from app.core.security import Principal, Role
from sqlalchemy import func

from app.db.models import (
    Company,
    Department,
    Goal,
    HistoryNote,
    Person,
    UserMemory,
)
from app.fixtures.chro_workflows import seed_chro_workflows
from app.fixtures.paths import COMPANIES_DIR, GROUP_DIR, SEED_ROOT
from app.org.companies import FIXTURE_SLUGS, GROUP_CHRO_USER_ID, LNT_COMPANIES
from app.org.reset import reset_org
from app.services.scorecard import current_period

_REL_TS = re.compile(r"^-(\d+)d$")


def _parse_ts(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(UTC)
    m = _REL_TS.match(str(raw).strip())
    if m:
        return datetime.now(UTC) - timedelta(days=int(m.group(1)))
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _seed_people(db: Session, people: list[dict], default_code: str | None) -> dict[str, Person]:
    by_name: dict[str, Person] = {}
    for row in people:
        code = row.get("company_code", default_code)
        if isinstance(code, str):
            code = code.strip().upper() or None
        p = Person(
            full_name=row["full_name"],
            role=row.get("role") or "",
            email=row.get("email") or "",
            company_code=code,
            is_principal=bool(row.get("is_principal")),
            authority_scope=list(row.get("authority_scope") or []),
            department_slugs=list(row.get("department_slugs") or []),
            preferred_channel=row.get("preferred_channel") or "any",
            response_sla_hours=row.get("response_sla_hours"),
        )
        db.add(p)
        db.flush()
        by_name[p.full_name] = p
    return by_name


def _seed_departments(
    db: Session,
    departments: list[dict],
    people_by_name: dict[str, Person],
    company_code: str | None,
) -> None:
    for row in departments:
        head = people_by_name.get(row.get("head_person_name") or "")
        d = Department(
            slug=row["slug"],
            title=row.get("title") or row["slug"],
            company_code=company_code,
            specialist_key=row.get("specialist_key"),
            head_person_id=head.id if head else None,
            authority_level=row.get("authority_level") or "propose_only",
            charter=row.get("charter"),
            headcount=row.get("headcount"),
        )
        db.add(d)
        db.flush()
        goals = row.get("goals") or row.get("okrs") or []
        for g in goals:
            # Support OE okrs shape (quarter / key_result) and goals shape.
            period_value = g.get("period_value") or g.get("quarter") or ""
            db.add(
                Goal(
                    department_id=d.id,
                    period_type=g.get("period_type") or "quarter",
                    period_value=str(period_value),
                    key_result=g.get("key_result") or "",
                    target=str(g.get("target") or ""),
                    current=str(g.get("current") or ""),
                    status=g.get("status") or "on_track",
                    pillar_key=g.get("pillar_key"),
                )
            )


def _seed_memory(db: Session, memory: dict, user_id: str, tag: str) -> int:
    n = 0
    for d in memory.get("decisions") or []:
        db.add(
            UserMemory(
                user_id=user_id,
                kind="decision",
                domain=d.get("domain") or "hr",
                summary=(d.get("summary") or "")[:400],
                pinned=True,
                created_at=_parse_ts(d.get("timestamp")),
            )
        )
        n += 1
    for it in memory.get("initiatives") or []:
        summary = it.get("summary") or it.get("title") or ""
        if it.get("title") and it.get("summary"):
            summary = f"{it['title']}: {it['summary']}"
        db.add(
            UserMemory(
                user_id=user_id,
                kind="initiative",
                domain="hr",
                summary=summary[:400],
                pinned=True,
                created_at=_parse_ts(it.get("updated_at") or it.get("created_at")),
            )
        )
        n += 1
    for a in memory.get("advice_given") or []:
        summary = a.get("advice_summary") or a.get("summary") or ""
        if a.get("query_summary"):
            summary = f"Q: {a['query_summary']} — A: {summary}"
        db.add(
            UserMemory(
                user_id=user_id,
                kind="advice",
                domain=a.get("domain") or "hr",
                summary=summary[:400],
                pinned=False,
                created_at=_parse_ts(a.get("timestamp")),
            )
        )
        n += 1
    # Open-loop style history notes for the Group CHRO.
    if tag == "group":
        db.add(
            HistoryNote(
                user_id=user_id,
                kind="promised",
                summary="Follow up LTMR retention turnaround before monthly review publish",
                quote="Escalate L&T Metro Rail Retention pillar to Group CHRO weekly until overall leaves red.",
                due_at=datetime.now(UTC) + timedelta(days=3),
                pinned=True,
            )
        )
        db.add(
            HistoryNote(
                user_id=user_id,
                kind="agreed",
                summary="Confirm training calendar H2 milestone (value 2) across ICs",
                quote="Training calendar target is 2 from October.",
                due_at=datetime.now(UTC) + timedelta(days=7),
                pinned=False,
            )
        )
        n += 2
    return n


def _seed_watches(db: Session, who: Principal, period: str) -> int:
    specs = [
        ("Group Retention at risk", None, {"subject": "pillar", "pillar": "retention",
                                           "comparator": "below", "threshold": 90}),
        ("Group Talent Acquisition below green", None, {"subject": "pillar", "pillar": "talent_acquisition",
                                                        "comparator": "below", "threshold": 90}),
        ("LTMR overall red/amber", "LTMR", {"subject": "overall", "comparator": "below", "threshold": 90}),
        ("LTMR retention off track", "LTMR", {"subject": "pillar", "pillar": "retention",
                                              "comparator": "below", "threshold": 75}),
        ("Group GPTW watch", None, {"subject": "kpi", "kpi_key": "gptw_score",
                                    "comparator": "below", "threshold": 90}),
        # Scorecard exception → alert (draft retention corrective is seeded as pending approval).
        ("Group retention exception", None, {"subject": "pillar", "pillar": "retention",
                                             "comparator": "below", "threshold": 75}),
        ("Group TA exception", None, {"subject": "pillar", "pillar": "talent_acquisition",
                                      "comparator": "below", "threshold": 75}),
        ("LTIM retention red/amber", "LTIM", {"subject": "pillar", "pillar": "retention",
                                              "comparator": "below", "threshold": 75}),
    ]
    cadence = {"type": "daily", "time": "09:00"}
    n = 0
    for name, code, cond in specs:
        try:
            with db.begin_nested():
                watches_mod.create(
                    db,
                    who,
                    name=name,
                    company_code=code,
                    condition=cond,
                    cadence=cadence,
                    enabled=True,
                )
            n += 1
        except Exception:
            continue
    db.commit()
    return n


def _seed_workforce_schedule(db: Session, who: Principal) -> int:
    """Weekly schedule for published weekly_workforce_brief workflow (autopilot suggestion)."""
    from app.db.models import Asset, JobSchedule
    from app.scheduler.cadence import next_after, validate

    asset = db.scalar(
        select(Asset).where(Asset.kind == "workflow", Asset.key == "weekly_workforce_brief")
    )
    if asset is None or asset.published_version is None or asset.deprecated:
        return 0
    exists = db.scalar(
        select(JobSchedule.id).where(
            JobSchedule.job == "workflow",
            JobSchedule.name == "Weekly workforce briefing",
        )
    )
    if exists:
        return 0
    cadence = validate({"type": "weekly", "weekday": 0, "time": "07:00"})
    db.add(
        JobSchedule(
            job="workflow",
            name="Weekly workforce briefing",
            cadence=cadence,
            params={"period": "current", "workflow_key": "weekly_workforce_brief"},
            enabled=True,
            next_run_at=next_after(cadence, datetime.now(UTC)),
            created_by=who.user_id,
        )
    )
    db.commit()
    return 1


def _seed_approvals(db: Session, who: Principal, period: str) -> int:
    from app.workforce import loader as wf_loader

    n = 0
    # Second identity as requester so four-eyes still allows admin to approve later.
    requester = Principal("chro-ops", Role.EDITOR, None)
    payloads: list[tuple[str, dict, dict]] = [
        ("send_kpi_reminder", {
            "company_codes": ["LTMR"],
            "period": period,
            "kpi_key": "overall_retention",
            "note": "Retention pillar off track — please confirm headcount and regrettable exits.",
        }, {"reason": "LTMR retention initiative"}),
        ("send_kpi_reminder", {
            "company_codes": ["LTF", "LTR"],
            "period": period,
            "kpi_key": None,
            "note": "Amber-adjacent ICs — confirm sourced KPI freshness before Group review.",
        }, {"reason": "Pre-monthly hygiene"}),
        ("create_snapshot", {"period": period}, {"reason": "Freeze mid-month view for CHRO brief"}),
    ]
    for draft in (wf_loader.draft_actions().get("drafts") or []):
        action = draft.get("action")
        args = draft.get("propose_args") or {}
        if action and args:
            payloads.append(
                (action, args, {"reason": draft.get("title") or draft.get("key"), "draft_key": draft.get("key")})
            )
    for action, args, ctx in payloads:
        try:
            with db.begin_nested():
                approvals.submit(db, requester, action, args, via="api", context=ctx)
            n += 1
        except Exception:
            continue
    try:
        with db.begin_nested():
            approvals.submit(
                db,
                who,
                "create_snapshot",
                {"period": period},
                via="api",
                context={"reason": "Group CHRO requested snapshot"},
            )
        n += 1
    except Exception:
        pass
    db.commit()
    return n


def _write_group_profile() -> None:
    data = _load_yaml(GROUP_DIR / "profile.yaml")
    company = data.get("company") or data
    profile = CompanyProfile.model_validate(company)
    save_profile(profile)


def _ingest_kpis(db: Session, through: str) -> dict[str, Any]:
    from scripts.seed_integrations import fiscal_periods, lnt_fixture
    from app.ingestion.ai_generator import load_fixture, write_fixture
    from app.ingestion import registry
    from app.ingestion.manual_seed import seed_manual
    from app.ingestion.runner import ingest
    from app.alerts import engine as alerts_engine

    fixture = lnt_fixture(ai=False)
    write_fixture(settings.stub_data_path, fixture)
    extractors = registry.build_extractors(db=db)
    periods = fiscal_periods(through)
    records = 0
    for period in periods:
        for s in ingest(db, period, extractors):
            records += s.records_written
        from app.mock_sources.store import profiles

        seed_manual(db, period, profiles(db) or load_fixture(settings.stub_data_path))
        alerts_engine.evaluate_period(db, period)
    return {"periods": periods, "records": records, "fixture": settings.stub_data_path}


def load_lnt(*, db: Session, reset: bool = True, ingest: bool = True,
             through: str | None = None, user_id: str = GROUP_CHRO_USER_ID) -> dict[str, Any]:
    """Full L&T demo load. Returns a summary dict."""
    if not SEED_ROOT.exists():
        raise FileNotFoundError(f"seed root missing: {SEED_ROOT}")
    through = through or current_period()
    who = Principal(user_id, Role.ADMIN, None)
    summary: dict[str, Any] = {"seed_root": str(SEED_ROOT)}

    if reset:
        summary["reset"] = reset_org(db)

    # Companies
    for code, name, _ in LNT_COMPANIES:
        if not db.scalar(select(Company.id).where(Company.code == code)):
            db.add(Company(code=code, name=name))
    db.commit()
    summary["companies"] = [c for c, _, _ in LNT_COMPANIES]

    # Group pack
    group_people = _load_yaml(GROUP_DIR / "people.yaml").get("people") or []
    people_by_name = _seed_people(db, group_people, None)
    group_depts = _load_yaml(GROUP_DIR / "departments.yaml").get("departments") or []
    _seed_departments(db, group_depts, people_by_name, None)
    mem_n = _seed_memory(db, _load_json(GROUP_DIR / "memory.json"), user_id, "group")
    db.commit()

    # IC packs
    for code, slug in FIXTURE_SLUGS.items():
        base = COMPANIES_DIR / slug
        ic_people = _load_yaml(base / "people.yaml").get("people") or []
        ic_map = _seed_people(db, ic_people, code)
        people_by_name.update(ic_map)
        ic_depts = _load_yaml(base / "departments.yaml").get("departments") or []
        _seed_departments(db, ic_depts, people_by_name, code)
        mem_n += _seed_memory(db, _load_json(base / "memory.json"), user_id, code.lower())
    db.commit()
    summary["memories"] = mem_n
    summary["people"] = db.scalar(select(func.count()).select_from(Person)) or 0
    summary["departments"] = db.scalar(select(func.count()).select_from(Department)) or 0
    summary["goals"] = db.scalar(select(func.count()).select_from(Goal)) or 0

    _write_group_profile()
    summary["profile"] = str(settings.company_profile_path)

    if ingest:
        summary["kpi"] = _ingest_kpis(db, through)

    summary["workflows"] = seed_chro_workflows(db, who)
    # Sample run rows so /workflows is non-empty without executing LLM steps.
    from app.db.models import WorkflowRun

    if not db.scalar(select(WorkflowRun.id).where(WorkflowRun.workflow == "chro_morning_brief")):
        db.add(
            WorkflowRun(
                workflow="chro_morning_brief",
                period=through,
                status="succeeded",
                params={},
                requested_by=who.user_id,
                role="admin",
                state={"card": {"note": "seeded demo"}},
                result={"summary": "Seeded CHRO morning brief placeholder"},
            )
        )
        db.add(
            WorkflowRun(
                workflow="performance_review",
                period=through,
                status="queued",
                params={},
                requested_by=who.user_id,
                role="admin",
                state={},
            )
        )
        db.commit()
        summary["sample_runs"] = 2
    summary["watches"] = _seed_watches(db, who, through)
    summary["approvals"] = _seed_approvals(db, who, through)
    summary["workforce_schedule"] = _seed_workforce_schedule(db, who)

    # Copy group docs into company knowledge folder for RAG remirror (best-effort).
    docs_dest = Path(settings.company_dir) / "docs"
    docs_dest.mkdir(parents=True, exist_ok=True)
    for src in (GROUP_DIR / "docs").glob("*.md"):
        (docs_dest / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    for code, slug in FIXTURE_SLUGS.items():
        for src in (COMPANIES_DIR / slug / "docs").glob("*.md"):
            (docs_dest / f"{code.lower()}_{src.name}").write_text(
                src.read_text(encoding="utf-8"), encoding="utf-8"
            )
    summary["docs"] = len(list(docs_dest.glob("*.md")))
    return summary
