"""docassure ベンチマーク: script が動き JSON が出ること、トラップで FP が 0 であることを検証する。目標未達では落とさない。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import docassure_benchmark as B  # noqa: E402


def test_fixture_counts():
    cases = B.load_cases()
    cats = {}
    for c in cases:
        cats[c["category"]] = cats.get(c["category"], 0) + 1
    assert len(cats) == 12 and min(cats.values()) >= 4
    assert cats["false_positive_trap"] >= 12


def test_benchmark_runs_and_writes_json():
    res = B.run(write=True)
    data = json.loads((B.EVAL / "result.json").read_text(encoding="utf-8"))
    for k in ("overall", "by_category", "mutation", "adversarial_traps", "fixtures"):
        assert k in data
    assert data["fixtures"]["total_cases"] == res["fixtures"]["total_cases"]
    assert (B.EVAL / "README.md").exists()


def test_traps_have_no_false_positives():
    res = B.run(write=False)
    assert res["adversarial_traps"]["false_positives"] == 0, res["adversarial_traps"]["fp_detail"]
    assert res["adversarial_traps"]["must_not_hits"] == 0
