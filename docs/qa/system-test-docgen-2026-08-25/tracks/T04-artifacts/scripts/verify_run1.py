"""C002-C016: 1回目実行後の成果物検証（改訂: min_value キー・相対パス・2枚/画面・login壁スキップを反映）。"""
import json, re, sys
sys.path.insert(0, "docs/qa/system-test-docgen-2026-08-25/tracks/T04-artifacts/scripts")
from qa_common import OUT, EV, check, report_aggregate, save

stream = (EV / "run1_stream.txt").read_text(encoding="utf-8", errors="replace")
run_ok = bool(re.search(r"RUN_ID:", stream)) and "REPORT_PATH:" in stream
m = re.search(r"SUMMARY:(\{.*\})", stream)
check("T04-C001", run_ok and bool(m), f"RUN_ID/REPORT_PATH present={run_ok}, SUMMARY={m.group(1) if m else 'なし'}")
report = json.loads((OUT / "report.json").read_text(encoding="utf-8"))
screens = report.get("screens", [])
paths = sorted({re.sub(r"^https?://127\.0\.0\.1:9104", "", s.get("url", "")) or "/" for s in screens})
crawled_expected = sorted(["/", "/about", "/products", "/contact", "/form"])
audit = [json.loads(ln) for ln in (OUT / "audit.jsonl").read_text().splitlines() if ln.strip()]
login_skip_documented = any(e.get("event") == "login_wall_detected" and e.get("url", "").endswith("/login") for e in audit)
check("T04-C002", paths == crawled_expected and login_skip_documented,
      f"screens={len(screens)} paths={paths}（選択 6 中 /login はログイン壁検出でスキップ・audit 記録={login_skip_documented}）")
agg = report_aggregate(report)
summ = json.loads(m.group(1)) if m else {}
check("T04-C003", all(summ.get(k) == agg[k] for k in agg), f"SUMMARY={summ} / report.json集計={agg}")
fields = [f for s in screens if s.get("url", "").rstrip("/").endswith("/form")
          for fm in s.get("forms", []) for f in fm.get("fields", [])]
save("form_fields.json", fields)
def vals(key):
    return [{"name": f.get("name"), key: f.get(key)} for f in fields if f.get(key) not in (None, "", False)]
check("T04-C004", bool(vals("required")), f"required={vals('required')}")
check("T04-C005", bool(vals("maxlength")), f"maxlength={vals('maxlength')}")
check("T04-C006", bool(vals("pattern")), f"pattern={vals('pattern')}")
check("T04-C007", bool(vals("min_value")) and bool(vals("max_value")),
      f"min_value={vals('min_value')} max_value={vals('max_value')}（number/date とも抽出）")
html_p = OUT / "report.html"
html = html_p.read_text(encoding="utf-8", errors="replace") if html_p.is_file() else ""
missing_html = [p for p in crawled_expected if p != "/" and p not in html]
check("T04-C008", html_p.is_file() and not missing_html, f"report.html={html_p.is_file()} 不記載={missing_html}（相対パス表記）")
sm, fm2 = OUT / "screens.md", OUT / "forms.md"
smt = sm.read_text(encoding="utf-8", errors="replace") if sm.is_file() else ""
missing_md = [p for p in crawled_expected if p != "/" and p not in smt]
check("T04-C009", sm.is_file() and fm2.is_file() and not missing_md, f"screens.md/forms.md 存在・不記載={missing_md}")
shots = sorted((OUT / "screenshots").glob("*.png")) if (OUT / "screenshots").is_dir() else []
vp = [s for s in shots if not s.name.endswith("_full.png")]
full = [s for s in shots if s.name.endswith("_full.png")]
check("T04-C010", len(vp) == len(screens) and len(full) == len(screens),
      f"viewport={len(vp)} full={len(full)} / screens={len(screens)}（1 画面 2 枚・欠損ゼロ）")
snaps = sorted((OUT / "snapshots").glob("*")) if (OUT / "snapshots").is_dir() else []
check("T04-C011", len(snaps) >= 1, f"snapshots={[s.name for s in snaps]}")
bad = [ln[:80] for ln in (OUT / "audit.jsonl").read_text().splitlines() if ln.strip() and not ln.strip().startswith("{")]
check("T04-C012", bool(audit) and not bad,
      f"lines={len(audit)} events={[e.get('event') for e in audit]}（00:14:52 の先行クロール 2 行を含む＝環境前提）")
site = json.loads((OUT / "site.json").read_text(encoding="utf-8"))
save("site_after_run1.json", site)
check("T04-C013", len(site.get("urls", [])) == 6 and site.get("crawl_mode") == "selected" and site.get("depth") == 1 and site.get("max_pages") == 50,
      f"urls={len(site.get('urls', []))} crawl_mode={site.get('crawl_mode')} depth={site.get('depth')} max_pages={site.get('max_pages')}")
check("T04-C014", list(site.get("login_urls") or []) == [],
      f"login_urls={site.get('login_urls')}（API 経由・client 未指定時。/login のログイン壁検出はサーバ側 audit にあるが site.json へは反映されない: incidents 参照）")
for cid, name in [("T04-C015", "accessibility_audit.json"), ("T04-C016", "technical_health.json")]:
    p = OUT / name
    ok = False; det = "存在しない"
    if p.is_file():
        try:
            d = json.loads(p.read_text(encoding="utf-8")); ok = True; det = f"keys={list(d)[:6]}"
        except ValueError as e: det = f"JSON 破損: {e}"
    check(cid, ok, f"{name}: {det}")
save("run1_report_aggregate.json", agg)
