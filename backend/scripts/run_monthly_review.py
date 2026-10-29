"""Generate the monthly review for a period (cron-able). Usage: uv run python -m scripts.run_monthly_review --period 2026-10

Runs the workflow to completion in-process and prints where to find it. Publishing is separate: it
needs a human approval (propose publish_monthly_report from the Approvals page or the Copilot).
"""
import argparse

from app.core.config import settings
from app.core.security import Principal, Role
from app.db.migrate import upgrade_head
from app.db.session import SessionLocal
from app.reports import monthly_review
from app.services.scorecard import current_period
from app.workflows import engine

ap = argparse.ArgumentParser()
ap.add_argument("--period", default=current_period())
ap.add_argument("--as-user", default="scheduler")
a = ap.parse_args()

upgrade_head()
llm = None
if settings.anthropic_api_key:
    from anthropic import Anthropic

    llm = Anthropic(api_key=settings.anthropic_api_key)
with SessionLocal() as db:
    run = engine.create_run(db, Principal(a.as_user, Role.VIEWER, None), monthly_review.WORKFLOW, a.period)
status = engine.execute(SessionLocal, monthly_review.WORKFLOW, run.id, {"llm": llm})
with SessionLocal() as db:
    from app.db.models import WorkflowRun

    r = db.get(WorkflowRun, run.id)
    method = r.result["commentary"]["method"] if status == "succeeded" else "-"
print(f"run #{run.id} for {a.period}: {status} (commentary: {method})")
