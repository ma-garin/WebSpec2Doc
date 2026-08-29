"""C017-C025: 1回目実行後の API 整合検証。"""
import json, pathlib, sys
sys.path.insert(0, "docs/qa/system-test-docgen-2026-08-25/tracks/T04-artifacts/scripts")
from qa_common import QDOM, OUT, EV, jget, check, report_aggregate, save

report = json.loads((OUT / "report.json").read_text(encoding="utf-8"))
agg = report_aggregate(report)
st, res = jget(f"/api/result?domain={QDOM}")
save("api_result_run1.json", {"status": st, "body": res})
check("T04-C017", st == 200 and res.get("summary") == agg, f"status={st} summary={res.get('summary')} 期待={agg}")
files = res.get("files", {}) if isinstance(res, dict) else {}
nonempty = {k: v for k, v in files.items() if v}
missing = [k for k, v in nonempty.items() if not pathlib.Path(v).is_file()]
check("T04-C018", bool(nonempty) and not missing, f"非空 files={len(nonempty)} 実在しない={missing} 空={sorted(set(files)-set(nonempty))}")
shots_api = res.get("screenshots", [])
shots_fs = sorted(str(p) for p in (OUT / "screenshots").glob("*.png"))
check("T04-C019", sorted(shots_api) == shots_fs and res.get("is_sample") is False,
      f"api={len(shots_api)} fs={len(shots_fs)} is_sample={res.get('is_sample')}")
st, runs = jget(f"/api/runs/{QDOM}")
save("api_runs_run1.json", runs)
rid = str(runs.get("runs", [{}])[0].get("run_id", "")) if runs.get("runs") else ""
(EV / "run1_id.txt").write_text(rid)
check("T04-C020", st == 200 and runs.get("total", 0) >= 1 and rid and runs.get("current_run_id") == rid,
      f"total={runs.get('total')}（00:14 の先行クロール分を含む）run_id={rid} current={runs.get('current_run_id')}")
st, det = jget(f"/api/runs/{QDOM}/{rid}")
save("api_run_detail_run1.json", det)
dfiles = det.get("files", {})
dmiss = [k for k, v in dfiles.items() if v and not pathlib.Path(v).is_file()]
check("T04-C021", st == 200 and det.get("artifacts", {}).get("result") in (True,) and not dmiss and det.get("position", {}).get("index") == 1,
      f"artifacts={det.get('artifacts')} 実在しないfiles={dmiss} position={det.get('position')}")
st1, ex1 = jget(f"/api/runs/{QDOM}/{rid}/exists")
st2, ex2 = jget(f"/api/runs/{QDOM}/99999999-999999/exists")
check("T04-C022", ex1.get("exists") is True and ex2.get("exists") is False, f"実在={ex1} 架空={ex2}")
st3, a1 = jget(f"/api/runs/{QDOM}/{rid}/artifact?name=report.json")
st4, a2 = jget(f"/api/runs/{QDOM}/{rid}/artifact?name=../../../etc/passwd")
check("T04-C023", st3 == 200 and pathlib.Path(a1.get("path", "x")).is_file() and st4 == 404,
      f"report.json status={st3} path 実在={pathlib.Path(a1.get('path','x')).is_file()} traversal status={st4} body={a2}")
st, rres = jget(f"/api/result?domain={QDOM}&run_id={rid}")
check("T04-C024", st == 200 and rres.get("summary") == agg and rres.get("run_id") == rid,
      f"status={st} summary={rres.get('summary')} run_id={rres.get('run_id')}")
st, hist = jget("/api/history/runs")
rows = [r for r in (hist.get("runs", hist) if isinstance(hist, dict) else hist) if isinstance(r, dict) and r.get("domain") == "127.0.0.1:9104"]
save("api_history_runs_run1.json", rows)
keys = ["scope_preset", "depth", "max_pages", "crawl_mode", "target_url_count"]
row = rows[0] if rows else {}
flat = json.dumps(row, ensure_ascii=False)
found = {k: (k in flat) for k in keys}
check("T04-C025", bool(rows) and all(found.values()), f"rows={len(rows)} 条件キー={found} row keys={sorted(row)[:20]}")
