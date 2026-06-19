"""Capture three dashboard screenshots for the README.

Expects a demo dashboard already running at http://127.0.0.1:8765 with the
demo token. Posts the token via /login then snaps Chat, Approvals, Proofs.

Honest output: if a page renders an empty state or error, we save it anyway
and the README copy describes it as the demo state — we do NOT mock content.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"
TOKEN = "midas-demo-token-for-local-preview-only"  # demo only
OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "assets"

SHOTS = [
    ("/", "screenshot-chat.png"),
    ("/approvals", "screenshot-approvals.png"),
    ("/proofs", "screenshot-proofs.png"),
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        page.goto(f"{BASE}/login")
        page.fill("input[name='token']", TOKEN)
        with page.expect_navigation(wait_until="load"):
            page.click("button[type='submit']")
        print(f"after login url={page.url} title={page.title()!r}")

        for route, fname in SHOTS:
            page.goto(f"{BASE}{route}", wait_until="load")
            page.wait_for_timeout(1500)
            target = OUT_DIR / fname
            page.screenshot(path=str(target), full_page=False)
            print(f"wrote {target} ({target.stat().st_size} bytes) url={page.url}")

        browser.close()


if __name__ == "__main__":
    main()
