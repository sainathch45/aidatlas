"""End-to-end interaction test against the real running frontend +
backend: load, run an allocation, click a marker, ask a question.
Screenshots each step for visual review, not just a pass/fail assert,
since UI correctness matters as much as functional correctness here.

    python tests/e2e_flow.py <frontend_url> <out_dir>
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def run(url: str, out_dir: str):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    console_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: console_errors.append(f"pageerror: {exc}"))

        print("1. Loading page...")
        page.goto(url, wait_until="networkidle", timeout=20000)
        page.wait_for_timeout(2500)
        page.screenshot(path=str(out / "1-loaded.png"))
        assert page.is_visible("#app"), "app shell never became visible"
        assert page.is_visible("#map"), "map container missing"
        print("   OK — app shell + map visible")

        print("2. Clicking RUN ALLOCATION (shelter)...")
        page.click("#run-btn")
        page.wait_for_function(
            "document.getElementById('run-status').textContent.includes('Done') || "
            "document.getElementById('run-status').textContent.includes('failed')",
            timeout=60000,
        )
        status_text = page.text_content("#run-status")
        page.screenshot(path=str(out / "2-after-allocation.png"))
        print(f"   run-status: {status_text!r}")
        assert "failed" not in status_text.lower(), f"allocation reported failure: {status_text}"
        stat_status = page.text_content("#stat-status")
        assert "ALLOCATED" in stat_status, f"stat-status didn't update: {stat_status!r}"
        print("   OK — allocation completed, stat-status updated")

        print("3. Checking detail panel auto-populated from top allocation...")
        detail_name = page.text_content("#detail-name")
        detail_amount = page.text_content("#detail-amount")
        print(f"   detail: {detail_name!r} / {detail_amount!r}")
        assert detail_name != "—", "detail panel never populated after allocation"
        assert "$" in detail_amount, f"detail amount not populated: {detail_amount!r}"

        print("4. Clicking a different marker on the map...")
        # Click somewhere in the map area with a marker likely present (Damascus region)
        page.mouse.click(400, 300)
        page.wait_for_timeout(1000)
        page.screenshot(path=str(out / "3-marker-clicked.png"))

        print("5. Asking a question...")
        page.fill("#ask-input", "Which district received the most funding?")
        page.click("#ask-form button[type=submit]")
        page.wait_for_function(
            "!document.querySelector('#ask-log .ask-a:last-child').classList.contains('loading')",
            timeout=30000,
        )
        answer_text = page.text_content("#ask-log .ask-a:last-child")
        page.screenshot(path=str(out / "4-after-ask.png"))
        print(f"   answer: {answer_text!r}")
        assert answer_text.strip(), "ask returned empty answer"

        browser.close()

    print(f"\n{len(console_errors)} console error(s) across the whole flow:")
    for e in console_errors:
        print(" -", e)
    print(f"\nScreenshots in {out}")
    print("ALL CHECKS PASSED" if not console_errors else "CHECKS PASSED WITH CONSOLE ERRORS -- REVIEW ABOVE")


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
