#!/usr/bin/env python3
"""E. System09 影響分析の独立評価（quality/commercial_eval/system09_independent/、3 ドメイン）。

ドメインごとの cases_*.json を、作成者側の評価（scripts/impact_eval.py）と同じ手順で分析して合算する。
作成者側の tests/fixtures/impact_eval/ は混ぜない。
使い方: venv/bin/python scripts/commercial_eval/system09_eval.py [--mode rule|full]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT), str(ROOT / "src")]
import impact_eval  # noqa: E402

DATA = ROOT / "quality" / "commercial_eval" / "system09_independent"


def main(mode: str) -> dict:
    total = {"tp": 0, "found": 0, "expected": 0, "items": 0, "cases": 0}
    per_domain = {}
    for cases_file in sorted(DATA.glob("cases_*.json")):
        spec = json.loads(cases_file.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            for doc in spec["documents"]:
                shutil.copy(DATA / doc["file"], work / doc["file"])
            for extra in DATA.glob("*.sql"):
                shutil.copy(extra, work / extra.name)
            (work / "cases.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            impact_eval.FIXTURES = work
            res = impact_eval.evaluate(mode)
        n_exp = sum(len(c["expected_items"]) for c in spec["cases"])
        tp = round(res["recall"] * n_exp)
        found = round(tp / res["precision"]) if res["precision"] else 0
        per_domain[cases_file.stem] = {k: res[k] for k in ("cases", "items", "recall", "precision", "candidate_rate")}
        total["tp"] += tp
        total["found"] += found
        total["expected"] += n_exp
        total["items"] += res["items"]
        total["cases"] += res["cases"]
    p = total["tp"] / total["found"] if total["found"] else None
    r = total["tp"] / total["expected"] if total["expected"] else None
    f1 = 2 * p * r / (p + r) if p and r else None
    return {"mode": mode, "cases": total["cases"], "precision": p and round(p, 3), "recall": r and round(r, 3),
            "f1": f1 and round(f1, 3), "found": total["found"], "expected": total["expected"], "per_domain": per_domain}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("rule", "full"), default="rule")
    print(json.dumps(main(ap.parse_args().mode), ensure_ascii=False, indent=1))
