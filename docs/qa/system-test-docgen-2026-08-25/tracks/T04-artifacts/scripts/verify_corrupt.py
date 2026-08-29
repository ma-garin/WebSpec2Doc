"""C046-C047: report.json 破損・欠落時の /api/result の縮退。必ず復元する。"""
import json, shutil, sys
sys.path.insert(0, "docs/qa/system-test-docgen-2026-08-25/tracks/T04-artifacts/scripts")
from qa_common import QDOM, OUT, EV, jget, check, save

target = OUT / "report.json"
backup = EV / "report.json.bak"
shutil.copy2(target, backup)
try:
    target.write_text("{broken json!!", encoding="utf-8")
    st, r = jget(f"/api/result?domain={QDOM}")
    save("api_result_corrupt.json", {"status": st, "body": r})
    check("T04-C046", st != 500 and isinstance(r, dict), f"status={st} summary={r.get('summary') if isinstance(r, dict) else r}（500/クラッシュしないこと。エラー明示の有無は observation）")
    target.unlink()
    st2, r2 = jget(f"/api/result?domain={QDOM}")
    save("api_result_missing.json", {"status": st2, "body": r2})
    check("T04-C047a", st2 != 500 and isinstance(r2, dict), f"欠落時 status={st2} summary={r2.get('summary') if isinstance(r2, dict) else r2}")
finally:
    shutil.copy2(backup, target)
st3, r3 = jget(f"/api/result?domain={QDOM}")
check("T04-C047b", st3 == 200 and isinstance(r3.get("summary"), dict), f"復元後 status={st3} summary={r3.get('summary')}")
