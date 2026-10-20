#!/usr/bin/env python3
"""F. Product Truth（状態の分類）の評価。

quality/commercial_eval/product_truth/cases.json の各ケースを、製品の実際の分類経路に通して照合する。
- runner_status: web.services.ta2_store._run_status（ランナーの生の結果 → 内部状態）
- evidence_category: 画面共通の語彙 WS2D.evidence.category（static/js/c-hybrid.js）
- test_status_label: テスト一覧の状態表示 TA2.panels.resultCell（static/js/ta2/panels.js）
画面側の 2 つは、起動中のサーバのテスト一覧画面をブラウザで開いて評価する。
使い方: venv/bin/python scripts/commercial_eval/product_truth_eval.py http://127.0.0.1:8766 /sites/<domain>/tests
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from web.services.ta2_store import _run_status  # noqa: E402

DATA = ROOT / "quality" / "commercial_eval" / "product_truth" / "cases.json"


def _browser_outputs(base: str, path: str, cases: list[dict]) -> dict[str, str]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(base + path, wait_until="networkidle")
        pg.wait_for_function("() => window.TA2 && window.TA2.panels && window.TA2.panels.resultCell && window.WS2D")
        out = {}
        for c in cases:
            if c["kind"] == "evidence_category":
                out[c["id"]] = pg.evaluate("(v) => window.WS2D.evidence.category(v)", c["input"])
            elif c["kind"] == "test_status_label":
                html = pg.evaluate("(v) => window.TA2.panels.resultCell({status: v, last: {}})", c["input"])
                out[c["id"]] = pg.evaluate(
                    "(h) => { const d = document.createElement('div'); d.innerHTML = h;"
                    " const s = d.querySelector('.pill'); return s ? s.textContent.trim() : ''; }", html)
        b.close()
    return out


def evaluate(base: str, path: str) -> dict:
    cases = json.loads(DATA.read_text(encoding="utf-8"))["cases"]
    got = {c["id"]: _run_status(c["input"]) for c in cases if c["kind"] == "runner_status"}
    got.update(_browser_outputs(base, path, cases))
    by_kind: dict[str, Counter] = {}
    wrong, danger = [], []
    for c in cases:
        k = by_kind.setdefault(c["kind"], Counter())
        ok = got.get(c["id"]) == c["expected"]
        k.update({"n": 1, "correct": int(ok)})
        if not ok:
            wrong.append(f'{c["id"]} {c["kind"]} {c["input"]!r}: {got.get(c["id"])!r} (正解 {c["expected"]!r})')
        if got.get(c["id"]) in (c.get("danger_if") or []):
            danger.append(f'{c["id"]} {c["input"]!r} → {got.get(c["id"])!r}')
    n = sum(v["n"] for v in by_kind.values())
    correct = sum(v["correct"] for v in by_kind.values())
    return {"n": n, "accuracy": round(correct / n, 3),
            "by_kind": {k: round(v["correct"] / v["n"], 3) for k, v in by_kind.items()},
            "dangerous_false_promotion": danger, "wrong": wrong}


if __name__ == "__main__":
    print(json.dumps(evaluate(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=1))
