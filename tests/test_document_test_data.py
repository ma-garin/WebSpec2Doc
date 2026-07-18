"""第3弾 S2: 実測制約から作るテストデータの公開契約。"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from mbt.test_data import generate_test_data, save_test_data


def test_required_maxlength_field_generates_concrete_rooted_values() -> None:
    report = {
        "screens": [
            {
                "page_id": "P001",
                "url": "https://example.com/contact",
                "forms": [
                    {
                        "fields": [
                            {
                                "name": "message",
                                "field_type": "textarea",
                                "required": True,
                                "maxlength": 3,
                                "locators": ["#message"],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    cases = generate_test_data(report)

    assert [(case["category"], case["value"]) for case in cases] == [
        ("required", ""),
        ("equivalence", "あ"),
        ("boundary", "ああ"),
        ("boundary", "あああ"),
        ("boundary", "ああああ"),
    ]
    assert [case["expected_client_behavior"] for case in cases] == [
        "reject_candidate",
        "accept_candidate",
        "accept_candidate",
        "accept_candidate",
        "reject_candidate",
    ]
    assert all(case["page_id"] == "P001" for case in cases)
    assert all(case["field_name"] == "message" for case in cases)
    assert all(case["locator"] == "#message" for case in cases)
    assert {case["evidence"] for case in cases} == {"measured_attribute"}
    assert {case["source_constraint"] for case in cases[2:]} == {"maxlength=3"}


def test_email_type_generates_valid_and_invalid_equivalence_classes() -> None:
    report = {
        "screens": [
            {
                "page_id": "P010",
                "url": "https://example.com/login",
                "forms": [
                    {
                        "fields": [
                            {
                                "name": "email",
                                "field_type": "email",
                                "required": False,
                                "locators": ["#email"],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    cases = generate_test_data(report)

    assert [(case["category"], case["value"]) for case in cases] == [
        ("equivalence", "user@example.com"),
        ("format", "invalid-email"),
    ]
    assert cases[1]["expected_client_behavior"] == "reject_candidate"
    assert cases[1]["source_constraint"] == "type=email"


def test_number_min_max_generate_inside_boundary_and_outside_values() -> None:
    report = {
        "screens": [
            {
                "page_id": "P020",
                "url": "https://example.com/order",
                "forms": [
                    {
                        "fields": [
                            {
                                "name": "quantity",
                                "field_type": "number",
                                "min_value": "1",
                                "max_value": "3",
                                "locators": ["#quantity"],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    cases = generate_test_data(report)

    boundaries = [
        (case["value"], case["expected_client_behavior"], case["source_constraint"])
        for case in cases
        if case["category"] == "boundary"
    ]
    assert boundaries == [
        ("0", "reject_candidate", "min_value=1"),
        ("1", "accept_candidate", "min_value=1"),
        ("2", "accept_candidate", "min_value=1"),
        ("2", "accept_candidate", "max_value=3"),
        ("3", "accept_candidate", "max_value=3"),
        ("4", "reject_candidate", "max_value=3"),
    ]


def test_select_uses_only_measured_options_and_does_not_invent_outside_value() -> None:
    report = {
        "screens": [
            {
                "page_id": "P030",
                "url": "https://example.com/profile",
                "forms": [
                    {
                        "fields": [
                            {
                                "name": "department",
                                "field_type": "select",
                                "options": ["営業", "開発", "管理"],
                                "locators": ["#department"],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    cases = generate_test_data(report)

    assert [(case["category"], case["value"]) for case in cases] == [
        ("option", "営業"),
        ("option", "管理"),
    ]
    assert {case["source_constraint"] for case in cases} == {"options"}


def test_minlength_generates_below_on_and_above_boundary_values() -> None:
    report = {
        "screens": [
            {
                "page_id": "P040",
                "url": "https://example.com/search",
                "forms": [
                    {
                        "fields": [
                            {
                                "name": "keyword",
                                "field_type": "text",
                                "minlength": "2",
                                "locators": ["#keyword"],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    cases = generate_test_data(report)

    boundaries = [
        (case["value"], case["expected_client_behavior"])
        for case in cases
        if case["source_constraint"] == "minlength=2"
    ]
    assert boundaries == [
        ("あ", "reject_candidate"),
        ("ああ", "accept_candidate"),
        ("あああ", "accept_candidate"),
    ]


def test_save_test_data_writes_machine_readable_json_and_csv(tmp_path: Path) -> None:
    cases = [
        {
            "case_id": "TD-0001",
            "page_id": "P001",
            "page_url": "https://example.com/",
            "field_name": "email",
            "field_type": "email",
            "locator": "#email",
            "category": "format",
            "value": "invalid-email",
            "expected_client_behavior": "reject_candidate",
            "source_constraint": "type=email",
            "evidence": "measured_attribute",
        }
    ]

    paths = save_test_data(cases, tmp_path)

    payload = json.loads(paths["test_data_json"].read_text(encoding="utf-8"))
    assert payload["meta"] == {
        "case_count": 1,
        "claim_scope": "generated_from_measured_constraints_review_required",
    }
    assert payload["cases"] == cases
    with paths["test_data_csv"].open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["case_id"] == "TD-0001"
    assert rows[0]["value"] == "invalid-email"


def test_cases_keep_requirement_trace_and_skip_unbounded_huge_strings() -> None:
    report = {
        "screens": [
            {
                "page_id": "P050",
                "url": "https://example.com/profile",
                "forms": [
                    {
                        "fields": [
                            {
                                "name": "bio",
                                "field_type": "textarea",
                                "maxlength": 1_000_000_000,
                                "locators": ["#bio"],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    cases = generate_test_data(report, {"P050": ["REQ-50", "REQ-51"]})

    assert [case["category"] for case in cases] == ["equivalence"]
    assert cases[0]["requirement_ids"] == "REQ-50, REQ-51"
    assert max(len(case["value"]) for case in cases) < 10_000


def test_does_not_invent_fill_values_for_non_fillable_or_pattern_only_fields() -> None:
    report = {
        "screens": [
            {
                "page_id": "P060",
                "url": "https://example.com/form",
                "forms": [
                    {
                        "fields": [
                            {"name": "token", "field_type": "hidden", "locators": ["#token"]},
                            {
                                "name": "code",
                                "field_type": "text",
                                "pattern": "[A-Z]{4}",
                                "locators": ["#code"],
                            },
                        ]
                    }
                ],
            }
        ]
    }

    assert generate_test_data(report) == []


def test_compound_constraints_have_one_consistent_expected_result() -> None:
    report = {
        "screens": [
            {
                "page_id": "P070",
                "url": "https://example.com/compound",
                "forms": [
                    {
                        "fields": [
                            {
                                "name": "quantity",
                                "field_type": "number",
                                "min_value": "3",
                                "max_value": "3",
                                "locators": ["#quantity"],
                            },
                            {
                                "name": "code",
                                "field_type": "text",
                                "minlength": 3,
                                "maxlength": 3,
                                "locators": ["#code"],
                            },
                        ]
                    }
                ],
            }
        ]
    }

    cases = generate_test_data(report)

    numeric_twos = [
        case for case in cases if case["field_name"] == "quantity" and case["value"] == "2"
    ]
    short_text = [case for case in cases if case["field_name"] == "code" and len(case["value"]) < 3]
    assert numeric_twos and {case["expected_client_behavior"] for case in numeric_twos} == {
        "reject_candidate"
    }
    assert short_text and {case["expected_client_behavior"] for case in short_text} == {
        "reject_candidate"
    }


def test_non_finite_number_constraints_are_ignored_without_failure() -> None:
    report = {
        "screens": [
            {
                "page_id": "P080",
                "url": "https://example.com/number",
                "forms": [
                    {
                        "fields": [
                            {
                                "name": "amount",
                                "field_type": "number",
                                "min_value": "NaN",
                                "max_value": "Infinity",
                                "locators": ["#amount"],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    cases = generate_test_data(report)

    assert [(case["category"], case["value"]) for case in cases] == [("equivalence", "1")]


def test_csv_neutralizes_formula_like_external_values_but_json_keeps_source(
    tmp_path: Path,
) -> None:
    case = {
        "case_id": "=CASE()",
        "requirement_ids": "+SUM(1,1)",
        "page_id": "-cmd|'/C calc'!A0",
        "page_url": '@HYPERLINK("https://evil.invalid")',
        "field_name": "\tformula",
        "field_type": "\rformula",
        "locator": "=1+1",
        "category": "format",
        "value": "-1",
        "expected_client_behavior": "reject_candidate",
        "source_constraint": "type=text",
        "evidence": "measured_attribute",
    }

    paths = save_test_data([case], tmp_path)

    payload = json.loads(paths["test_data_json"].read_text(encoding="utf-8"))
    assert payload["cases"][0] == case
    with paths["test_data_csv"].open(encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    for key in (
        "case_id",
        "requirement_ids",
        "page_id",
        "page_url",
        "field_name",
        "field_type",
        "locator",
    ):
        assert row[key].startswith("'")
    assert row["value"] == "-1"
