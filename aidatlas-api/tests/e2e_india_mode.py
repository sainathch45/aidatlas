"""E2E check for the AI-drafted India mode specifically, against the
live deployed site. Verifies the honesty signals actually render: amber
"not official" badge, N/A pool, priority rank instead of a dollar
figure, source citations.

    python tests/e2e_india_mode.py <frontend_url> <screenshot_dir>
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def run(url: str, out_dir: str):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))

        page.goto(url, wait_until="networkidle", timeout=20000)
        page.wait_for_timeout(2500)

        for code, district_count in [("MHD", 6), ("ASF", 2)]:
            print(f"--- {code} ---")
            page.select_option("#crisis-select", code)
            page.wait_for_timeout(1500)

            pool_text = page.text_content("#stat-pool")
            assert "N/A" in pool_text, f"{code}: pool should say N/A, got {pool_text!r}"
            print(f"  OK pool stat: {pool_text!r}")

            btn_text = page.text_content("#run-btn")
            assert "DRAFT" in btn_text, f"{code}: button should say DRAFT, got {btn_text!r}"
            print(f"  OK button label: {btn_text!r}")

            page.click("#run-btn")
            page.wait_for_function(
                "document.getElementById('run-status').textContent.includes('Done') || "
                "document.getElementById('run-status').textContent.includes('failed')",
                timeout=90000,
            )
            status_text = page.text_content("#run-status")
            assert "failed" not in status_text.lower(), f"{code}: draft failed: {status_text}"
            print(f"  OK run-status: {status_text!r}")

            stat_status = page.text_content("#stat-status")
            assert "AI-DRAFTED" in stat_status and "NOT OFFICIAL" in stat_status, f"{code}: {stat_status!r}"
            print(f"  OK stat-status: {stat_status!r}")

            detail_amount_label = page.text_content("#detail-amount-label")
            detail_amount = page.text_content("#detail-amount")
            assert detail_amount_label == "Priority", f"{code}: expected Priority label, got {detail_amount_label!r}"
            assert detail_amount.startswith("#"), f"{code}: expected #N rank, got {detail_amount!r}"
            print(f"  OK detail shows priority rank: {detail_amount!r}")

            sources_visible = not page.is_hidden("#detail-sources")
            assert sources_visible, f"{code}: source citations should be visible"
            sources_text = page.text_content("#detail-sources")
            print(f"  OK sources shown: {sources_text[:80]!r}")

            page.screenshot(path=str(out / f"{code}-drafted.png"))

        print(f"\n{len(errors)} console error(s):")
        for e in errors:
            print(" -", e)
        browser.close()

    print("ALL CHECKS PASSED" if not errors else "CHECKS PASSED WITH CONSOLE ERRORS")


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
