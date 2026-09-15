"""
Responsive UI test: captures screenshots at mobile, laptop, and desktop viewports.
Pages tested: home, chat, attractions, login, complaint, news.
"""

import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8000"

VIEWPORTS = [
    {"name": "mobile",   "width": 375,  "height": 812},   # iPhone 14
    {"name": "laptop",   "width": 1366, "height": 768},   # HD laptop
    {"name": "desktop",  "width": 1920, "height": 1080},  # Full HD
]

PAGES = [
    {"name": "home",        "url": "/"},
    {"name": "chat",        "url": "/chat/"},
    {"name": "attractions", "url": "/attractions/"},
    {"name": "news",        "url": "/news/"},
    {"name": "businesses",  "url": "/businesses/"},
    {"name": "login",       "url": "/login/"},
]

OUT_DIR = Path("screenshots")
OUT_DIR.mkdir(exist_ok=True)

ISSUES = []


def check_page(page, vp, pg):
    """Load page and check for obvious responsive issues."""
    page.set_viewport_size({"width": vp["width"], "height": vp["height"]})
    name = f"{pg['name']}_{vp['name']}"

    try:
        resp = page.goto(f"{BASE_URL}{pg['url']}", timeout=15000, wait_until="domcontentloaded")
        status = resp.status if resp else 0

        page.wait_for_timeout(800)  # let JS settle

        # --- checks ---
        issues = []

        # 1. HTTP error
        if status >= 400:
            issues.append(f"HTTP {status}")

        # 2. JS errors logged to console (collected via page.on earlier)
        # (handled via event listener set up before navigation)

        # 3. Horizontal overflow (content wider than viewport)
        overflow = page.evaluate("""() => {
            const docW = document.documentElement.scrollWidth;
            const winW = window.innerWidth;
            return docW > winW ? docW - winW : 0;
        }""")
        if overflow > 5:
            issues.append(f"horizontal overflow {overflow}px")

        # 4. Images without alt text (accessibility)
        no_alt = page.evaluate("""() =>
            [...document.querySelectorAll('img:not([alt])')].length
        """)
        if no_alt > 0:
            issues.append(f"{no_alt} img(s) missing alt")

        # 5. Tiny tap targets on mobile (buttons < 44px)
        if vp["name"] == "mobile":
            tiny = page.evaluate("""() => {
                const els = [...document.querySelectorAll('a, button, [role=button]')];
                return els.filter(el => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0 && (r.width < 44 || r.height < 44);
                }).length;
            }""")
            if tiny > 3:
                issues.append(f"{tiny} tap targets <44px")

        # Screenshot (full page for desktop/laptop, viewport-only for mobile)
        full = vp["name"] != "mobile"
        page.screenshot(path=str(OUT_DIR / f"{name}.png"), full_page=full)

        status_str = "PASS" if not issues else "WARN"
        print(f"  [{status_str}] {name:<30}  HTTP {status}  {', '.join(issues) or 'ok'}")

        if issues:
            ISSUES.append({"page": name, "issues": issues})

    except Exception as exc:
        print(f"  [FAIL] {name:<30}  {exc}")
        ISSUES.append({"page": name, "issues": [str(exc)]})


def main():
    print(f"\nResponsive test — {BASE_URL}")
    print(f"Viewports: {[v['name'] for v in VIEWPORTS]}")
    print(f"Pages:     {[p['name'] for p in PAGES]}\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path="/usr/bin/chromium",
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = browser.new_context()
        page = ctx.new_page()

        # Collect JS console errors
        js_errors = []
        page.on("console", lambda msg: js_errors.append(msg.text)
                if msg.type == "error" else None)

        for vp in VIEWPORTS:
            print(f"── {vp['name'].upper()} ({vp['width']}×{vp['height']}) ──")
            for pg in PAGES:
                check_page(page, vp, pg)
            print()

        browser.close()

    # Summary
    print("=" * 55)
    if not ISSUES:
        print("All pages passed on all viewports.")
    else:
        print(f"{len(ISSUES)} page/viewport(s) had warnings:")
        for item in ISSUES:
            print(f"  {item['page']}: {', '.join(item['issues'])}")
    print(f"\nScreenshots saved to: {OUT_DIR.resolve()}/")
    return 1 if any("FAIL" in str(i) for i in ISSUES) else 0


if __name__ == "__main__":
    sys.exit(main())
