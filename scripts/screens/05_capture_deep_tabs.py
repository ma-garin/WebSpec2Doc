"""実行結果画面の第3階層タブ（UML図種別・CI形式・AutoRunプレビュー）を撮る。"""
from __future__ import annotations
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"
OUT = Path(sys.argv[1]); results = []
DOMAIN, RUN_ID = "demomart", "20260828-143210"
PATH = f"/runs/{DOMAIN}/{RUN_ID}"
THIRD = ".uml-subtab, .autorun-preview-tab, .ci-format-tabs button"

def vis(page, sel):
    return [e for e in page.query_selector_all(sel) if e.is_visible()]

def snap(page, sid, name, note):
    rec = {"id": sid, "group": "System 01 / 実行結果タブ", "name": name, "path": PATH,
           "note": note, "status": 200, "final_url": PATH}
    try:
        page.wait_for_timeout(700)
        f = OUT / f"{sid}.png"; page.screenshot(path=str(f), full_page=True)
        rec.update(ok=True, file=f.name, title=page.title())
    except Exception as exc:
        rec.update(ok=False, error=f"{type(exc).__name__}: {exc}")
    results.append(rec); print(("OK  " if rec.get("ok") else "FAIL"), sid, name, rec.get("error",""))

with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    page = b.new_context(viewport={"width":1440,"height":900}, locale="ja-JP").new_page()
    page.on("dialog", lambda d: d.dismiss())
    page.goto(BASE + PATH, wait_until="networkidle"); page.wait_for_timeout(1500)

    n_tabs = len(vis(page, ".result-tab"))
    for i in range(n_tabs):
        tabs = vis(page, ".result-tab")
        if i >= len(tabs): break
        tlabel = tabs[i].inner_text().strip().replace("\n", " ")
        try: tabs[i].click(timeout=8000)
        except Exception: continue
        page.wait_for_timeout(1200)
        n_subs = len(vis(page, ".result-subtab"))
        sub_range = range(n_subs) if n_subs else [None]
        for j in sub_range:
            slabel = ""
            if j is not None:
                subs = vis(page, ".result-subtab")
                if j >= len(subs): break
                slabel = subs[j].inner_text().strip().replace("\n", " ")
                try: subs[j].click(timeout=6000)
                except Exception: continue
                page.wait_for_timeout(900)
            thirds = vis(page, THIRD)
            if len(thirds) <= 1:
                continue
            for k in range(len(thirds)):
                thirds = vis(page, THIRD)
                if k >= len(thirds): break
                ulabel = thirds[k].inner_text().strip().replace("\n", " / ")
                try: thirds[k].click(timeout=6000)
                except Exception: continue
                page.wait_for_timeout(1000)
                sid = f"D07-T{i+1:02d}-S{(j+1) if j is not None else 0:02d}-U{k+1:02d}"
                nm = f"実行結果 › {tlabel}" + (f" › {slabel}" if slabel else "") + f" › {ulabel}"
                snap(page, sid, nm, "成果物タブ内の第3階層（図種別・形式切替）")
    b.close()

(OUT / "manifest5.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print("第3階層:", len(results), "成功:", sum(1 for r in results if r.get("ok")))
