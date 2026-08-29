"""C048-C049: 実行回ページ（結果パネル）の表示と実ファイルの一致（Playwright headless）。"""
import json, sys, urllib.request
sys.path.insert(0, "docs/qa/system-test-docgen-2026-08-25/tracks/T04-artifacts/scripts")
from qa_common import BASE, QDOM, OUT, EV, check, save
from playwright.sync_api import sync_playwright

run2_id = (EV / "run2_id.txt").read_text().strip()
report = json.loads((OUT / "report.json").read_text(encoding="utf-8"))
n_screens = len(report.get("screens", []))
url = f"{BASE}/runs/127.0.0.1:9104/{run2_id}"
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto(url, wait_until="networkidle", timeout=30000)
    try:
        page.wait_for_function("() => (document.getElementById('r-domain')||{}).textContent.trim().length > 0", timeout=15000)
    except Exception:
        pass
    page.screenshot(path=str(EV / "ui_run_page.png"), full_page=True)
    data = page.evaluate("""() => {
      const txt = id => { const e = document.getElementById(id); return e ? e.textContent.trim() : null; };
      return {
        domain: txt('r-domain'), crawled: txt('r-crawled'),
        tabs: [...document.querySelectorAll('.result-tabs .result-tab')].map(t => t.textContent.trim()),
        panel_visible: !!document.getElementById('result-panel') && getComputedStyle(document.getElementById('result-panel')).display !== 'none',
        kpi: txt('kpi-hero-wrap'),
        links: [...document.querySelectorAll("a[href*='/preview'],a[href*='/download']")].map(a => a.getAttribute('href')).slice(0, 30),
        body_head: document.body.innerText.slice(0, 600),
      };
    }""")
    b.close()
save("ui_run_page.json", data)
dom_ok = data.get("domain") == "127.0.0.1:9104"
kpi = (data.get("kpi") or "") + (data.get("body_head") or "")
count_ok = str(n_screens) in kpi
check("T04-C048", dom_ok and data.get("panel_visible") and count_ok,
      f"domain={data.get('domain')} panel={data.get('panel_visible')} 画面数{n_screens}表示={count_ok} tabs={data.get('tabs')}")
links = data.get("links") or []
bad = []
for href in links:
    try:
        with urllib.request.urlopen(BASE + href if href.startswith('/') else href, timeout=15) as r:
            if r.status != 200: bad.append((href, r.status))
    except Exception as e:  # noqa: BLE001
        bad.append((href, str(e)[:60]))
check("T04-C049", bool(links) and not bad, f"links={len(links)} 失敗={bad} tabs={data.get('tabs')}")
