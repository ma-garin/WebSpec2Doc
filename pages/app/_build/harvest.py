"""実アプリのhappy-path通信を採取し、静的再生用フィクスチャを生成する。

本物UIをPlaywrightで操作しつつ、全レスポンス（画面HTML/API/JSON/画像）を記録。
- テキスト応答: fixtures.json に {METHOD pathname: [ {status,ct,body}, ... ]}（順序リスト）
- バイナリ応答(画像): assets/blob_N.<ext> に保存し、fixtures では {blob: path} 参照
- 画面HTML(GET /): index.captured.html に別保存（<base>調整は後段で行う）
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

APP = "http://127.0.0.1:8765"
TARGET = "http://127.0.0.1:8766/"
OUT = Path(sys.argv[1])
(OUT / "assets").mkdir(parents=True, exist_ok=True)

records: dict[str, list] = {}
blob_i = 0


def keyof(method: str, url: str) -> str:
    p = urlsplit(url)
    return f"{method} {p.path}"


def on_response(resp):
    global blob_i
    try:
        req = resp.request
        url = resp.url
        if not url.startswith(APP):
            return
        p = urlsplit(url)
        # 静的資産はリポジトリから直接配るので採取不要
        if p.path.startswith("/static/") or p.path in ("/favicon.ico", "/favicon.svg"):
            return
        method = req.method
        status = resp.status
        ct = resp.headers.get("content-type", "")
        entry = {"status": status, "ct": ct, "query": p.query}
        try:
            body = resp.body()
        except Exception:
            body = b""
        is_text = any(t in ct for t in ("json", "text", "html", "javascript", "xml", "csv", "event-stream", "mermaid"))
        if is_text or (not ct and len(body) < 200000):
            try:
                entry["body"] = body.decode("utf-8", "replace")
            except Exception:
                entry["body"] = ""
        else:
            ext = {"image/png": "png", "image/jpeg": "jpg", "image/svg+xml": "svg",
                   "image/webp": "webp", "application/zip": "zip",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
                   "application/pdf": "pdf"}.get(ct.split(";")[0].strip(), "bin")
            blob_i += 1
            name = f"assets/blob_{blob_i}.{ext}"
            (OUT / name).write_bytes(body)
            entry["blob"] = name
        records.setdefault(keyof(method, url), []).append(entry)
    except Exception as e:
        print("  ! on_response err:", e)


def click_if(page, sel, timeout=1500):
    try:
        loc = page.locator(sel).first
        if loc.is_visible(timeout=timeout):
            loc.click()
            return True
    except Exception:
        pass
    return False


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="ja-JP")
    page = ctx.new_page()
    page.set_default_timeout(30000)
    page.on("response", on_response)

    print("goto /")
    resp = page.goto(APP, wait_until="networkidle")
    page.wait_for_timeout(1500)
    # 採取した画面HTML（レンダリング後DOMではなく、サーバ配信の生HTML）を保存
    # 生HTMLは最初のドキュメントレスポンスから採る
    (OUT / "index.captured.html").write_text(resp.text(), encoding="utf-8")

    for sel in ["#arm-close", ".tour-skip", "[data-tour-skip]", "button:has-text('スキップ')",
                "button:has-text('後で')", "#onboarding-skip"]:
        if click_if(page, sel, 800):
            page.wait_for_timeout(300)

    print("fill URL + start")
    page.fill("#hero-url", TARGET)
    page.wait_for_timeout(200)
    page.click("#hero-start-btn")
    page.wait_for_timeout(1000)

    if not page.locator("#discover-loading").is_visible():
        click_if(page, "#discover-btn")
    page.wait_for_timeout(1500)

    print("wait discovery done")
    page.locator("#p1-next-btn").wait_for(state="visible", timeout=180000)
    for _ in range(120):
        if page.locator("#p1-next-btn").is_enabled():
            break
        page.wait_for_timeout(1000)
    page.wait_for_timeout(500)
    page.click("#p1-next-btn")
    page.wait_for_timeout(1000)

    print("submit crawl")
    page.click("#submit-btn")
    page.wait_for_timeout(1500)
    try:
        page.locator("#exec-preview-image").wait_for(state="visible", timeout=60000)
    except Exception:
        pass

    print("wait report ready")
    page.locator("#btn-view-report").wait_for(state="visible", timeout=600000)
    page.wait_for_timeout(500)
    overlay = page.locator("#completion-overlay")
    if overlay.is_visible():
        ob = overlay.locator("button:has-text('レポート')").first
        if ob.count() and ob.is_visible():
            ob.click()
        else:
            page.keyboard.press("Escape"); page.wait_for_timeout(400); page.click("#btn-view-report")
    else:
        page.click("#btn-view-report")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2500)

    print("tour report tabs")
    for tab in ("overview", "screens", "test-design", "flow", "runs", "history"):
        loc = page.locator(f".result-tab[data-tab='{tab}']")
        if loc.count() and loc.first.is_visible():
            loc.first.click()
            page.wait_for_timeout(1800)
    # サブタブ（遷移図の各UML・遷移表）も踏む
    for sub in ("シーケンス図", "コミュニケーション図", "アクティビティ図", "遷移表"):
        click_if(page, f"button:has-text('{sub}')", 800)
        page.wait_for_timeout(800)

    ctx.close(); b.close()

# シリアライズ
(OUT / "fixtures.json").write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
keys = sorted(records.keys())
print(f"\ncaptured {len(keys)} endpoint-keys, {sum(len(v) for v in records.values())} responses, {blob_i} blobs")
for k in keys:
    print(f"  {len(records[k]):3}x  {k}")
