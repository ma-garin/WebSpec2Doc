"""holdout 測定スクリプトが実行でき、JSON が出ること。精度の閾値では落とさない。"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_holdout_script_runs_and_writes_json():
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "docassure_holdout.py")], capture_output=True, text=True, cwd=ROOT)
    assert p.returncode == 0, p.stderr
    res = json.loads((ROOT / "quality/docassure_eval/holdout/result.json").read_text(encoding="utf-8"))
    assert res["holdout"]["total_cases"] >= 60
    for k in ("precision", "recall", "f1", "critical_recall", "tp", "fp", "fn"):
        assert k in res["overall"]
    assert (ROOT / "quality/docassure_eval/holdout/README.md").exists()
