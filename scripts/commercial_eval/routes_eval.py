#!/usr/bin/env python3
"""B. route / API 抽出の評価。

製品の reverse_analysis.json（static_candidates）を quality/commercial_eval/routes/expected.json と照合する。
使い方: venv/bin/python scripts/commercial_eval/routes_eval.py <reverse_analysis.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import norm_path, prf  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = ROOT / "quality" / "commercial_eval" / "routes" / "expected.json"


def evaluate(report: dict, expected: dict) -> dict:
    cases = expected["cases"]
    want = {(c["kind"], norm_path(c["path"])) for c in cases if c["should_detect"]}
    trap = {(c["kind"], norm_path(c["path"])) for c in cases if not c["should_detect"]}
    # 画面（web/routes/reverse_analysis.py）と同じく、path が無ければ expression を候補の値として扱う
    def value(c: dict) -> str:
        return (c.get("path") or c.get("expression") or "").strip("`'\"")

    got = {(c.get("kind"), norm_path(value(c))) for c in report.get("static_candidates") or []
           if c.get("kind") in ("route", "api") and value(c).startswith("/")}
    out = {}
    for kind in ("route", "api", None):
        w = {x for x in want if kind is None or x[0] == kind}
        g = {x for x in got if kind is None or x[0] == kind}
        out[kind or "all"] = prf(len(w & g), len(g - w), len(w - g))
    out["trap_hits"] = sorted(p for _, p in (got & trap))
    out["missed"] = sorted(f"{k}:{p}" for k, p in want - got)
    out["extra"] = sorted(f"{k}:{p}" for k, p in got - want)
    out["n_cases"] = len(cases)
    out["candidates_without_value"] = sum(1 for c in report.get("static_candidates") or []
                                          if c.get("kind") == "api" and not value(c).startswith("/"))
    return out


if __name__ == "__main__":
    rep = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps(evaluate(rep, json.loads(EXPECTED.read_text(encoding="utf-8"))), ensure_ascii=False, indent=1))
