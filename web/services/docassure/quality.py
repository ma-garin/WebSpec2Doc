"""品質スコア。指摘 0 件を 100 点にしない。評価対象 0 件・coverage<0.5 は value=None。"""
from __future__ import annotations

from typing import Any

from . import boundary, completeness, testability
from .model import Score
from .testability import to_dict, unit_view

DIMENSIONS = ("Clarity", "Completeness", "Consistency", "Atomicity", "Testability", "Traceability",
              "Measurability", "ExceptionCompleteness", "BoundaryCompleteness", "StateCompleteness")
DEFAULT_WEIGHTS = {"Testability": 3.0, "Consistency": 3.0, "Completeness": 1.5, "Clarity": 1.5}  # 他は 1.0
MIN_COVERAGE = 0.5
PENALTY = {"critical": 40, "high": 25, "medium": 12, "low": 5, "info": 0}
VERDICT_SCORE = {"CAN_TEST": 100, "PARTIALLY_TESTABLE": 50, "NOT_TESTABLE": 0}
# rule_id の語 -> 次元
RULE_DIM = (("TESTAB", "Testability"), ("AMBIG", "Clarity"), ("VAGUE", "Clarity"), ("CLARITY", "Clarity"),
            ("CONFLICT", "Consistency"), ("CONSIST", "Consistency"), ("CONTRA", "Consistency"),
            ("ATOMIC", "Atomicity"), ("COMPOUND", "Atomicity"), ("TRACE", "Traceability"),
            ("MEASUR", "Measurability"), ("QUANT", "Measurability"), ("EXCEPT", "ExceptionCompleteness"),
            ("BOUND", "BoundaryCompleteness"), ("STATE", "StateCompleteness"), ("COMPLET", "Completeness"))
_COMPOUND = ("かつ", "および", "及び", "ならびに", "さらに", "また、")
_STATE_WORDS = ("状態", "ステータス", "遷移", "未処理", "処理中", "完了", "承認待ち")
_BOUND_WORDS = ("文字", "件", "桁", "範囲", "以上", "以下", "最大", "最小", "未満", "上限", "下限", "サイズ", "長さ")


# 既定 rule pack（rules/packs/default.json）の rule_id の接頭辞 → 次元。先頭一致で誤対応を避ける
PACK_DIM = (("AMB-", "Clarity"), ("TBD-", "Completeness"), ("PLH-", "Completeness"), ("REQ-ITEMS", "Completeness"),
            ("REF-", "Traceability"), ("ID-", "Traceability"), ("TERM-", "Consistency"),
            ("NUM-001", "Measurability"), ("NUM-002", "BoundaryCompleteness"))


def _dim_of(rule_id: str) -> str | None:
    r = (rule_id or "").upper()
    hit = next((d for k, d in PACK_DIM if r.startswith(k)), None)
    if hit:
        return hit
    return next((d for k, d in RULE_DIM if k in r), None)


def _fv(f: Any) -> dict:
    return to_dict(f)


def _intrinsic(dim: str, v: dict, units_all: list[dict]) -> tuple[float | None, str]:
    """要件 1 件の固有判定。評価不能は (None, '')。"""
    text, rid = v["text"], v["requirement_id"]
    if not text.strip():
        return None, ""
    if dim == "Testability":
        verdict = testability.assess(v["_src"])["verdict"]
        return (VERDICT_SCORE[verdict], f"{rid}: {verdict}") if verdict in VERDICT_SCORE else (None, "")
    if dim == "Measurability":
        if testability.RE_THRESHOLD.search(text):
            return 100, ""
        w = [x for x in testability.VAGUE_WORDS if x in text]
        return (0, f"{rid}: 「{w[0]}」に数値基準がない") if w else (None, "")
    if dim == "Atomicity":
        n = sum(text.count(c) for c in _COMPOUND)
        return (0, f"{rid}: 複合要件（接続語 {n} 個）") if n >= 2 and not v.get("split") else (100, "")
    if dim == "ExceptionCompleteness":
        if v["kind"] != "functional":
            return None, ""
        ok = bool(v["fields"].get("exception") or testability.RE_FAILURE.search(text))
        return (100, "") if ok else (0, f"{rid}: 例外・失敗時の記述なし")
    if dim == "BoundaryCompleteness":
        if not any(w in text for w in _BOUND_WORDS):
            return None, ""
        gap = boundary.derive(v["_src"]).get("gap")
        return (0, f"{rid}: 境界値を決める数値がない") if gap else (100, "")
    if dim == "StateCompleteness":
        if not (v["fields"].get("state") or any(w in text for w in _STATE_WORDS)):
            return None, ""
        return (100, "") if v["fields"].get("state") else (50, f"{rid}: 状態の明示項目なし")
    if dim == "Completeness":
        cands = completeness.check([v["_src"]])
        types = {c["type"] for c in cands}
        if not any(t in text for tpl in completeness.TEMPLATES.values() for t in tpl["triggers"]):
            return None, ""
        total = sum(len(t["items"]) for n, t in completeness.TEMPLATES.items()
                    if any(x in text for x in t["triggers"]))
        return (round(100 * (1 - len(cands) / max(total, 1)), 1),
                f"{rid}: 網羅候補 {len(cands)} 件（{', '.join(sorted(types))}）") if cands or total else (None, "")
    return None, ""


def _score_dim(dim: str, views: list[dict], fmap: dict[str, list[dict]], allowed: bool) -> Score:
    if not views or not allowed:
        return Score(dim, None, 0.0, (), (), tuple(v["requirement_id"] for v in views))
    per: dict[str, float] = {}
    deductions: list[tuple[float, str]] = []
    for v in views:
        rid = v["requirement_id"]
        vals = []
        score, note = _intrinsic(dim, v, views)
        if score is not None:
            vals.append(score)
            if score < 100 and note:
                deductions.append((100 - score, note))
        ran = False
        pen = 0
        for f in fmap.get(rid, []):
            if f.get("result") == "NOT_EVALUATED":
                continue
            ran = True
            if f.get("result") == "FAIL":
                p = PENALTY.get(f.get("severity"), 0)
                pen += p
                deductions.append((p, f"{rid}: {f.get('title') or f.get('rule_id')}（{f.get('severity')}）"))
        if ran:
            vals.append(max(0, 100 - pen))
        if vals:
            per[rid] = min(vals)
    cov = len(per) / len(views)
    inc, ne = tuple(per), tuple(v["requirement_id"] for v in views if v["requirement_id"] not in per)
    expl = tuple(d[1] for d in sorted(deductions, key=lambda x: -x[0])[:3])
    if not per or cov < MIN_COVERAGE:
        return Score(dim, None, round(cov, 3), expl, inc, ne)
    return Score(dim, round(sum(per.values()) / len(per), 1), round(cov, 3), expl, inc, ne)


def score_document(units: list[Any], findings: list[Any], expected_dimensions=None,
                   weights: dict[str, float] | None = None) -> dict[str, Score]:
    views = []
    for u in units or []:
        v = unit_view(u)
        v["_src"] = u
        v["split"] = bool(to_dict(u).get("split"))
        views.append(v)
    fmap: dict[str, list[dict]] = {}
    fdim: dict[str, dict[str, list[dict]]] = {}
    for f in findings or []:
        d = _fv(f)
        dim = _dim_of(d.get("rule_id", ""))
        if dim:
            fdim.setdefault(dim, {}).setdefault(d.get("requirement_id", ""), []).append(d)
    expected = set(expected_dimensions) if expected_dimensions is not None else set(DIMENSIONS)
    out: dict[str, Score] = {}
    for dim in DIMENSIONS:
        out[dim] = _score_dim(dim, views, fdim.get(dim, {}), dim in expected)
    w = {**{d: 1.0 for d in DIMENSIONS}, **DEFAULT_WEIGHTS, **(weights or {})}
    total_w = sum(w[d] for d in DIMENSIONS)
    ev = [d for d in DIMENSIONS if out[d].value is not None]
    cov_w = sum(w[d] for d in ev) / total_w if total_w else 0.0
    if not ev or cov_w < MIN_COVERAGE:
        value = None
    else:
        value = round(sum(out[d].value * w[d] for d in ev) / sum(w[d] for d in ev), 1)
    worst = sorted(ev, key=lambda d: out[d].value)[:3]
    out["Overall"] = Score("Overall", value, round(cov_w, 3),
                           tuple(f"{d}={out[d].value}" for d in worst),
                           tuple(ev), tuple(d for d in DIMENSIONS if d not in ev))
    return out
