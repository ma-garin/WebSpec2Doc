"""認証画面（ログイン必須モード）のキャプチャ。実際のフローを通して撮る。"""
from __future__ import annotations
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8766"
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
results = []

def snap(page, sid, name, path, note, full=True):
    rec = {"id": sid, "group": "認証・オンボーディング", "name": name, "path": path,
           "note": note, "final_url": page.url.replace(BASE, "")}
    try:
        page.wait_for_timeout(700)
        f = OUT / f"{sid}.png"
        page.screenshot(path=str(f), full_page=full)
        rec.update(ok=True, file=f.name, status=200, title=page.title())
    except Exception as exc:
        rec.update(ok=False, error=f"{type(exc).__name__}: {exc}")
    results.append(rec)
    print(("OK  " if rec.get("ok") else "FAIL"), sid, name, rec.get("error", ""))

def go(page, path):
    return page.goto(BASE + path, wait_until="networkidle", timeout=25000)

with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="ja-JP")
    page = ctx.new_page(); page.on("dialog", lambda d: d.dismiss())

    # 1) 初回セットアップ（ユーザーが1人も居ない状態）
    r = go(page, "/auth/setup")
    snap(page, "A01", "初期セットアップ（管理者の作成）", "/auth/setup",
         "ユーザーが1人も居ない状態でのみ到達する初回セットアップ画面")

    # 未ログインで保護画面に触れたときの誘導
    go(page, "/dashboard")
    snap(page, "A02", "未ログイン時のリダイレクト先", "/dashboard → /auth/login",
         "ログイン必須モードで保護画面に触れたときの挙動")

    # 2) セットアップを実行して管理者を作る
    go(page, "/auth/setup")
    try:
        page.fill("input[name=tenant_name]", "デモ商事")
        page.fill("input[name=name]", "デモ管理者")
        page.fill("input[name=email]", "admin@example.com")
        page.fill("input[name=password]", "Demo-Passw0rd!")
        page.fill("input[name=password_confirm]", "Demo-Passw0rd!")
        page.click("button[type=submit]")
        page.wait_for_load_state("networkidle", timeout=20000)
        print("after setup ->", page.url)
    except Exception as exc:
        print("setup form failed:", exc)

    snap(page, "A03", "セットアップ直後の着地画面（システム選択・ログイン済）", "/systems",
         "初期セットアップ完了後に開くシステム選択ハブ（ログイン済み状態）")

    # 3) ログイン済みのトップバー・ユーザーメニュー
    go(page, "/dashboard")
    try:
        page.click("#user-menu-btn, .topbar-user, [data-user-menu]", timeout=4000)
        page.wait_for_timeout(600)
    except Exception:
        try:
            page.evaluate("""() => { const m=document.querySelector('#user-menu,.user-menu-dropdown,.topbar-user-menu');
                                     if(m){m.classList.remove('hidden'); m.removeAttribute('hidden'); m.style.display='block';} }""")
            page.wait_for_timeout(400)
        except Exception as exc:
            print("user menu:", exc)
    snap(page, "A04", "トップバーのユーザーメニュー（ログイン済）", "/dashboard",
         "アカウント・ユーザー管理・ログアウトへの導線", full=False)

    # 4) テナント選択
    go(page, "/auth/tenant")
    snap(page, "A05", "テナント選択", "/auth/tenant",
         "複数テナントに所属する利用者が作業対象を選ぶ画面")

    # 5) ログアウト → ログイン画面
    try:
        page.evaluate("""() => { const f=document.createElement('form');
            f.method='POST'; f.action='/auth/logout'; document.body.appendChild(f); f.submit(); }""")
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception as exc:
        print("logout:", exc)
    go(page, "/auth/login")
    snap(page, "A06", "ログイン", "/auth/login", "メール／パスワード。モック認証時は選択式も出る")

    # ログイン失敗時の表示
    try:
        page.fill("input[name=email]", "admin@example.com")
        page.fill("input[name=password]", "wrong-password")
        page.click("button[type=submit]")
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception as exc:
        print("login-fail:", exc)
    snap(page, "A07", "ログイン失敗（エラー表示）", "/auth/login",
         "資格情報が誤っている場合のエラー表示")

    # 6) サインアップ
    go(page, "/auth/signup")
    snap(page, "A08", "サインアップ（新規ユーザー登録）", "/auth/signup",
         "招待/自己登録によるユーザー作成")

    b.close()

(OUT / "manifest3.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print("認証系:", len(results), "成功:", sum(1 for r in results if r.get("ok")))
