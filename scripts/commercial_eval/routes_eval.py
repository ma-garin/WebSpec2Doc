#!/usr/bin/env python3
"""B. route / API 抽出の評価。

製品の reverse_analysis.json（static_candidates）を quality/commercial_eval/routes/expected.json と照合する。
使い方: venv/bin/python scripts/commercial_eval/routes_eval.py <reverse_analysis.json> [<expected.json>]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from common import norm_path, prf  # noqa: E402

from reverse_analysis.normalize import expression_path_pattern  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = ROOT / "quality" / "commercial_eval" / "routes" / "expected.json"


def evaluate(report: dict, expected: dict) -> dict:
    # 静的に決まらないと正解側が判断したケース（exclude_from_metrics）は、検出・誤検出のどちらにも数えない
    cases = [c for c in expected["cases"] if not c.get("exclude_from_metrics")]
    want = {(c["kind"], norm_path(c["path"])) for c in cases if c["should_detect"]}
    trap = {(c["kind"], norm_path(c["path"])) for c in cases if not c["should_detect"]}
    # 画面（web/routes/reverse_analysis.py）と同じく、path が無ければ expression を候補の値として扱う
    def value(c: dict) -> str:
        return c.get("path") or c.get("path_pattern") or expression_path_pattern(c.get("expression")) or ""

    # 別オリジン（外部サービス）への呼び出しは、このサイトの API ではないので数えない（製品は origin を付けて区別する）
    cands = [c for c in report.get("static_candidates") or []
             if c.get("kind") in ("route", "api") and value(c).startswith("/") and not c.get("origin")]
    got = {(c.get("kind"), norm_path(value(c))) for c in cands}
    # route の情報源（REA）が route 宣言を出さなかった入力は、0 件ではなく取得不能として分母から外す
    route_unavailable = not any(c.get("kind") == "route" for c in report.get("static_candidates") or []) and any(
        d.get("code") == "provider_route_not_provided" for d in report.get("diagnostics") or [])
    out = {"route_unavailable": route_unavailable}
    for kind in ("route", "api", None):
        w = {x for x in want if kind is None or x[0] == kind}
        g = {x for x in got if kind is None or x[0] == kind}
        if route_unavailable and kind == "route":
            out["route"] = {"state": "UNAVAILABLE", "expected_routes": len(w)}
            continue
        if route_unavailable and kind is None:
            w = {x for x in w if x[0] != "route"}
        out[kind or "all"] = prf(len(w & g), len(g - w), len(w - g))
    # method: 正解に method がある API のうち、同じ path の候補が付けた method が一致した割合
    methods = {}
    for c in cands:
        if c.get("kind") == "api":
            methods.setdefault(norm_path(value(c)), set()).add((c.get("method") or "").upper())
    graded = [(c, methods.get(norm_path(c["path"]), set())) for c in cases
              if c["should_detect"] and c["kind"] == "api" and c.get("method") and norm_path(c["path"]) in methods]
    out["method"] = {"n": len(graded), "correct": sum(c["method"].upper() in m for c, m in graded),
                     "unknown": sum(m <= {"UNKNOWN", ""} for _, m in graded)}
    out["trap_hits"] = sorted(p for _, p in (got & trap))
    out["missed"] = sorted(f"{k}:{p}" for k, p in want - got)
    out["extra"] = sorted(f"{k}:{p}" for k, p in got - want)
    out["n_cases"] = len(cases)
    out["candidates_without_value"] = sum(1 for c in report.get("static_candidates") or []
                                          if c.get("kind") == "api" and not value(c).startswith("/"))
    return out


if __name__ == "__main__":
    rep = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    expected = Path(sys.argv[2]) if len(sys.argv) > 2 else EXPECTED
    print(json.dumps(evaluate(rep, json.loads(expected.read_text(encoding="utf-8"))), ensure_ascii=False, indent=1))
