from __future__ import annotations

import logging
from dataclasses import dataclass
from itertools import product

from crawler.page_crawler import FieldData, FormData, SourceEvidence
from ingest.models import DocumentEvidence

logger = logging.getLogger(__name__)

_FALLBACK = "正常値 / 空値 / 特殊文字"

SOURCE_RULES = "rules"
SOURCE_LLM = "llm"
SOURCE_DOCUMENT = "document"
# ルール由来のテスト条件は DOM 属性からの機械導出のため confidence は 1.0 固定
RULES_CONFIDENCE = 1.0


@dataclass(frozen=True)
class TestCondition:
    """根拠と確信度を持つテスト条件。"""

    __test__ = False  # pytest 収集対象外（テストクラスではなくドメインモデル）
    description: str
    source: str  # "rules" / "llm" / "document"
    confidence: float
    evidence: SourceEvidence | None
    observed_result: str = ""  # 期待結果（実測）: dry-run で観測されたメッセージ
    doc_evidence: DocumentEvidence | None = None  # 文書由来条件（source="document"）の根拠


_REQUIRED_CONDITION_KEYWORD = "必須チェック"


def derive_conditions_with_evidence(field: FieldData) -> tuple[TestCondition, ...]:
    """フィールド属性からテスト条件を導出し、フィールドの根拠情報を付与して返す。"""
    return tuple(
        TestCondition(
            description=description,
            source=SOURCE_RULES,
            confidence=RULES_CONFIDENCE,
            evidence=field.evidence,
        )
        for description in derive_conditions(field)
    )


def attach_observed_validation(
    conditions: tuple[TestCondition, ...],
    field: FieldData,
    observations: list,  # list[ValidationObservation]
) -> tuple[TestCondition, ...]:
    """必須チェック条件に、dry-run 実測のバリデーションメッセージを期待結果として転記する。

    実測値のため confidence=1.0・観測時の evidence を付与する。
    """
    from dataclasses import replace

    observation = next(
        (
            obs
            for obs in observations
            if getattr(obs, "field_name", "") and obs.field_name == field.name and obs.message
        ),
        None,
    )
    if observation is None:
        return conditions
    return tuple(
        (
            replace(
                condition,
                observed_result=observation.message,
                confidence=1.0,
                evidence=observation.evidence or condition.evidence,
            )
            if _REQUIRED_CONDITION_KEYWORD in condition.description
            else condition
        )
        for condition in conditions
    )


_MAX_PAIRWISE_FIELDS = 8
_MAX_PAIRWISE_CASES = 20
_MAX_REPRESENTATIVE_VALUES = 3

_CRITICALITY_KEYWORDS = (
    "決済",
    "支払",
    "payment",
    "クレジット",
    "個人情報",
    "プライバシー",
    "ログイン",
    "パスワード",
    "password",
)
_HIGH_CRITICALITY = 3.0
_NORMAL_CRITICALITY = 1.0
_MAX_RISK_SCORE = 100.0


def derive_conditions(field: FieldData) -> tuple[str, ...]:
    conditions: list[str] = []
    if field.required:
        conditions.append("未入力で送信（必須チェック）")
    conditions.extend(_length_conditions(field))
    conditions.extend(_type_conditions(field))
    if field.pattern:
        conditions.append("パターン適合 / 不適合")
    if field.options:
        conditions.append(f"選択肢{len(field.options)}件の各値 / 未選択")
    return tuple(conditions) if conditions else (_FALLBACK,)


def _length_conditions(field: FieldData) -> list[str]:
    result: list[str] = []
    if field.maxlength is not None:
        n = field.maxlength
        result.append(f"最大長: {n - 1}/{n}/{n + 1}文字")
    if field.minlength is not None:
        m = field.minlength
        result.append(f"最小長: {max(m - 1, 0)}/{m}文字")
    return result


def _type_conditions(field: FieldData) -> list[str]:
    ftype = field.field_type
    has_range = bool(field.min_value or field.max_value)
    if ftype == "email":
        return ["メール形式: 正常 / @なし / ドメインなし"]
    if ftype in ("number", "range"):
        if has_range:
            return [f"範囲 {field.min_value or '?'}〜{field.max_value or '?'}: 境界 / 範囲外"]
        return ["数値: 非数値 / 負値 / 0"]
    if ftype == "date":
        if has_range:
            return [f"日付範囲 {field.min_value or '?'}〜{field.max_value or '?'}: 境界 / 範囲外"]
        return ["日付: 不正日付 / 過去 / 未来"]
    if ftype == "tel":
        return ["電話番号: 正常 / 桁数違い / 記号混在"]
    if ftype == "password":
        return ["パスワード: 最小長 / 記号含む / 空"]
    if ftype == "checkbox":
        return ["ON / OFF"]
    return []


def _get_representative_values(field: FieldData) -> list[str]:
    """各フィールドの代表値（正常・境界・異常）を最大3件返す。"""
    if field.options:
        opts = list(field.options)
        abnormal = "" if field.required else "invalid"
        return [opts[0], opts[-1], abnormal][:_MAX_REPRESENTATIVE_VALUES]
    if field.field_type == "email":
        return ["user@example.com", "", "invalid-email"]
    if field.field_type == "number":
        return ["0", str(field.min_value or "1"), "abc"]
    if field.maxlength is not None:
        n = field.maxlength
        # n-1 は境界未満、n は境界ちょうど、n+1 は境界超え（truncateして文字列で表現）
        return [str(n - 1), str(n), str(n + 1)]
    return ["正常値", "", "<script>"]


def generate_pairwise_cases(fields: list[FieldData]) -> list[dict[str, str]]:
    """2-way カバレッジ（ペアワイズ）でテストケースセットを生成する。
    各フィールドの代表値（正常・境界・異常）を組み合わせ、
    全ての 2 フィールドの組み合わせをカバーする最小セットを返す。
    8 フィールド超は先頭 8 フィールドに縮退して爆発を防ぐ。"""
    if not fields:
        return []

    active = fields[:_MAX_PAIRWISE_FIELDS]
    rep_values = [_get_representative_values(f) for f in active]

    if len(active) <= 2:
        # 2フィールド以下は全組み合わせを直接返す
        combos = list(product(*rep_values))
        return [{active[i].name: combo[i] for i in range(len(active))} for combo in combos][
            :_MAX_PAIRWISE_CASES
        ]

    # 3フィールド以上: 最初のフィールドの各値を基準行として、
    # 残りフィールドをラウンドロビンで割り当てることで2-wayカバレッジを近似する
    cases: list[dict[str, str]] = []
    first_vals = rep_values[0]
    rest_fields = active[1:]
    rest_vals = rep_values[1:]

    max_rest_len = max(len(v) for v in rest_vals)
    for _fi, fval in enumerate(first_vals):
        for ri in range(max_rest_len):
            row: dict[str, str] = {active[0].name: fval}
            for _j, (rf, rv) in enumerate(zip(rest_fields, rest_vals, strict=False)):
                row[rf.name] = rv[ri % len(rv)]
            cases.append(row)
            if len(cases) >= _MAX_PAIRWISE_CASES:
                return cases

    return cases[:_MAX_PAIRWISE_CASES]


def generate_decision_table(
    fields: list[FieldData],
    transitions: list[str],
) -> list[dict[str, str | dict[str, str]]]:
    """条件（フィールド値の充足状態）× アクション（遷移先）のデシジョンテーブルを生成。
    transitions は遷移先 URL のリスト。"""
    if not fields or not transitions:
        return []

    def _condition_labels(f: FieldData) -> tuple[str, str]:
        return ("充足", "未充足") if f.required else ("入力", "未入力")

    field_states = [_condition_labels(f) for f in fields]

    if len(fields) <= 4:
        combos = list(product(*field_states))
    else:
        # 5フィールド以上はペアワイズで縮退（全組み合わせ爆発を防ぐ）
        pairwise_fields = [
            FieldData(
                field_type="text",
                name=f.name,
                placeholder="",
                required=f.required,
                options=tuple(_condition_labels(f)),
            )
            for f in fields
        ]
        pw_cases = generate_pairwise_cases(pairwise_fields)
        combos = [
            tuple(case.get(f.name, _condition_labels(f)[0]) for f in fields) for case in pw_cases
        ]

    rows: list[dict[str, str | dict[str, str]]] = []
    for i, combo in enumerate(combos):
        conditions = {fields[j].name: combo[j] for j in range(len(fields))}
        url = transitions[i % len(transitions)]
        rows.append({"conditions": conditions, "expected_transition": url})

    return rows


def compute_risk_score(
    forms: list[FormData],
    headings: tuple[str, ...],
    change_freq: float = 0.0,
) -> float:
    """フォーム複雑度・変更頻度・重要度でリスクスコアを算出。
    change_freq は 0.0〜1.0（過去スナップショット差分履歴から計算）。"""
    all_fields = [f for form in forms for f in form.fields]
    validation_count = sum(
        1 for f in all_fields if f.required or f.maxlength is not None or f.pattern or f.options
    )
    option_count = sum(len(f.options) for f in all_fields)
    complexity = len(all_fields) + validation_count + option_count

    lower_headings = " ".join(headings).lower()
    criticality = (
        _HIGH_CRITICALITY
        if any(kw.lower() in lower_headings for kw in _CRITICALITY_KEYWORDS)
        else _NORMAL_CRITICALITY
    )

    risk = complexity * (1 + change_freq) * criticality
    return min(risk, _MAX_RISK_SCORE)
