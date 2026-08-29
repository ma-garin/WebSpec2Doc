"""C027-C033: 2回目実行後の上書き・保全・履歴・再クロール条件検証。"""
import json, re, pathlib, sys
sys.path.insert(0, "docs/qa/system-test-docgen-2026-08-25/tracks/T04-artifacts/scripts")
from qa_common import QDOM, OUT, EV, jget, check, report_aggregate, save

run1_id = (EV / "run1_id.txt").read_text().strip()
report = json.loads((OUT / "report.json").read_text(encoding="utf-8"))
paths = sorted({re.sub(r"^https?://127\.0\.0\.1:9104", "", s.get("url", "")) or "/" for s in report.get("screens", [])})
check("T04-C027", paths == sorted(["/", "/products", "/dashboard"]), f"現 report.json paths={paths}")
st, runs = jget(f"/api/runs/{QDOM}")
save("api_runs_run2.json", runs)
ids = [str(r.get("run_id")) for r in runs.get("runs", [])]
prev_total = json.loads((EV / "api_runs_run1.json").read_text()).get("total", 1)
check("T04-C028", runs.get("total") == prev_total + 1 and ids[0] > ids[1] and ids[1] == run1_id,
      f"total={runs.get('total')}（前回 {prev_total}+1 期待）ids={ids} run1={run1_id}")
run2_id = ids[0] if ids else ""
(EV / "run2_id.txt").write_text(run2_id)
agg1 = json.loads((EV / "run1_report_aggregate.json").read_text())
st, r1 = jget(f"/api/result?domain={QDOM}&run_id={run1_id}")
check("T04-C029", st == 200 and r1.get("summary") == agg1, f"status={st} run1 summary={r1.get('summary')} 期待={agg1}")
rdir = OUT / "runs" / run1_id / "screenshots"
n = len(list(rdir.glob("*.png"))) if rdir.is_dir() else 0
check("T04-C030", n == agg1["screens"], f"runs/{run1_id}/screenshots png={n} 期待={agg1['screens']}")
st, hist = jget("/api/history/runs")
rows = [r for r in (hist.get("runs", hist) if isinstance(hist, dict) else hist) if isinstance(r, dict) and r.get("domain") == "127.0.0.1:9104"]
save("api_history_runs_run2.json", rows)
ts = [str(r.get("timestamp") or r.get("started_at") or r.get("at") or "") for r in rows]
rids = [str(r.get("run_id", "")) for r in rows]
check("T04-C031", len(rows) >= 2 and ts == sorted(ts, reverse=True) and {run1_id, run2_id} <= set(rids),
      f"rows={len(rows)} 時刻={ts} run_ids={rids}")
st, site = jget(f"/api/site?domain={QDOM}")
site = site.get("site") or {}
save("api_site_run2.json", site)
urls = sorted(u.replace("http://127.0.0.1:9104", "") or "/" for u in site.get("urls", []))
check("T04-C032", urls == sorted(["/", "/products", "/dashboard"]) and site.get("crawl_mode") == "selected" and site.get("depth") == 1,
      f"urls={urls} crawl_mode={site.get('crawl_mode')} depth={site.get('depth')} max_pages={site.get('max_pages')}")
check("T04-C033", any(u.endswith("/dashboard") for u in site.get("login_urls", [])), f"login_urls={site.get('login_urls')}")
