from __future__ import annotations

from crawler.page_crawler import FieldData

_FALLBACK = "正常値 / 空値 / 特殊文字"


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
