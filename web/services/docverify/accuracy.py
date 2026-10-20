"""System 06 R5: 精度ページの表示用データ（FR-06-170・172・173・174）。

scripts/docverify_eval.py が書いた quality/docverify_eval/result.json を読み、画面に出す形へ変える。
値の無いものは「未測定」と書き、推定値で埋めない。測定そのものはここでは行わない。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

RESULT_PATH = Path(__file__).resolve().parents[3] / "quality" / "docverify_eval" / "result.json"
# 規則の調整に使っていない、別の作成者による検証用セットの結果（scripts/commercial_eval/docverify_holdout_eval.py）。
# あれば規則ごとに最も低い値を採る（調整に使ったセットの値だけで有効・無効を決めない）。最後が改善に一度も使っていない最終評価用
_EVAL = Path(__file__).resolve().parents[3] / "quality" / "commercial_eval"
HOLDOUT_PATHS = (_EVAL / "docverify_holdout" / "result.json", _EVAL / "holdout_final" / "docverify" / "result.json")
MIN_PRECISION = 0.75  # 商用品質の基準。これ未満の規則は既定で無効
MIN_RECALL = 0.7  # これ未満の規則は有効のままにするが、見落としが多い限定的な検出と明示する
UNMEASURED = "未測定"

LABELS = {
    "AMBIGUOUS": "曖昧語",
    "REQ.INCOMPLETE": "未決定の記述",
    "REQ.OPEN_ENDED": "閉じていない列挙",
    "REQ.UNIVERSAL": "例外の無い表現",
    "REQ.AND_OR": "「および/または」",
    "REQ.MEASURABILITY": "数値の無い量・時間",
    "REQ.MULTIPLE_REQUIREMENTS": "1 文に複数の要求",
}
# 評価単位 → checks が出す rule ID（scripts/docverify_eval.py の RULES と同じ）
MEMBERS = {"AMBIGUOUS": ("RD.AMBIGUOUS", "REQ.AMBIGUOUS_TERM")}
# 精度を測る対象だが、まだ評価セットが無い検査（FR-06-172 の「未測定」）
NOT_YET = (
    ("SET.DUPLICATE", "重複候補（文書全体の検査）"),
    ("SET.CONFLICT", "矛盾候補（文書全体の検査）"),
)
METHOD_LABELS = (("injected", "欠陥を注入した文"), ("authored", "自作の文"), ("real", "実文書"))
MSG_NONE = "精度はまだ測定していません。測定すると規則ごとの値が表示されます。"
MSG_BROKEN = "精度の記録を読めませんでした。測定をやり直すと表示されます。"


def load(path: Path | None = None) -> dict | None:
    """result.json を読む。無ければ None、壊れていれば ValueError。"""
    p = Path(path or RESULT_PATH)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("docverify accuracy: %s を読めない: %s", p, e)
        raise ValueError(MSG_BROKEN) from e
    if not isinstance(data, dict) or not isinstance(data.get("rules"), dict):
        raise ValueError(MSG_BROKEN)
    if path is None:
        _apply_holdout(data)
    return data


def _apply_holdout(data: dict) -> None:
    """検証用セットの値があれば、規則ごとに適合率・再現率の最も低い値を採る（元の値は tuning_set に残す）。"""
    for path in HOLDOUT_PATHS:
        try:
            hold = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        except (OSError, json.JSONDecodeError):
            log.warning("docverify accuracy: 検証用セットの結果 %s を読めない", path)
            continue
        if not isinstance(hold, dict):
            continue
        for rid, r in data["rules"].items():
            h = (hold.get("rules") or {}).get(rid)
            if not isinstance(h, dict):
                continue
            r.setdefault("tuning_set", {"precision": r.get("precision"), "recall": r.get("recall"), "n": r.get("n")})
            r["holdout"] = {"precision": h.get("precision"), "recall": h.get("recall"), "n": hold.get("n")}
            for key in ("precision", "recall"):
                vals = [v for v in (r.get(key), h.get(key)) if v is not None]
                r[key] = min(vals) if vals else None


def fmt(v) -> str:
    return UNMEASURED if v is None else f"{v:.3f}"


def _status(r: dict) -> tuple[bool, str]:
    p = r.get("precision")
    if p is None:
        if r.get("n_predicted") == 0 and r.get("n"):
            return True, "検出が 0 件のため適合率を出せません（無効にする根拠がありません）。"
        return True, "適合率が未測定です。"
    if p < MIN_PRECISION:
        return False, f"適合率 {p:.3f} が基準 {MIN_PRECISION} 未満のため、既定で無効にしています。"
    rc = r.get("recall")
    if rc is not None and rc < MIN_RECALL:
        return True, (f"適合率は基準 {MIN_PRECISION} 以上ですが、再現率 {rc:.3f} が基準 {MIN_RECALL} 未満です。"
                      "見落としが多い限定的な検出のため、指摘が無くても問題が無いとは言えません。")
    return True, f"適合率が基準 {MIN_PRECISION} 以上です。"


def _cell(block: dict | None, rid: str) -> dict:
    r = ((block or {}).get("rules") or {}).get(rid)
    if not r:
        return {"precision": UNMEASURED, "recall": UNMEASURED, "n": UNMEASURED}
    return {"precision": fmt(r.get("precision")), "recall": fmt(r.get("recall")), "n": r.get("n"),
            "n_gold": r.get("n_gold"), "n_predicted": r.get("n_predicted")}


def _row(rid: str, r: dict, data: dict) -> dict:
    enabled, reason = _status(r)
    prev = ((data.get("previous") or {}).get("rules") or {}).get(rid) or {}
    delta = (data.get("delta") or {}).get(rid) or {}
    return {
        "rule": rid, "label": LABELS.get(rid, rid), "measured": True,
        "precision": fmt(r.get("precision")), "recall": fmt(r.get("recall")),
        "n": r.get("n"), "n_gold": r.get("n_gold"), "n_predicted": r.get("n_predicted"),
        "enabled_by_default": enabled, "reason": reason,
        "limited": enabled and r.get("recall") is not None and r.get("recall") < MIN_RECALL,
        "tuning_set": r.get("tuning_set"), "holdout": r.get("holdout"),
        "by_method": {m: _cell((data.get("by_method") or {}).get(m), rid) for m, _ in METHOD_LABELS},
        "previous": {"precision": fmt(prev.get("precision")), "recall": fmt(prev.get("recall"))},
        "delta": {"precision": fmt(delta.get("precision")), "recall": fmt(delta.get("recall"))},
    }


def _unmeasured_row(rid: str, label: str) -> dict:
    cell = {"precision": UNMEASURED, "recall": UNMEASURED, "n": UNMEASURED}
    return {"rule": rid, "label": label, "measured": False, "precision": UNMEASURED, "recall": UNMEASURED,
            "n": UNMEASURED, "n_gold": None, "n_predicted": None, "enabled_by_default": True,
            "reason": "評価セットが無く、まだ測っていません。",
            "by_method": {m: dict(cell) for m, _ in METHOD_LABELS},
            "previous": {"precision": UNMEASURED, "recall": UNMEASURED},
            "delta": {"precision": UNMEASURED, "recall": UNMEASURED}}


def page(path: Path | None = None) -> dict:
    """精度ページの表示データ。壊れた記録は ValueError（呼び出し側で利用者向けの文にする）。"""
    data = load(path)
    methods = [{"key": k, "label": v} for k, v in METHOD_LABELS]
    if data is None:
        rows = [_unmeasured_row(rid, label) for rid, label in LABELS.items()]
        rows += [_unmeasured_row(rid, label) for rid, label in NOT_YET]
        return {"measured": False, "message": MSG_NONE, "measured_on": UNMEASURED, "rules_version": UNMEASURED,
                "dataset": None, "kappa": UNMEASURED, "scope": "", "methods": methods, "rules": rows,
                "previous_measured_on": UNMEASURED, "limits": [], "min_precision": MIN_PRECISION}
    rows = [_row(rid, r, data) for rid, r in data["rules"].items()]
    known = {r["rule"] for r in rows}
    rows += [_unmeasured_row(rid, label) for rid, label in LABELS.items() if rid not in known]
    rows += [_unmeasured_row(rid, label) for rid, label in NOT_YET]
    ds = data.get("dataset") or {}
    kappa = (ds.get("annotation") or {}).get("kappa")
    return {"measured": True, "message": "", "measured_on": data.get("measured_on") or UNMEASURED,
            "rules_version": data.get("rules_version") or UNMEASURED,
            "dataset": {"name": ds.get("name"), "language": ds.get("language"), "n": ds.get("n"),
                        "license": ds.get("license"),
                        "annotators": (ds.get("annotation") or {}).get("annotators")},
            "kappa": fmt(kappa), "scope": data.get("scope") or "", "methods": methods, "rules": rows,
            "previous_measured_on": (data.get("previous") or {}).get("measured_on") or UNMEASURED,
            "limits": list(data.get("limits") or []), "min_precision": MIN_PRECISION}


def disabled_rules(path: Path | None = None) -> frozenset[str]:
    """既定で無効にする checks の rule ID。記録が無い・壊れているときは空（何も無効にしない）。"""
    try:
        data = load(path)
    except ValueError:
        return frozenset()
    if not data:
        return frozenset()
    out: set[str] = set()
    for rid, r in data["rules"].items():
        if not _status(r)[0]:
            out.update(MEMBERS.get(rid, (rid,)))
    return frozenset(out)
