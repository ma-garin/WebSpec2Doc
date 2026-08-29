"""C034-C037: サンプルレポートの is_sample・履歴不混入・再クロール導線。"""
import json, sys
sys.path.insert(0, "docs/qa/system-test-docgen-2026-08-25/tracks/T04-artifacts/scripts")
from qa_common import http, jget, check, save

SD = "sample.webspec2doc.local"
st, body = http("/api/sample-report", method="POST", data=b"")
try: res = json.loads(body)
except ValueError: res = {"_raw": body[:200].decode("utf-8", "replace")}
save("sample_report_resp.json", {"status": st, "body": res})
check("T04-C034", st == 200 and res.get("domain") == SD, f"status={st} body={res}")
st, r = jget(f"/api/result?domain={SD}")
check("T04-C035", st == 200 and r.get("is_sample") is True, f"status={st} is_sample={r.get('is_sample')} summary={r.get('summary')}")
st1, h1 = jget("/api/history")
st2, h2 = jget("/api/history/runs")
blob1, blob2 = json.dumps(h1, ensure_ascii=False), json.dumps(h2, ensure_ascii=False)
save("history_after_sample.json", {"history_has_sample": SD in blob1, "runs_has_sample": SD in blob2})
check("T04-C036", SD not in blob1 and SD not in blob2, f"/api/history 混入={SD in blob1} /api/history/runs 混入={SD in blob2}")
st, site = jget(f"/api/site?domain={SD}")
save("api_site_sample.json", {"status": st, "body": site})
# 事実の記録: site が None なら再クロール導線は前回条件を復元できない（recrawl.js は login_urls を空集合で扱う）
check("T04-C037", st == 200, f"status={st} site={site.get('site')}（None=復元条件なし。導線挙動は incidents 参照）")
