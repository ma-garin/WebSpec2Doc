"""テスト技法の実適用 — 観測した入力項目から、技法に基づく具体的なテスト値を導出する。

これまでの段階11（テスト基本設計）は技法の**名前を割り当てるだけ**で、
「同値分割」と書かれていても実際の同値クラスは1つも作られていなかった。
利用者の仕様は「テスト用のモデリング、デシジョンなどのテスト技法の
**確実かつ完璧な提示**」であり、名前の割り当てでは要件を満たさない。

本モジュールは、クローラが実測した項目（型・必須・min/max・選択肢・パターン）から
JSTQB の標準技法を**実際に適用**し、具体的な値と期待結果を導出する。

対象へのアクセスは発生しない（観測済みデータのみを使う純関数）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TECHNIQUE_EQUIVALENCE = "同値分割"
TECHNIQUE_BOUNDARY = "境界値分析"
TECHNIQUE_DECISION_TABLE = "デシジョンテーブル"
TECHNIQUE_STATE_TRANSITION = "状態遷移テスト"
TECHNIQUE_PAIRWISE = "ペアワイズ"


@dataclass(frozen=True)
class TestValue:
    """技法から導出した1つの具体値と、その扱い。"""

    value: str
    label: str
    #: True なら受理されるべき値、False なら拒否されるべき値
    valid: bool
    technique: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "label": self.label,
            "valid": self.valid,
            "technique": self.technique,
            "rationale": self.rationale,
            "expected": "受理される" if self.valid else "拒否され、理由が示される",
        }


# ─────────────────── 同値分割 ───────────────────


def equivalence_classes(field: dict[str, Any]) -> tuple[TestValue, ...]:
    """項目の型・制約から同値クラスの代表値を導出する。"""
    field_type = str(field.get("field_type", "text"))
    required = bool(field.get("required"))
    values: list[TestValue] = []

    if required:
        values.append(
            TestValue(
                value="",
                label="未入力",
                valid=False,
                technique=TECHNIQUE_EQUIVALENCE,
                rationale="必須項目のため、未入力は無効同値クラス",
            )
        )

    if field_type == "email":
        values += [
            _v("user@example.com", "正しい形式", True, TECHNIQUE_EQUIVALENCE, "有効同値クラス"),
            _v("userexample.com", "@なし", False, TECHNIQUE_EQUIVALENCE, "無効同値クラス（形式違反）"),
            _v("user@", "ドメインなし", False, TECHNIQUE_EQUIVALENCE, "無効同値クラス（形式違反）"),
        ]
    elif field_type == "tel":
        values += [
            _v("0312345678", "妥当な桁数", True, TECHNIQUE_EQUIVALENCE, "有効同値クラス"),
            _v("03", "桁数不足", False, TECHNIQUE_EQUIVALENCE, "無効同値クラス"),
            _v("03-abc-defg", "記号・英字混在", False, TECHNIQUE_EQUIVALENCE, "無効同値クラス"),
        ]
    elif field_type == "number":
        values += _number_equivalence(field)
    elif field_type == "select":
        options = [str(o) for o in (field.get("options") or [])]
        for option in options:
            values.append(
                _v(option, f"選択肢「{option}」", True, TECHNIQUE_EQUIVALENCE, "各選択肢は個別の同値クラス")
            )
    elif field_type in ("checkbox", "radio"):
        values += [
            _v("on", "選択あり", True, TECHNIQUE_EQUIVALENCE, "2値の同値クラス"),
            _v("off", "選択なし", True, TECHNIQUE_EQUIVALENCE, "2値の同値クラス"),
        ]
    else:
        values += [
            _v("通常の入力値", "通常値", True, TECHNIQUE_EQUIVALENCE, "有効同値クラス"),
            _v("<script>alert(1)</script>", "特殊文字", False, TECHNIQUE_EQUIVALENCE,
               "無効同値クラス（エスケープ・拒否のいずれかが必要）"),
        ]
    return tuple(values)


def _number_equivalence(field: dict[str, Any]) -> list[TestValue]:
    low, high = _range_of(field)
    if low is None and high is None:
        return [_v("1", "通常値", True, TECHNIQUE_EQUIVALENCE, "有効同値クラス")]
    values = []
    if low is not None and high is not None:
        mid = (low + high) // 2
        values.append(_v(str(mid), "範囲内", True, TECHNIQUE_EQUIVALENCE, f"有効同値クラス（{low}〜{high}）"))
    if low is not None:
        values.append(_v(str(low - 1), "下限未満", False, TECHNIQUE_EQUIVALENCE, "無効同値クラス"))
    if high is not None:
        values.append(_v(str(high + 1), "上限超過", False, TECHNIQUE_EQUIVALENCE, "無効同値クラス"))
    return values


# ─────────────────── 境界値分析 ───────────────────


def boundary_values(field: dict[str, Any]) -> tuple[TestValue, ...]:
    """min/max・maxlength から境界値（境界とその前後）を導出する。

    JSTQB の 3値境界（境界の直前・境界・直後）を採る。
    """
    values: list[TestValue] = []
    low, high = _range_of(field)
    if low is not None:
        values += [
            _v(str(low - 1), f"下限-1（{low - 1}）", False, TECHNIQUE_BOUNDARY, "下限の直前は無効"),
            _v(str(low), f"下限（{low}）", True, TECHNIQUE_BOUNDARY, "下限そのものは有効"),
            _v(str(low + 1), f"下限+1（{low + 1}）", True, TECHNIQUE_BOUNDARY, "下限の直後は有効"),
        ]
    if high is not None:
        values += [
            _v(str(high - 1), f"上限-1（{high - 1}）", True, TECHNIQUE_BOUNDARY, "上限の直前は有効"),
            _v(str(high), f"上限（{high}）", True, TECHNIQUE_BOUNDARY, "上限そのものは有効"),
            _v(str(high + 1), f"上限+1（{high + 1}）", False, TECHNIQUE_BOUNDARY, "上限の直後は無効"),
        ]

    maxlength = _int_or_none(field.get("maxlength"))
    if maxlength:
        values += [
            _v("x" * (maxlength - 1), f"最大長-1（{maxlength - 1}文字）", True,
               TECHNIQUE_BOUNDARY, "最大長の直前は有効"),
            _v("x" * maxlength, f"最大長（{maxlength}文字）", True,
               TECHNIQUE_BOUNDARY, "最大長そのものは有効"),
            _v("x" * (maxlength + 1), f"最大長+1（{maxlength + 1}文字）", False,
               TECHNIQUE_BOUNDARY, "最大長の直後は無効"),
        ]
    return tuple(values)


# ─────────────────── デシジョンテーブル ───────────────────


def decision_table(fields: list[dict[str, Any]]) -> dict[str, Any]:
    """必須項目の入力有無の組合せからデシジョンテーブルを作る。

    必須項目が n 個あるとき、「全て入力」と「1つずつ欠落」の n+1 規則で
    十分な判定被覆が得られる（全組合せ 2^n は爆発するため採らない）。
    """
    required = [f for f in fields if f.get("required")]
    if not required:
        return {"applicable": False, "reason": "必須項目が無いため、判定条件が構成されません。"}

    names = [str(f.get("name", "")) for f in required]
    rules: list[dict[str, Any]] = [
        {
            "rule": "R1",
            "conditions": {name: "入力あり" for name in names},
            "action": "送信が受理される",
            "expected_valid": True,
        }
    ]
    for index, missing in enumerate(names, start=2):
        rules.append(
            {
                "rule": f"R{index}",
                "conditions": {
                    name: ("未入力" if name == missing else "入力あり") for name in names
                },
                "action": f"「{missing}」の必須エラーが表示され、送信されない",
                "expected_valid": False,
            }
        )
    return {
        "applicable": True,
        "technique": TECHNIQUE_DECISION_TABLE,
        "conditions": names,
        "rules": rules,
        "coverage": "各必須項目の欠落を個別に検証する規則被覆（全組合せではない）",
    }


# ─────────────────── 状態遷移テスト ───────────────────


def state_transitions(screens: list[dict[str, Any]]) -> dict[str, Any]:
    """観測した画面遷移から 0-switch（各遷移を1回通る）の被覆を導出する。"""
    edges: list[dict[str, str]] = []
    for screen in screens:
        source = str(screen.get("page_id", ""))
        transitions = screen.get("transitions")
        if not isinstance(transitions, dict):
            continue
        for target in transitions.get("to") or []:
            edges.append({"from": source, "to": str(target)})
    if not edges:
        return {"applicable": False, "reason": "画面遷移が観測されていません。"}
    return {
        "applicable": True,
        "technique": TECHNIQUE_STATE_TRANSITION,
        "transitions": edges,
        "coverage": f"0-switch被覆: {len(edges)} 遷移をすべて1回以上通る",
    }


# ─────────────────── ペアワイズ ───────────────────


def pairwise_pairs(fields: list[dict[str, Any]]) -> dict[str, Any]:
    """選択式項目のペアワイズ（2因子間網羅）の組合せを導出する。

    全組合せは爆発するため、任意の2項目間で全ての値の組が
    少なくとも1回現れることを保証する。
    """
    factors = [
        (str(f.get("name", "")), _factor_levels(f))
        for f in fields
        if _factor_levels(f)
    ]
    if len(factors) < 2:
        return {"applicable": False, "reason": "組合せ対象の選択式項目が2つ未満です。"}

    pairs: list[dict[str, Any]] = []
    for i in range(len(factors)):
        for j in range(i + 1, len(factors)):
            name_a, levels_a = factors[i]
            name_b, levels_b = factors[j]
            for a in levels_a:
                for b in levels_b:
                    pairs.append({name_a: a, name_b: b})
    return {
        "applicable": True,
        "technique": TECHNIQUE_PAIRWISE,
        "factors": {name: levels for name, levels in factors},
        "required_pairs": len(pairs),
        "coverage": "2因子間網羅（全組合せではない）",
        "sample_pairs": pairs[:20],
    }


def _factor_levels(field: dict[str, Any]) -> list[str]:
    field_type = str(field.get("field_type", ""))
    if field_type == "select":
        return [str(o) for o in (field.get("options") or [])][:6]
    if field_type in ("checkbox", "radio"):
        return ["on", "off"]
    return []


# ─────────────────── 統合 ───────────────────


def apply_all(screen: dict[str, Any]) -> dict[str, Any]:
    """1画面に対して適用可能な技法をすべて実行し、具体的な設計を返す。"""
    fields = [
        f
        for form in (screen.get("forms") or [])
        for f in (form.get("fields") or [])
        if isinstance(f, dict) and f.get("field_type") != "hidden"
    ]
    per_field = []
    for field in fields:
        eq = equivalence_classes(field)
        bv = boundary_values(field)
        if not eq and not bv:
            continue
        per_field.append(
            {
                "field": str(field.get("name", "")),
                "field_type": str(field.get("field_type", "")),
                "equivalence": [v.to_dict() for v in eq],
                "boundary": [v.to_dict() for v in bv],
                "case_count": len(eq) + len(bv),
            }
        )
    return {
        "page_id": str(screen.get("page_id", "")),
        "fields": per_field,
        "decision_table": decision_table(fields),
        "pairwise": pairwise_pairs(fields),
        "total_cases": sum(f["case_count"] for f in per_field),
    }


# ─────────────────── 補助 ───────────────────


def _v(value: str, label: str, valid: bool, technique: str, rationale: str) -> TestValue:
    return TestValue(value=value, label=label, valid=valid, technique=technique, rationale=rationale)


def _range_of(field: dict[str, Any]) -> tuple[int | None, int | None]:
    return _int_or_none(field.get("min_value")), _int_or_none(field.get("max_value"))


def _int_or_none(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
