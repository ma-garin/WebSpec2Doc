"""実測フォーム制約から具体的なテストデータを生成する。"""

from __future__ import annotations

import csv
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ACCEPT = "accept_candidate"
REJECT = "reject_candidate"
MEASURED_ATTRIBUTE = "measured_attribute"
MAX_GENERATED_TEXT_LENGTH = 10_000
NON_FILLABLE_FIELD_TYPES = {
    "button",
    "checkbox",
    "file",
    "hidden",
    "image",
    "radio",
    "reset",
    "submit",
}
TEST_DATA_FIELDS = (
    "case_id",
    "requirement_ids",
    "page_id",
    "page_url",
    "field_name",
    "field_type",
    "locator",
    "category",
    "value",
    "expected_client_behavior",
    "source_constraint",
    "evidence",
)


def generate_test_data(
    report: dict[str, Any], requirement_ids_by_page: dict[str, list[str]] | None = None
) -> list[dict[str, Any]]:
    """report.jsonの実測属性だけを根拠に、決定的な入力値を返す。"""
    cases: list[dict[str, Any]] = []
    requirements = requirement_ids_by_page or {}
    for screen in _dict_items(report.get("screens", [])):
        page_id = str(screen.get("page_id", ""))
        page_url = str(screen.get("url", ""))
        for form in _dict_items(screen.get("forms", [])):
            for field in _dict_items(form.get("fields", [])):
                field_cases = _field_cases(page_id, page_url, field)
                requirement_ids = ", ".join(requirements.get(page_id, []))
                for case in field_cases:
                    case["requirement_ids"] = requirement_ids
                cases.extend(field_cases)
    for index, case in enumerate(cases, 1):
        case["case_id"] = f"TD-{index:04d}"
    return cases


def save_test_data(cases: list[dict[str, Any]], output_dir: Path) -> dict[str, Path]:
    """根拠付きテストデータをJSON/CSVへ保存する。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "test_data.json"
    csv_path = output_dir / "test_data.csv"
    json_path.write_text(
        json.dumps(
            {
                "meta": {
                    "case_count": len(cases),
                    "claim_scope": "generated_from_measured_constraints_review_required",
                },
                "cases": cases,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TEST_DATA_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for case in cases:
            writer.writerow({key: _safe_csv_value(value) for key, value in case.items()})
    return {"test_data_json": json_path, "test_data_csv": csv_path}


def _dict_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _field_cases(page_id: str, page_url: str, field: dict[str, Any]) -> list[dict[str, Any]]:
    field_name = str(field.get("name", ""))
    if not field_name:
        return []
    locator = _first_locator(field.get("locators", []))
    field_type = str(field.get("field_type", "text"))
    if field_type in NON_FILLABLE_FIELD_TYPES:
        return []
    pattern_blocks_synthetic_text = bool(field.get("pattern")) and field_type not in {
        "number",
        "range",
    }
    cases: list[dict[str, Any]] = []
    if field.get("required") is True:
        cases.append(
            _case(
                page_id,
                page_url,
                field_name,
                field_type,
                locator,
                "required",
                "",
                REJECT,
                "required=true",
            )
        )
    options = _string_items(field.get("options", []))
    if options:
        for value in dict.fromkeys((options[0], options[-1])):
            cases.append(
                _case(
                    page_id,
                    page_url,
                    field_name,
                    field_type,
                    locator,
                    "option",
                    value,
                    ACCEPT,
                    "options",
                )
            )
    elif not pattern_blocks_synthetic_text:
        normal_value = _normal_value(field_type)
        if normal_value is None:
            return _apply_measured_constraints(cases, field)
        cases.append(
            _case(
                page_id,
                page_url,
                field_name,
                field_type,
                locator,
                "equivalence",
                normal_value,
                ACCEPT,
                f"type={field_type}",
            )
        )
    if field_type == "email" and not options and not pattern_blocks_synthetic_text:
        cases.append(
            _case(
                page_id,
                page_url,
                field_name,
                field_type,
                locator,
                "format",
                "invalid-email",
                REJECT,
                "type=email",
            )
        )
    if field_type == "number":
        for attr, outside_delta in (("min_value", Decimal("-1")), ("max_value", Decimal("1"))):
            boundary = _decimal(field.get(attr))
            if boundary is None:
                continue
            values = (
                (boundary - 1, REJECT if outside_delta < 0 else ACCEPT),
                (boundary, ACCEPT),
                (boundary + 1, REJECT if outside_delta > 0 else ACCEPT),
            )
            for numeric_value, expected in values:
                cases.append(
                    _case(
                        page_id,
                        page_url,
                        field_name,
                        field_type,
                        locator,
                        "boundary",
                        _format_decimal(numeric_value),
                        expected,
                        f"{attr}={_format_decimal(boundary)}",
                    )
                )
    minlength = _positive_int(field.get("minlength"))
    if (
        minlength is not None
        and minlength < MAX_GENERATED_TEXT_LENGTH
        and not pattern_blocks_synthetic_text
    ):
        for length, expected in (
            (max(0, minlength - 1), REJECT),
            (minlength, ACCEPT),
            (minlength + 1, ACCEPT),
        ):
            cases.append(
                _case(
                    page_id,
                    page_url,
                    field_name,
                    field_type,
                    locator,
                    "boundary",
                    "あ" * length,
                    expected,
                    f"minlength={minlength}",
                )
            )
    maxlength = _positive_int(field.get("maxlength"))
    if (
        maxlength is not None
        and maxlength < MAX_GENERATED_TEXT_LENGTH
        and not pattern_blocks_synthetic_text
    ):
        for length, expected in (
            (max(0, maxlength - 1), ACCEPT),
            (maxlength, ACCEPT),
            (maxlength + 1, REJECT),
        ):
            cases.append(
                _case(
                    page_id,
                    page_url,
                    field_name,
                    field_type,
                    locator,
                    "boundary",
                    "あ" * length,
                    expected,
                    f"maxlength={maxlength}",
                )
            )
    return _apply_measured_constraints(cases, field)


def _apply_measured_constraints(
    cases: list[dict[str, Any]], field: dict[str, Any]
) -> list[dict[str, Any]]:
    """各候補を全実測制約で再評価し、複合制約による期待値矛盾を防ぐ。"""
    for case in cases:
        case["expected_client_behavior"] = _expected_behavior(field, str(case.get("value", "")))
    return cases


def _expected_behavior(field: dict[str, Any], value: str) -> str:
    if field.get("required") is True and value == "":
        return REJECT
    options = _string_items(field.get("options", []))
    if options and value not in options:
        return REJECT
    field_type = str(field.get("field_type", "text"))
    if value and field_type in {"number", "range"}:
        numeric = _decimal(value)
        if numeric is None:
            return REJECT
        minimum, maximum = _decimal(field.get("min_value")), _decimal(field.get("max_value"))
        if minimum is not None and numeric < minimum:
            return REJECT
        if maximum is not None and numeric > maximum:
            return REJECT
    if value and field_type == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+", value):
        return REJECT
    minlength, maxlength = _positive_int(field.get("minlength")), _positive_int(
        field.get("maxlength")
    )
    if minlength is not None and len(value) < minlength:
        return REJECT
    if maxlength is not None and len(value) > maxlength:
        return REJECT
    return ACCEPT


def _case(
    page_id: str,
    page_url: str,
    field_name: str,
    field_type: str,
    locator: str,
    category: str,
    value: str,
    expected: str,
    source_constraint: str,
) -> dict[str, Any]:
    return {
        "case_id": "",
        "page_id": page_id,
        "page_url": page_url,
        "field_name": field_name,
        "field_type": field_type,
        "locator": locator,
        "category": category,
        "value": value,
        "expected_client_behavior": expected,
        "source_constraint": source_constraint,
        "evidence": MEASURED_ATTRIBUTE,
    }


def _first_locator(value: object) -> str:
    if not isinstance(value, list):
        return ""
    return next((str(item) for item in value if isinstance(item, str) and item), "")


def _string_items(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _normal_value(field_type: str) -> str | None:
    values = {
        "color": "#336699",
        "date": "2026-01-01",
        "datetime-local": "2026-01-01T12:00",
        "email": "user@example.com",
        "month": "2026-01",
        "number": "1",
        "password": "Aa1!test",
        "range": "1",
        "search": "あ",
        "tel": "09012345678",
        "text": "あ",
        "textarea": "あ",
        "time": "12:00",
        "url": "https://example.com",
        "week": "2026-W01",
    }
    return values.get(field_type)


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdigit():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


def _decimal(value: object) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = Decimal(str(value))
        return parsed if parsed.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _format_decimal(value: Decimal) -> str:
    return format(value, "f").rstrip("0").rstrip(".") if value % 1 else str(int(value))


def _safe_csv_value(value: object) -> object:
    """表計算ソフトで式・制御文字として解釈される外部値を無効化する。"""
    if not isinstance(value, str) or not value:
        return value
    if value[0] in {"=", "+", "-", "@", "\t", "\r"}:
        if value[0] in {"+", "-"} and _decimal(value) is not None:
            return value
        return f"'{value}"
    return value
