"""要件中の数値から同値クラスと境界値を導出する。数値で決められなければ TESTABILITY_GAP。"""
from __future__ import annotations

import re
from typing import Any

from .testability import unit_view

NUM = r"(\d+(?:\.\d+)?)"
RE_RANGE = re.compile(NUM + r"\s*(?:〜|~|-|から)\s*" + NUM)
RE_BOUND = re.compile(NUM + r"\s*(?:[A-Za-zぁ-んァ-ヶ一-龥%]{0,4})\s*(以上|以下|未満|超|以内|まで)")
RE_LABEL = re.compile(r"(最大|上限|最小|下限)\s*(?:は|で)?\s*" + NUM)
SPECIAL = ["null", "empty"]


def _n(s: str) -> float:
    f = float(s)
    return int(f) if f == int(f) and "." not in s else f


def _extract(text: str) -> dict:
    lo = hi = None  # (value, inclusive)
    spans = []
    m = RE_RANGE.search(text)
    if m:
        lo, hi = (_n(m.group(1)), True), (_n(m.group(2)), True)
        text = text[:m.start()] + " " * (m.end() - m.start()) + text[m.end():]
    for m in RE_BOUND.finditer(text):
        val, kind = _n(m.group(1)), m.group(2)
        if kind == "以上" and lo is None:
            lo = (val, True)
        elif kind == "超" and lo is None:
            lo = (val, False)
        elif kind in ("以下", "以内", "まで") and hi is None:
            hi = (val, True)
        elif kind == "未満" and hi is None:
            hi = (val, False)
    for m in RE_LABEL.finditer(text):
        val = _n(m.group(2))
        if m.group(1) in ("最大", "上限") and hi is None:
            hi = (val, True)
        elif m.group(1) in ("最小", "下限") and lo is None:
            lo = (val, True)
    return {"lo": lo, "hi": hi}


def derive(unit: Any) -> dict:
    v = unit_view(unit)
    rid = v["requirement_id"]
    b = _extract(v["text"])
    lo, hi = b["lo"], b["hi"]
    if lo is None and hi is None:
        return {"requirement_id": rid, "gap": "TESTABILITY_GAP",
                "reason": "数値の上限・下限が原文にないため境界値を決められない",
                "special": SPECIAL}
    isf = any(isinstance(x[0], float) for x in (lo, hi) if x)
    step = 0.01 if isf else 1
    values: list[dict] = []
    classes: list[dict] = []
    e_lo = e_hi = None
    if lo:
        e_lo = lo[0] if lo[1] else round(lo[0] + step, 2)
        values += [{"label": "min-1", "value": round(e_lo - step, 2), "valid": False},
                   {"label": "min", "value": e_lo, "valid": True},
                   {"label": "min+1", "value": round(e_lo + step, 2), "valid": True}]
        classes.append({"name": "invalid_below", "rule": f"< {e_lo}", "valid": False})
    if hi:
        e_hi = hi[0] if hi[1] else round(hi[0] - step, 2)
        values += [{"label": "max-1", "value": round(e_hi - step, 2), "valid": True},
                   {"label": "max", "value": e_hi, "valid": True},
                   {"label": "max+1", "value": round(e_hi + step, 2), "valid": False}]
    valid_rule = (f"{e_lo} <= x <= {e_hi}" if lo and hi else f"x >= {e_lo}" if lo else f"x <= {e_hi}")
    classes.insert(1 if lo else 0, {"name": "valid", "rule": valid_rule, "valid": True})
    if hi:
        classes.append({"name": "invalid_above", "rule": f"> {e_hi}", "valid": False})
    return {"requirement_id": rid, "gap": None,
            "ranges": {"min": e_lo, "max": e_hi,
                       "min_inclusive": lo[1] if lo else None, "max_inclusive": hi[1] if hi else None},
            "equivalence_classes": classes, "boundary_values": values, "special": SPECIAL}
