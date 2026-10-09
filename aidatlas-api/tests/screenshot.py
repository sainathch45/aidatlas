"""One-off visual check: load the real frontend in headless Chromium,
wait for the boot sequence + map to render, capture a screenshot, and
dump any console errors. Not a CI test -- a manual verification tool.

    python tests/screenshot.py <url> <out.png>
"""

import sys

from playwright.sync_api import sync_playwright


def capture(url: str, out_path: str):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: console_errors.append(f"pageerror: {exc}"))

        page.goto(url, wait_until="networkidle", timeout=20000)
        page.wait_for_timeout(2500)  # let the boot sequence finish and map tiles load
        page.screenshot(path=out_path, full_page=False)
        browser.close()

        print(f"Screenshot saved to {out_path}")
        if console_errors:
            print(f"\n{len(console_errors)} console error(s):")
            for e in console_errors:
                print(" -", e)
        else:
            print("No console errors.")


if __name__ == "__main__":
    capture(sys.argv[1], sys.argv[2])
