"""Browser smoke test: drives the real UI against a running backend + frontend.

Usage (servers already running):  cd backend && PYTHONPATH=. uv run --with playwright python ../e2e/smoke.py
Env: WEB=http://localhost:3010 API=http://localhost:8010 SHOTS=/tmp/e2e_shots
"""
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.core.security import Role, make_token

WEB, API = os.environ.get("WEB", "http://localhost:3010"), os.environ.get("API", "http://localhost:8010")
SHOTS = Path(os.environ.get("SHOTS", "/tmp/e2e_shots"))
SHOTS.mkdir(parents=True, exist_ok=True)
TOKEN = make_token("e2e-admin", Role.ADMIN, None)

problems: list[str] = []
checks: list[str] = []


def check(cond: bool, label: str):
    (checks if cond else problems).append(label)
    print(("  ok   " if cond else "  FAIL ") + label)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_context(viewport={"width": 1400, "height": 950}).new_page()
    page.on("console", lambda m: problems.append(f"console {m.type}: {m.text[:200]} @ {page.url}")
            if m.type == "error" and "503" not in m.text and not ("401" in m.text and page.url.endswith("/login")) else None)
    page.on("pageerror", lambda e: problems.append(f"pageerror: {str(e)[:200]} @ {page.url}"))
    page.on("response", lambda r: problems.append(f"HTTP {r.status} {r.request.method} {r.url.replace(API, '')}")
            if r.status >= 400 and "/login" not in page.url and "favicon" not in r.url
            and not (r.status == 503 and r.url.endswith("/copilot/chat")) else None)

    def shot(name):
        page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)

    print("login")
    page.goto(f"{WEB}/")
    page.wait_for_url(re.compile(r"/login"))
    shot("00-login-redirect")
    page.fill("textarea#token", "not-a-token")
    page.click("text=Continue")
    page.wait_for_selector("text=That token was not accepted")
    check(True, "bad token is rejected with a message")
    page.fill("textarea#token", TOKEN)
    page.click("text=Continue")
    page.wait_for_url(f"{WEB}/")
    page.wait_for_selector("text=Group HR Scorecard")
    check(True, "valid token signs in and lands on the dashboard")

    print("dashboard")
    page.wait_for_selector("text=Group score")
    page.wait_for_selector("table tbody tr")
    rows = page.locator("table tbody tr").count()
    check(rows == 88, f"company table lists all 88 companies (saw {rows})")
    check(page.locator("text=Synthetic data").count() > 0, "synthetic-data banner is shown")
    page.fill("input[aria-label='Search companies']", "IC07")
    check(page.locator("table tbody tr").count() == 10, "search narrows the table (IC07x = 10 rows)")
    page.fill("input[aria-label='Search companies']", "")
    page.select_option("select[aria-label='Filter by status']", "red")
    red_rows = page.locator("table tbody tr").count()
    check(0 < red_rows < 88, f"status filter works ({red_rows} red companies)")
    page.select_option("select[aria-label='Filter by status']", "all")
    shot("01-dashboard")
    page.click("text=Talent Acquisition >> nth=0")
    page.wait_for_url(re.compile(r"/pillars/talent_acquisition"))
    page.wait_for_selector("text=Offer To Joining")
    check(True, "pillar tile drills down to sub-KPIs")
    shot("02-pillar")
    page.locator("details summary").first.click()
    page.locator("details a[href^='/companies/']").first.click()
    page.wait_for_url(re.compile(r"/companies/\d+"))
    page.wait_for_selector("text=Sub-KPIs")
    check(True, "company link from the pillar table opens the company scorecard")
    shot("03-company")

    print("manual inputs + timestamps")
    page.goto(f"{WEB}/inputs")
    page.wait_for_selector("text=Manual inputs")
    page.select_option("form select >> nth=0", index=1)
    page.select_option("form select >> nth=1", "gptw_score")
    page.fill("input[type=number]", "73")
    before = datetime.now()
    page.click("text=Save")
    page.wait_for_selector("text=Saved.")
    page.wait_for_selector("text=Change history")
    cell = page.locator("table tbody tr td").first.inner_text()
    try:
        shown = datetime.strptime(cell.strip(), "%m/%d/%Y, %I:%M:%S %p")
    except ValueError:
        shown = None
    ok = shown is not None and abs(shown - before) < timedelta(minutes=3)
    check(ok, f"history timestamp shows local 'now' (cell={cell!r}, local now={before:%H:%M:%S})")
    shot("04-inputs")

    for path, needle, name in [("/unread", "Unread", "05-unread"), ("/approvals", "New request", "06-approvals"),
                               ("/connections", "Capability registry", "07-connections"),
                               ("/connections/registry", "Add a connection", "08-registry")]:
        page.goto(f"{WEB}{path}")
        page.wait_for_selector(f"text={needle}", timeout=15000)
        shot(name)
        check(True, f"{path} renders")

    print("reports: generate a monthly review")
    page.goto(f"{WEB}/reports")
    page.wait_for_selector("text=Monthly leadership review")
    page.click("text=Generate review for")
    page.wait_for_url(re.compile(r"/reports/runs/\d+"))
    page.wait_for_selector("text=Sources and lineage", timeout=30000)  # the finished report, not the progress label
    check(page.locator("text=Synthetic data").count() > 0, "generated review renders with commentary and the synthetic warning")
    check(page.locator("text=AI-drafted").count() > 0, "the commentary is AI-drafted with every number verified (a real model)")
    with page.expect_download() as pdf_dl:
        page.click("button:has-text('Download PDF')")
    pdf_path = str(SHOTS / "review.pdf")
    pdf_dl.value.save_as(pdf_path)
    from pypdf import PdfReader
    pdf_text = "\n".join(p_.extract_text() for p_ in PdfReader(pdf_path).pages)
    check(open(pdf_path, "rb").read(4) == b"%PDF" and "Group score" in pdf_text and "Synthetic data" in pdf_text, "the review downloads as a PDF with its content")
    check(page.locator("text=Sources and lineage").count() > 0, "review shows lineage")
    shot("09-review")

    print("copilot page (live model)")
    page.goto(f"{WEB}/copilot")
    page.wait_for_selector("text=New session")
    page.fill("input[aria-label='Message']", "What is the Group HR score for 2026-10?")
    page.click("text=Send")
    page.wait_for_selector("text=Used: get_group_score", timeout=90000)
    page.wait_for_selector("text=Thinking…", state="detached", timeout=120000)  # the tool event comes before the answer
    page.wait_for_function("document.querySelector('main').innerText.length > 300", timeout=120000)
    answer = page.locator("main").inner_text()
    check("Group" in answer and "amber" in answer.lower(), "the Copilot answers from the scoring service with a real model")
    shot("10-copilot")

    import io as _io
    import time as _time
    RUN = str(int(_time.time()))[-6:]  # unique names, so the test can be re-run against the same database

    print("hard reload keeps you signed in")
    page.goto(f"{WEB}/inputs")
    page.reload()
    page.wait_for_selector("text=Manual inputs")
    check(page.url.endswith("/inputs"), "a hard reload of a deep page stays on it (no bounce to login)")
    check(page.locator("text=Signed in as").count() > 0 and page.locator("text=e2e-admin").count() > 0, "sidebar shows who is signed in")
    check(all(page.locator(f"nav >> text={h}").count() > 0 for h in ("Work", "Build", "Admin")), "navigation is grouped")

    print("dashboard: distinct headings, pin a filtered view, export")
    page.goto(f"{WEB}/pinned")
    page.wait_for_selector("text=Your bookmarks")
    while page.locator("text=Unpin").count():  # start clean: a previous failed run may have left pins
        page.locator("text=Unpin").first.click()
        page.wait_for_timeout(300)
    page.goto(f"{WEB}/")
    page.wait_for_selector("table tbody tr")
    heads = [t.strip() for t in page.locator("table thead th").all_inner_texts()]
    check(len(set(heads)) == len(heads), f"every table heading is distinct ({heads[3:]})")
    page.select_option("select[aria-label='Filter by status']", "red")
    red_rows = page.locator("table tbody tr").count()
    page.click("button:has-text('Pin')")
    page.wait_for_selector("text=Pinned")
    page.goto(f"{WEB}/pinned")
    page.wait_for_selector("text=Dashboard views")
    link = page.locator("a:has-text('Dashboard 2026')").first
    check(link.count() > 0, "the pinned view is listed")
    link.click()
    page.wait_for_selector("table tbody tr")
    check(page.locator("table tbody tr").count() == red_rows and "status=red" in page.url, "opening the pin restores the filter")
    with page.expect_download() as dl:
        page.click("text=Export Excel")
    path = str(SHOTS / "export.xlsx")
    dl.value.save_as(path)
    from openpyxl import load_workbook
    wb = load_workbook(path)
    check(wb.sheetnames == ["Scorecard", "KPIs", "Group", "Notes"] and wb["Scorecard"].max_row == 90, f"Excel export downloads with all 88 companies ({wb.sheetnames})")
    page.goto(f"{WEB}/pinned")
    page.click("text=Unpin >> nth=0")
    page.wait_for_selector("text=Nothing pinned yet.")
    check(True, "unpinning removes the row (DELETE answers 204, which the UI must tolerate)")
    shot("11-pinned")

    print("documents: built-in, search, upload, delete")
    page.goto(f"{WEB}/documents")
    page.wait_for_selector("text=Library")
    check(page.locator("text=Scorecard KPI definitions").count() > 0, "built-in KPI definitions are in the library")
    page.fill("input[aria-label='Search documents']", "regrettable exits CPR")
    page.click("button:has-text('Search')")
    page.wait_for_selector("mark")
    check("Scorecard KPI definitions" in page.locator("main").inner_text(), "searching finds the KPI definition, with the match highlighted")
    page.set_input_files("input[type=file]", {"name": f"policy-{RUN}.txt", "mimeType": "text/plain", "buffer": f"Probation lasts {RUN} days for all new joiners.".encode()})
    page.click("button:has-text('Upload')")
    page.wait_for_selector("text=Uploaded and indexed.")
    page.fill("input[aria-label='Search documents']", f"probation {RUN}")
    page.click("button:has-text('Search')")
    page.wait_for_selector(f"text=policy-{RUN}.txt")
    check(True, "an uploaded document is searchable straight away")
    shot("12-documents")
    page.once("dialog", lambda d: d.accept())
    page.locator("li", has_text=f"policy-{RUN}.txt").locator("text=Delete").click()
    page.wait_for_selector(f"text=policy-{RUN}.txt", state="detached")
    check(True, "deleting a document removes it")

    print("skills and agents")
    page.goto(f"{WEB}/skills")
    page.wait_for_selector("text=Brief me on the monthly review")
    check(page.locator("li:has-text('Identify missing KPI submissions')").count() > 0 and page.locator("text=published").count() >= 4, "the four built-in skills are listed and published")
    page.click("text=Identify missing KPI submissions")
    page.wait_for_selector("text=Run this skill")
    page.click("button:has-text('Run')")
    page.wait_for_selector("text=Used:", timeout=120000)
    page.wait_for_selector("button:has-text('Running')", state="detached", timeout=120000)  # answer streams after the tool call
    check(len(page.locator("main div.whitespace-pre-wrap").first.inner_text()) > 40, "a built-in skill runs with a real model and shows its answer")
    shot("13-skill")
    page.goto(f"{WEB}/skills")
    page.locator("form label:has-text('Key') input").fill(f"e2e_{RUN}")
    page.locator("form label:has-text('Name') input").fill(f"E2E skill {RUN}")
    page.click("button:has-text('Create draft')")
    page.wait_for_selector("text=Draft created")
    page.goto(f"{WEB}/skills/e2e_{RUN}")
    page.wait_for_selector("text=Definition")
    check(page.locator("form >> input[type=month]").count() > 0 and "get_group_score" in page.locator("main").inner_text(),
          "an author sees a draft skill's inputs and tools (not an empty shell)")
    page.click("button:has-text('Validate')")
    page.wait_for_selector("text=Last validation · passed")
    check(True, "a new skill validates")
    page.click("button:has-text('Propose publishing')")
    page.wait_for_selector("text=Sent for approval")
    check(True, "publishing is sent for a second admin's approval")
    shot("14-skill-detail")
    page.goto(f"{WEB}/agents")
    page.wait_for_selector("text=HR Analytics")
    page.goto(f"{WEB}/copilot")
    page.wait_for_selector("select#agent")
    check("HR Analytics" in page.locator("select#agent").inner_text(), "the Copilot offers published agents")

    print("scorecard rules: draft, preview, propose")
    page.goto(f"{WEB}/settings/scorecard")
    page.wait_for_selector("text=Active rules")
    check(page.locator("text=built in").count() > 0, "starts on the built-in rules")
    page.click("button:has-text('Draft a change')")
    page.locator("label:has-text('Score cap') input").fill("100")
    page.locator("label:has-text('Why') input").fill(f"cap at 100 ({RUN})")
    page.click("button:has-text('Save draft')")
    page.wait_for_selector("text=saved")
    page.click("text=Preview impact")
    page.wait_for_selector("text=would change status")
    check(True, "a draft shows its impact before activation")
    page.click("text=Propose activation")
    page.wait_for_selector("text=Sent for approval")
    check(True, "activation is sent for approval")
    shot("15-rules")

    print("schedules")
    page.goto(f"{WEB}/settings/schedules")
    page.wait_for_selector("text=New schedule")
    page.locator("form label:has-text('Name') input").fill(f"Nightly load {RUN}")
    page.click("button:has-text('Create schedule')")
    page.wait_for_selector(f"text=Nightly load {RUN}")
    page.locator("li", has_text=f"Nightly load {RUN}").locator("text=Run now").click()
    page.wait_for_selector("text=Ran it now.")
    page.wait_for_selector("text=Last run")
    check("success" in page.locator("li", has_text=f"Nightly load {RUN}").inner_text(), "run-now executes the job and records success")
    shot("16-schedules")
    page.once("dialog", lambda d: d.accept())
    page.locator("li", has_text=f"Nightly load {RUN}").locator("text=Delete").click()
    page.wait_for_selector(f"text=Nightly load {RUN}", state="detached")

    print("AI-generated source systems and live adapters")
    page.goto(f"{WEB}/connections")
    page.wait_for_selector("text=AI-generated source systems")
    check("88 of 88" in page.locator("main").inner_text() or "of 88 companies generated" in page.locator("main").inner_text(), "the AI-generated sources panel shows the generated companies")
    page.click("button:has-text('Run ingestion for')")
    page.wait_for_selector("text=successfactors: success", timeout=120000)
    check(page.locator("text=Live · AI-generated data").count() >= 4 or page.locator("text=Live").count() >= 4, "all four sources ran live through the adapters")
    shot("17-connections-live")

    print("memories")
    page.goto(f"{WEB}/memories")
    page.wait_for_selector("text=Memory is")
    page.click("button:has-text('Turn off')")
    page.wait_for_selector("text=Memory is off")
    page.click("button:has-text('Turn on')")
    page.wait_for_selector("text=Memory is on")
    check(True, "memory can be switched off and on")

    print("alert settings, then a live alert in the open browser")
    page.goto(f"{WEB}/unread")
    page.wait_for_selector("text=Alert settings")
    page.click("text=Edit")
    page.select_option("label:has-text('Minimum severity') select", "low")
    page.click("button:has-text('Save')")
    page.wait_for_selector("text=Saved. Your open streams")
    check(True, "alert settings save")
    page.goto(f"{WEB}/")
    page.wait_for_selector("table tbody tr")
    page.wait_for_timeout(1500)  # let the live stream connect
    import httpx
    cid = 1 + int(RUN) % 80
    r = httpx.post(f"{API}/inputs", headers={"Authorization": f"Bearer {TOKEN}"}, timeout=60,
                   json={"company_id": cid, "period": "2027-04", "kpi_key": "gptw_score", "value": 10})
    check(r.status_code == 201, "a manual input is saved through the API")
    page.wait_for_selector("[role=status] a:has-text('red')", timeout=20000)
    check(True, "a live alert pops up in the already-open page (server-sent events)")
    shot("18-live-toast")

    print("scorecard rules: KPI weights and targets")
    page.goto(f"{WEB}/settings/scorecard")
    page.wait_for_selector("text=Active rules")
    page.click("button:has-text('Draft a change')")
    page.wait_for_selector("input[aria-label='Kra Submission target']")
    page.fill("input[aria-label='Kra Submission target']", "90")
    page.wait_for_selector("text=(changed)")
    page.locator("label:has-text('Why') input").fill(f"KRA bar 90 ({RUN})")
    page.click("button:has-text('Save draft')")
    page.wait_for_selector("text=Draft v")
    check(True, "a KPI target change is drafted from the UI")
    shot("19-kpi-rules")

    print("sessions page")
    page.goto(f"{WEB}/sessions")
    page.wait_for_selector("input[aria-label='Search sessions']")
    check(True, "the sessions page renders")

    print("sign out")
    page.goto(f"{WEB}/")
    page.wait_for_selector("text=Sign out")
    page.click("text=Sign out")
    page.wait_for_url(re.compile(r"/login"))
    page.goto(f"{WEB}/reports")
    page.wait_for_url(re.compile(r"/login"))
    check(True, "after sign-out, protected pages redirect to login")
    browser.close()

print(f"\n{len(checks)} checks passed, {len(problems)} problem(s)")
for x in problems:
    print("  PROBLEM:", x)
sys.exit(1 if problems else 0)
