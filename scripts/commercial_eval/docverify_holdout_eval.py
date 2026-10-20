#!/usr/bin/env python3
"""D. System06 規則の検証用セット（quality/commercial_eval/docverify_holdout/）での評価。

規則の調整に使った ja_v1 とは別の作成者が、製品コードを見ずに付けたラベルと照合する。
使い方: venv/bin/python scripts/commercial_eval/docverify_holdout_eval.py [--data <jsonl>] [--exclude <txt>]
--exclude には評価から外す文を 1 行 1 文で書く（改善の作業中に見てしまった文など。外した件数は結果に残す）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(Path(__file__).resolve().parent), str(ROOT), str(ROOT / "src")]
from common import prf  # noqa: E402
from web.services.docverify import checks  # noqa: E402

DATA = ROOT / "quality" / "commercial_eval" / "docverify_holdout" / "holdout.jsonl"
RULES = {
    "AMBIGUOUS": ("RD.AMBIGUOUS", "REQ.AMBIGUOUS_TERM"),
    "REQ.INCOMPLETE": ("REQ.INCOMPLETE",), "REQ.OPEN_ENDED": ("REQ.OPEN_ENDED",),
    "REQ.UNIVERSAL": ("REQ.UNIVERSAL",), "REQ.AND_OR": ("REQ.AND_OR",),
    "REQ.MEASURABILITY": ("REQ.MEASURABILITY",), "REQ.MULTIPLE_REQUIREMENTS": ("REQ.MULTIPLE_REQUIREMENTS",),
}


def main(data: Path = DATA, exclude: Path | None = None) -> dict:
    rows = [json.loads(line) for line in data.read_text(encoding="utf-8").splitlines() if line.strip()]
    seen = {t.strip() for t in exclude.read_text(encoding="utf-8").splitlines() if t.strip()} if exclude else set()
    excluded = sum(r["text"].strip() in seen for r in rows)
    rows = [r for r in rows if r["text"].strip() not in seen]
    out, misses = {}, {}
    for label, members in RULES.items():
        tp = fp = fn = 0
        for r in rows:
            found = {f["rule"] for f in checks.candidates([{"id": "p1", "location": "eval", "text": r["text"]}], apply_disabled=False)}
            hit, want = bool(found & set(members)), label in r["labels"]
            tp, fp, fn = tp + (hit and want), fp + (hit and not want), fn + (want and not hit)
            if hit != want:
                misses.setdefault(label, []).append(("FP " if hit else "FN ") + r["id"])
        out[label] = prf(tp, fp, fn)
    for label in out:
        o = out[label]
        o.update({"n": len(rows), "n_gold": o["tp"] + o["fn"], "n_predicted": o["tp"] + o["fp"]})
    return {"n": len(rows), "excluded": excluded, "rules": out, "misses": misses}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=DATA)
    ap.add_argument("--exclude", type=Path)
    a = ap.parse_args()
    res = main(a.data, a.exclude)
    (a.data.parent / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res["rules"], ensure_ascii=False, indent=1))
