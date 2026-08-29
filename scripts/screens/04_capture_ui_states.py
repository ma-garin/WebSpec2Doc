from __future__ import annotations
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(sys.argv[1]); results = []

def snap(page, base, sid, group, name, path, note, full=True):
    rec = {"id": sid, "group": group, "name": name, "path": path, "note": note,
           "status": 200, "final_url": page.url.replace(base, "")}
    try:
        page.wait_for_timeout(600)
        f = OUT / f"{sid}.png"; page.screenshot(path=str(f), full_page=full)
        rec.update(ok=True, file=f.name, title=page.title())
    except Exception as exc:
        rec.update(ok=False, error=f"{type(exc).__name__}: {exc}")
    results.append(rec); print(("OK  " if rec.get("ok") else "FAIL"), sid, name, rec.get("error",""))

with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])

    # 認証ありインスタンス: ログインしてユーザーメニューを開く
    AUTH = "http://127.0.0.1:8766"
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="ja-JP")
    pg = ctx.new_page(); pg.on("dialog", lambda d: d.dismiss())
    pg.goto(AUTH + "/auth/login", wait_until="networkidle")
    try:
        pg.fill("input[name=email]", "admin@example.com")
        pg.fill("input[name=password]", "Demo-Passw0rd!")
        pg.click("button[type=submit]"); pg.wait_for_load_state("networkidle", timeout=20000)
        print("login ->", pg.url)
        if "/auth/tenant" in pg.url:
            pg.click("form:has(input[name=tenant_id]) button[type=submit]", timeout=8000)
            pg.wait_for_load_state("networkidle", timeout=20000)
            print("tenant selected ->", pg.url)
    except Exception as exc:
        print("login failed:", exc)
    pg.goto(AUTH + "/dashboard", wait_until="networkidle"); pg.wait_for_timeout(1200)
    pg.click("#usermenu-trigger", timeout=8000); pg.wait_for_timeout(600)
    snap(pg, AUTH, "A04", "認証・オンボーディング",
         "トップバーのユーザーメニュー（ログイン済）", "/dashboard",
         "アカウント／ユーザー管理／テナント管理／ログアウトへの導線", full=False)
    ctx.close()

    # 認証オフインスタンス: ユーザーメニュー（ゲスト表示）とサイドバー折りたたみ
    APP = "http://127.0.0.1:8765"
    ctx2 = b.new_context(viewport={"width": 1440, "height": 900}, locale="ja-JP")
    pg2 = ctx2.new_page(); pg2.on("dialog", lambda d: d.dismiss())
    pg2.goto(APP + "/dashboard", wait_until="networkidle"); pg2.wait_for_timeout(1200)
    pg2.click("#usermenu-trigger", timeout=8000); pg2.wait_for_timeout(600)
    snap(pg2, APP, "U01", "共通UI状態", "ユーザーメニュー（認証オフ・ゲスト）", "/dashboard",
         "認証オフ運用時のユーザーメニュー表示", full=False)

    pg2.goto(APP + "/dashboard", wait_until="networkidle"); pg2.wait_for_timeout(1000)
    pg2.click("#sidebar-toggle-btn", timeout=8000); pg2.wait_for_timeout(800)
    snap(pg2, APP, "U02", "共通UI状態", "サイドバー折りたたみ状態", "/dashboard",
         "サイドバーを畳んだときのレイアウト", full=False)

    # サイドバーのシステム別ナビ（テスト活動支援 / AutoRun）

    # モバイル幅（レスポンシブ）
    ctx3 = b.new_context(viewport={"width": 390, "height": 844}, locale="ja-JP",
                         device_scale_factor=2, is_mobile=True, has_touch=True)
    pg3 = ctx3.new_page(); pg3.on("dialog", lambda d: d.dismiss())
    for sid, path, name in [("R01", "/systems", "システム選択（モバイル幅 390px）"),
                            ("R02", "/dashboard", "ダッシュボード（モバイル幅 390px）"),
                            ("R03", "/generate", "仕様書生成（モバイル幅 390px）")]:
        pg3.goto(APP + path, wait_until="networkidle"); pg3.wait_for_timeout(1200)
        snap(pg3, APP, sid, "レスポンシブ（モバイル幅）", name, path,
             "iPhone 相当 390×844 での表示")
    b.close()

(OUT / "manifest4.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print("追加:", len(results), "成功:", sum(1 for r in results if r.get("ok")))
