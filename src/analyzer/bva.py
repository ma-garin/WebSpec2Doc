"""実測バリデーション属性からの境界値分析（BVA）テストケース導出。

日本の SIer 開発で標準的な「項目定義書」「境界値データ」成果物の
具体値部分を、DOM から実測した属性（maxlength・min/max・pattern・
required・options）のみから機械導出する。根拠のない値は出力しない
（evidence-only 原則）— pattern が既知の型に一致しない場合は
「例生成不能」と明示し、値をでっち上げない。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from crawler.page_crawler import FieldData, SourceEvidence, ValidationObservation

_UNPARSEABLE_NOTE = "（例生成不能・手動作成要）"


@dataclass(frozen=True)
class BoundaryCase:
    """実測バリデーション属性から導出した境界値テストケース。"""

    field_name: str
    kind: str  # "max_length" / "min_length" / "range_min" / "range_max" /
    # "pattern_valid" / "pattern_invalid" / "required_empty" / "option"
    value: str
    expected: str
    source_attribute: str
    generated: bool = True
    evidence: SourceEvidence | None = None
    confidence: float = 1.0


_SOURCE_ATTR = {
    "max_length": "maxlength",
    "min_length": "minlength",
    "range_min": "min_value",
    "range_max": "max_value",
    "pattern_valid": "pattern",
    "pattern_invalid": "pattern",
    "required_empty": "required",
    "option": "options",
}

KIND_LABELS = {
    "max_length": "最大長",
    "min_length": "最小長",
    "range_min": "範囲下限",
    "range_max": "範囲上限",
    "pattern_valid": "パターン適合",
    "pattern_invalid": "パターン不適合",
    "required_empty": "必須",
    "option": "選択肢",
}


def _case(
    field: FieldData, kind: str, value: str, expected: str, generated: bool = True
) -> BoundaryCase:
    return BoundaryCase(
        field_name=field.name,
        kind=kind,
        value=value,
        expected=expected,
        source_attribute=_SOURCE_ATTR[kind],
        generated=generated,
        evidence=field.evidence,
        confidence=field.confidence,
    )


def _max_length_cases(field: FieldData) -> list[BoundaryCase]:
    n = field.maxlength
    if n is None or n <= 0:
        return []
    return [
        _case(field, "max_length", "a" * (n - 1), "受理"),
        _case(field, "max_length", "a" * n, "受理"),
        _case(field, "max_length", "a" * (n + 1), "エラー（最大長超過）"),
    ]


def _min_length_cases(field: FieldData) -> list[BoundaryCase]:
    m = field.minlength
    if m is None or m <= 0:
        return []
    below = max(m - 1, 0)
    return [
        _case(field, "min_length", "a" * below, "エラー（最小長未満）"),
        _case(field, "min_length", "a" * m, "受理"),
    ]


def _range_cases(field: FieldData) -> list[BoundaryCase]:
    if field.field_type not in ("number", "range"):
        return []
    if not field.min_value or not field.max_value:
        return []
    try:
        lo = int(field.min_value)
        hi = int(field.max_value)
    except ValueError:
        return []
    return [
        _case(field, "range_min", str(lo - 1), "エラー（範囲未満）"),
        _case(field, "range_min", str(lo), "受理"),
        _case(field, "range_max", str(hi), "受理"),
        _case(field, "range_max", str(hi + 1), "エラー（範囲超過）"),
    ]


_FIXED_DIGITS_RE = re.compile(r"^\^?\[0-9\]\{(\d+)\}\$?$")
_DIGIT_RANGE_RE = re.compile(r"^\^?\[0-9\]\{(\d+),(\d+)\}\$?$")
_DIGIT_SPACE_RANGE_RE = re.compile(r"^\^?\[0-9 \]\{(\d+),(\d+)\}\$?$")
_MONTH_YEAR_RE = re.compile(r"^\^?\(0\[1-9\]\|1\[0-2\]\)/\[0-9\]\{2\}\$?$")


def _try_fixed_digits(pattern: str) -> tuple[str, str] | None:
    match = _FIXED_DIGITS_RE.match(pattern)
    if not match:
        return None
    n = int(match.group(1))
    if n <= 0:
        return None
    valid = "1" * n
    invalid = "1" * (n - 1) if n > 1 else "a"
    return valid, invalid


def _try_digit_range(pattern: str) -> tuple[str, str] | None:
    match = _DIGIT_RANGE_RE.match(pattern)
    if not match:
        return None
    lo = int(match.group(1))
    if lo <= 0:
        return None
    valid = "1" * lo
    invalid = "1" * (lo - 1) if lo > 1 else "a"
    return valid, invalid


def _try_digit_space_range(pattern: str) -> tuple[str, str] | None:
    match = _DIGIT_SPACE_RANGE_RE.match(pattern)
    if not match:
        return None
    lo = int(match.group(1))
    if lo <= 0:
        return None
    return "1" * lo, "a" * lo


def _try_month_year(pattern: str) -> tuple[str, str] | None:
    if not _MONTH_YEAR_RE.match(pattern):
        return None
    return "12/28", "13/28"


def _generate_pattern_examples(pattern: str) -> tuple[str, str] | None:
    """既知パターン辞書から適合例・不適合例を生成し、re.fullmatch で自己検証する。

    辞書に無い、または生成した値が自己検証を通らないパターンは None
    （呼び出し側が「例生成不能」として扱う）。
    """
    try:
        compiled = re.compile(pattern)
    except re.error:
        return None
    candidates = (
        _try_fixed_digits(pattern)
        or _try_digit_range(pattern)
        or _try_digit_space_range(pattern)
        or _try_month_year(pattern)
    )
    if candidates is None:
        return None
    valid, invalid = candidates
    if compiled.fullmatch(valid) is None or compiled.fullmatch(invalid) is not None:
        return None
    return valid, invalid


def _pattern_cases(field: FieldData) -> list[BoundaryCase]:
    if not field.pattern:
        return []
    examples = _generate_pattern_examples(field.pattern)
    if examples is None:
        return [_case(field, "pattern_valid", "", _UNPARSEABLE_NOTE, generated=False)]
    valid, invalid = examples
    return [
        _case(field, "pattern_valid", valid, "受理"),
        _case(field, "pattern_invalid", invalid, "エラー（形式不正）"),
    ]


def _required_cases(field: FieldData) -> list[BoundaryCase]:
    if not field.required:
        return []
    return [_case(field, "required_empty", "", "エラー（必須）")]


def _option_cases(field: FieldData) -> list[BoundaryCase]:
    if not field.options:
        return []
    opts = list(field.options)
    cases = [
        _case(field, "option", opts[0], "受理"),
        _case(field, "option", opts[-1], "受理"),
    ]
    if not field.required:
        cases.append(_case(field, "option", "", "受理"))
    return cases


def derive_boundary_cases(field: FieldData) -> tuple[BoundaryCase, ...]:
    """フィールドの実測属性から境界値ケースを導出する。

    required の実測メッセージ転記は attach_observed_boundary_cases で行う
    （dry-run 実測が無ければこの関数の出力のみで完結する）。
    """
    cases: list[BoundaryCase] = []
    cases.extend(_max_length_cases(field))
    cases.extend(_min_length_cases(field))
    cases.extend(_range_cases(field))
    cases.extend(_pattern_cases(field))
    cases.extend(_required_cases(field))
    cases.extend(_option_cases(field))
    return tuple(cases)


def attach_observed_boundary_cases(
    cases: tuple[BoundaryCase, ...],
    field: FieldData,
    observations: list[ValidationObservation],
) -> tuple[BoundaryCase, ...]:
    """required_empty ケースの期待結果を dry-run 実測メッセージへ置き換える。

    analyzer.test_conditions.attach_observed_validation と同じ前例に倣う。
    """
    observation = next(
        (
            obs
            for obs in observations
            if getattr(obs, "field_name", "") and obs.field_name == field.name and obs.message
        ),
        None,
    )
    if observation is None:
        return cases
    return tuple(
        (
            replace(
                case,
                expected=observation.message,
                confidence=1.0,
                evidence=observation.evidence or case.evidence,
            )
            if case.kind == "required_empty"
            else case
        )
        for case in cases
    )
