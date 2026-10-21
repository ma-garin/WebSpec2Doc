"""曖昧な要件の書き換え「提案」。原文は変更せず、原文にない値は作らない（プレースホルダ + INFERRED）。"""
from __future__ import annotations

from .testability import assess, unit_view

NOTE = "提案（未承認・原文は変更しない）"


def _slot(fields: dict, key: str, label: str) -> dict:
    if fields.get(key):
        return {"value": fields[key], "provenance": "OBSERVED"}
    return {"value": f"<要確認: {label}>", "provenance": "INFERRED"}


def propose(unit) -> dict:
    v = unit_view(unit)
    f, a = v["fields"], assess(unit)
    s = {"actor": _slot(f, "actor", "主体"), "condition": _slot(f, "condition", "条件"),
         "action": _slot(f, "action", "動作"), "expected": _slot(f, "expected_result", "期待結果")}
    if "閾値・単位" in a["missing"]:
        s["threshold"] = {"value": "<要確認: 閾値>", "provenance": "INFERRED"}
    if "失敗時の挙動" in a["missing"]:
        s["failure"] = {"value": "<要確認: 失敗時の挙動>", "provenance": "INFERRED"}
    g = f"{s['actor']['value']}が{s['condition']['value']}の状態である"
    t = s["expected"]["value"] + (f"（{s['threshold']['value']}）" if "threshold" in s else "")
    when = s["action"]["value"]
    return {"requirement_id": v["requirement_id"], "original": v["raw_text"],
            "proposal": {"given": g, "when": when, "then": t}, "structured": s,
            "status": "PROPOSAL", "note": NOTE, "provenance": "INFERRED",
            "fix_levels": {"minimal": "不足項目を確認して値を埋める: " + (" / ".join(a["missing"]) or "なし"),
                           "recommended": f"Given/When/Then に整形し、閾値と失敗時の挙動を明記する: {g} / {when} / {t}",
                           "strict": "推奨に加え、境界値・権限・状態遷移ごとに別要件へ分割し受入基準を付ける"}}
