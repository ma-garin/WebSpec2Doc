#!/usr/bin/env python3
"""T04-C017/C013: 結果パネル表示・再クロールボタン・サンプル識別表示を headless で確認。"""
from pathlib import Path
from playwright.sync_api import sync_playwright

EV = Path(__file__).resolve().parents[1] / "evidence"
BASE = "http://127.0.0.1:8765"
DOM = "127.0.0.1:9104"
SAMPLE = "sample.webspec2doc.local"

def probe(page, domain, tag):
    page.goto(f"{BASE}/#report/{domain}", wait_until="networkidle")
    page.wait_for_timeout(2500)
    page.screenshot(path=str(EV / f"c017_{tag}_panel.png"), full_page=False)
    body = page.inner_text("body")
    recrawl_btns = page.locator("button:visible", has_text="再クロール").count() \
        + page.locator("[onclick*='recrawl']:visible").count()
    print(f"[{tag}] url={page.url}")
    print(f"[{tag}] panel_has_domain={'あり' if domain in body else 'なし'}")
    print(f"[{tag}] recrawl_button_count={recrawl_btns}")
    print(f"[{tag}] sample_badge={'サンプル' in body}")
    heads = [h.strip() for h in body.splitlines() if h.strip()][:12]
    (EV / f"c017_{tag}_text.txt").write_text("\n".join(body.splitlines()[:80]))
    print(f"[{tag}] first_lines={heads[:6]}")

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page(viewport={"width": 1440, "height": 900})
    probe(page, DOM, "9104")
    probe(page, SAMPLE, "sample")
    b.close()
