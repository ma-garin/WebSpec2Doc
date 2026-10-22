#!/usr/bin/env python3
"""ADVERSARIAL セット（quality/docassure_eval/adversarial）の測定。全 case が「何も検出してはいけない」。

検出（finding FAIL・conflict・NOT_TESTABLE）が 1 件でもあれば誤検出。severity が info のものは数えない（benchmark と同じ）。
調整には使わない（fixture 固有の分岐を作らない）。再生成: python scripts/docassure_adversarial.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import docassure_benchmark as b  # noqa: E402

ROOT = b.EVAL / "adversarial"


def run(write: bool = True, root: Path = ROOT) -> dict:
    cases = b.load_cases(root)
    rows = []
    for c in cases:
        dets = [d for d in b.detect(c["documents"]) if d.get("severity") != "info"]
        rows.append({"id": c["id"], "fp": [f"{d['kind']}:{d['rule']}" for d in dets]})
    bad = [r for r in rows if r["fp"]]
    n = len(rows)
    res = {"cases": n, "cases_clean": n - len(bad), "cases_with_fp": len(bad),
           "fp_total": sum(len(r["fp"]) for r in bad),
           "specificity": round((n - len(bad)) / n, 3) if n else None,
           "fp_by_rule": Counter(x for r in bad for x in r["fp"]).most_common(),
           "false_positives": bad,
           "caveat": "自作・件数が少ない。誤検出耐性（特異度）の確認用で、再現率は測らない。"}
    if write:
        (root / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


if __name__ == "__main__":
    r = run()
    print(json.dumps({k: r[k] for k in ("cases", "cases_clean", "cases_with_fp", "fp_total", "specificity")}, ensure_ascii=False))
