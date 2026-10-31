"""Screenshot every route for visual review.

Usage (servers running):  cd backend && PYTHONPATH=. uv run --with playwright python ../e2e/shots.py [label]
Env: WEB=http://localhost:3000  SHOTS=<dir>  (default: <repo>/e2e/shots/<label>)
Signs in by minting a dev token, the same way smoke.py does, and storing it where the app reads it.
"""
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.core.security import Role, make_token

WEB = os.environ.get("WEB", "http://localhost:3000")
LABEL = sys.argv[1] if len(sys.argv) > 1 else "current"
OUT = Path(os.environ.get("SHOTS", Path(__file__).parent / "shots" / LABEL))
OUT.mkdir(parents=True, exist_ok=True)
TOKEN = make_token("e2e-admin", Role.ADMIN, None)

ROUTES = os.environ.get("ROUTES", ",".join(["home", "company", "chat", "actions", "workflows", "reports", "documents", "knowledge", "memory", "dream"])).split(",")

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script(f"localStorage.setItem('chro_token', '{TOKEN}'); localStorage.setItem('theme', '{os.environ.get('THEME', 'light')}')")
    page = ctx.new_page()
    for route in ROUTES:
        page.goto(f"{WEB}/{route}", wait_until="load")
        page.wait_for_timeout(2500)
        page.screenshot(path=str(OUT / f"{route}.png"), full_page=True)
        print("shot", route)
    ctx2 = browser.new_context(viewport={"width": 1440, "height": 900})
    login = ctx2.new_page()
    login.goto(f"{WEB}/login", wait_until="load")
    login.wait_for_timeout(1000)
    login.screenshot(path=str(OUT / "login.png"))
    print("shot login")
    browser.close()
print("saved to", OUT)
