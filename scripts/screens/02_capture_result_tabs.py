"""実行結果画面の成果物タブ／サブタブを全部撮る（capture.py で失敗した分）。"""
from __future__ import annotations
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
DOMAIN, RUN_ID = "demomart", "20260828-143210"
PATH = f"/runs/{DOMAIN}/{RUN_ID}"
results = []

def snap(page, sid, group, name, note):
    rec = {"id": sid, "group": group, "name": name, "path": PATH, "note": note,
           "status": 200, "final_url": page.url.replace(BASE, "")}
    try:
        page.wait_for_timeout(700)
        f = OUT / f"{sid}.png"
        page.screenshot(path=str(f), full_page=True)
        rec.update(ok=True, file=f.name, title=page.title())
    except Exception as exc:
        rec.update(ok=False, error=f"{type(exc).__name__}: {exc}")
    results.append(rec)
    print(("OK  " if rec.get("ok") else "FAIL"), sid, name, rec.get("error", ""))

with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="ja-JP")
    page = ctx.new_page(); page.on("dialog", lambda d: d.dismiss())
    page.goto(BASE + PATH, wait_until="networkidle", timeout=25000)
    page.wait_for_timeout(1500)

    # 成果物カード（実行結果 / 解析結果 / 実行結果レポート）
    cards = page.query_selector_all(".rr-artifact-card, .run-artifact-card, [data-artifact]")
    print("artifact cards:", len(cards))

    def visible_tabs():
        return [t for t in page.query_selector_all(".result-tab") if t.is_visible()]

    tabs = visible_tabs()
    print("visible result-tab:", len(tabs), [t.inner_text().strip().replace("\n"," ") for t in tabs])
    for i in range(len(tabs)):
        tabs = visible_tabs()
        if i >= len(tabs): break
        label = tabs[i].inner_text().strip().replace("\n", " ")
        try:
            tabs[i].click(timeout=8000)
        except Exception as exc:
            results.append({"id": f"D07-T{i+1:02d}", "group": "System 01 / 実行結果タブ",
                            "name": f"実行結果 › {label}", "path": PATH,
                            "note": "成果物タブ", "ok": False, "error": str(exc)[:200]})
            print("FAIL click", label); continue
        page.wait_for_timeout(1200)
        snap(page, f"D07-T{i+1:02d}", "System 01 / 実行結果タブ",
             f"実行結果 › {label}", "実行結果画面の左レール（成果物タブ）")
        subs = [s for s in page.query_selector_all(".result-subtab") if s.is_visible()]
        for j in range(len(subs)):
            subs = [s for s in page.query_selector_all(".result-subtab") if s.is_visible()]
            if j >= len(subs): break
            slabel = subs[j].inner_text().strip().replace("\n", " ")
            try:
                subs[j].click(timeout=6000)
            except Exception:
                print("skip sub", slabel); continue
            page.wait_for_timeout(900)
            snap(page, f"D07-T{i+1:02d}-S{j+1:02d}", "System 01 / 実行結果タブ",
                 f"実行結果 › {label} › {slabel}", "成果物タブ内のサブタブ")

    b.close()

(OUT / "manifest2.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print("追加:", len(results), "成功:", sum(1 for r in results if r.get("ok")))
