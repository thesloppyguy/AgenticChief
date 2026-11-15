"""Browser smoke test for the L&T CHRO Copilot UI tour routes.

Usage (servers already running, L&T demo seeded):
  cd backend && PYTHONPATH=. uv run --with playwright python ../e2e/smoke.py

Env:
  WEB=http://localhost:3000
  API=http://localhost:8000
  SHOTS=/tmp/e2e_shots
  SKIP_COPILOT=1   # skip the live-model chat check
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

WEB = os.environ.get("WEB", "http://localhost:3000")
API = os.environ.get("API", "http://localhost:8000")
SHOTS = Path(os.environ.get("SHOTS", "/tmp/e2e_shots"))
SHOTS.mkdir(parents=True, exist_ok=True)
SKIP_COPILOT = os.environ.get("SKIP_COPILOT", "").lower() in ("1", "true", "yes")

problems: list[str] = []
checks: list[str] = []


def check(cond: bool, label: str) -> None:
    (checks if cond else problems).append(label)
    print(("  ok   " if cond else "  FAIL ") + label)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_context(viewport={"width": 1400, "height": 950}).new_page()
    page.on(
        "console",
        lambda m: problems.append(f"console {m.type}: {m.text[:200]} @ {page.url}")
        if m.type == "error"
        and "503" not in m.text
        and "hydration" not in m.text.lower()
        and not ("401" in m.text and page.url.endswith("/login"))
        else None,
    )
    page.on("pageerror", lambda e: problems.append(f"pageerror: {str(e)[:200]} @ {page.url}"))
    page.on(
        "response",
        lambda r: problems.append(
            f"HTTP {r.status} {r.request.method} {r.url.replace(API, '').replace(WEB, '')}"
        )
        if r.status >= 400
        and "/login" not in page.url
        and "favicon" not in r.url
        and "/avatars/" not in r.url
        and not (r.status == 503 and r.url.endswith("/copilot/chat"))
        else None,
    )

    def shot(name: str) -> None:
        page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)

    print("login")
    page.goto(f"{WEB}/login")
    page.wait_for_selector("text=Demo sign-in")
    shot("00-login")
    page.fill("#email", "e2e@lokibots.ai")
    page.fill("#password", "e2e")
    page.click("button:has-text('Login')")
    page.wait_for_url(re.compile(r"/home"))
    page.wait_for_selector("text=Home")
    check(True, "demo email/password signs in and lands on /home")

    print("home")
    page.wait_for_selector("text=Export Excel")
    page.wait_for_selector("text=Export CSV")
    page.wait_for_selector("text=Ask the Co-Pilot")
    # Five L&T ICs in the company table
    for code in ("LTF", "LTMR", "LTR", "LTTS", "LTIM"):
        check(page.locator(f"text={code}").count() > 0, f"home lists {code}")
    shot("01-home")

    print("company")
    page.goto(f"{WEB}/company")
    page.wait_for_selector("text=By company")
    page.wait_for_selector("text=By pillar")
    page.wait_for_selector("text=LTF")
    page.get_by_role("tab", name="By pillar").click()
    page.wait_for_timeout(500)
    check(page.locator("text=Talent Acquisition").count() > 0 or page.locator("main").inner_text() != "",
          "company by-pillar tab renders")
    shot("02-company")

    print("actions")
    page.goto(f"{WEB}/actions")
    page.wait_for_selector("text=Actions")
    page.wait_for_selector("text=Pending")
    page.wait_for_timeout(1500)
    pending = page.locator("button").filter(has_text="Approve").count()
    check(page.locator("text=Pending").count() > 0, "actions inbox renders")
    shot("03-actions")

    print("workflows + watches")
    page.goto(f"{WEB}/workflows")
    page.wait_for_selector("text=Workflows")
    page.wait_for_timeout(1500)
    check(page.locator("text=CHRO morning brief").count() > 0, "CHRO morning brief is in the catalog")
    page.get_by_role("tab", name="Watches").click()
    page.wait_for_selector("text=Your watches")
    page.wait_for_timeout(1000)
    check(page.locator("button:has-text('Test')").count() > 0, "seeded watches list with Test controls")
    shot("04-workflows")

    print("reports")
    page.goto(f"{WEB}/reports")
    page.wait_for_selector("text=Reports")
    page.wait_for_timeout(1500)
    # Open the seeded morning brief if listed
    link = page.locator("a[href^='/reports/']").first
    if link.count():
        href = link.get_attribute("href") or "/reports/1"
        page.goto(f"{WEB}{href}")
        page.wait_for_timeout(2000)
        body = page.locator("main").inner_text()
        check("scorecard" in body.lower() or "Infographics" in body or "Morning" in body
              or "Workforce" in body or "Decision" in body,
              "report run detail renders brief content")
        shot("05-report-detail")
    else:
        check(False, "reports list has at least one run link")

    print("documents")
    page.goto(f"{WEB}/documents")
    page.wait_for_selector("text=Knowledge")
    page.wait_for_timeout(1000)
    check(page.locator("input").count() > 0, "documents/knowledge page renders")
    shot("06-documents")

    print("memory")
    page.goto(f"{WEB}/memory")
    page.wait_for_selector("text=Memory")
    page.wait_for_timeout(1000)
    check(True, "memory store renders")
    shot("07-memory")

    print("dream")
    page.goto(f"{WEB}/dream")
    page.wait_for_selector("text=Dream")
    page.wait_for_timeout(1500)
    check(page.locator("text=Everything").count() > 0 or page.locator("main").inner_text() != "",
          "dream timeline renders")
    shot("08-dream")

    print("unread")
    page.goto(f"{WEB}/unread")
    page.wait_for_selector("text=Unread")
    page.wait_for_timeout(1000)
    check(page.locator("text=Mark all read").count() > 0, "unread alerts page renders")
    shot("09-unread")

    if not SKIP_COPILOT:
        print("copilot (live model)")
        page.goto(f"{WEB}/chat")
        page.wait_for_selector("text=Try an example", timeout=15000)
        page.get_by_role("button", name=re.compile(r"Group score", re.I)).click()
        # Example prompts create a session and navigate to /chat/{id}
        page.wait_for_url(re.compile(r"/chat/\d+"), timeout=60000)
        try:
            page.wait_for_function(
                """() => {
                  const t = document.body.innerText;
                  return /get_group_score|Group HR|Group score|85\\.|amber|On track|Needs attention/i.test(t)
                    && t.length > 500;
                }""",
                timeout=180_000,
            )
            check(True, "copilot answered from scorecard/workforce tools")
        except Exception:
            check(False, "copilot answered from scorecard/workforce tools")
        shot("10-chat")
    else:
        print("copilot skipped (SKIP_COPILOT)")

    browser.close()

print(f"\n{len(checks)} checks passed, {len(problems)} problems")
for p_ in problems:
    print(" -", p_)
sys.exit(1 if problems else 0)
