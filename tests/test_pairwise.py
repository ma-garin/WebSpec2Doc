"""ペアワイズ法の契約。

守るべきは「全ペアの完全被覆」「決定性」「実測選択肢以外を発明しないこと」。
"""

from __future__ import annotations

from itertools import combinations, product

from mbt.pairwise import (
    build_pairwise_cases,
    extract_factors,
    generate_pairwise_rows,
)


def _factors(*specs: tuple[str, list[str]]) -> list[dict]:
    return [{"name": n, "field_type": "select", "values": v} for n, v in specs]


def _all_pairs_covered(factors: list[dict], rows: list[dict]) -> bool:
    names = [f["name"] for f in factors]
    for (i, fi), (j, fj) in combinations(enumerate(factors), 2):
        for a, b in product(fi["values"], fj["values"]):
            if not any(row[names[i]] == a and row[names[j]] == b for row in rows):
                return False
    return True


# ─────────────────── 生成の正しさ ───────────────────


def test_every_value_pair_is_covered_3x3x3() -> None:
    factors = _factors(("a", ["1", "2", "3"]), ("b", ["x", "y", "z"]), ("c", ["p", "q", "r"]))

    rows = generate_pairwise_rows(factors)

    assert _all_pairs_covered(factors, rows)


def test_pairwise_is_smaller_than_exhaustive() -> None:
    """3^4=81 通りを2因子網羅なら十数行に圧縮できる（それが存在意義）。"""
    factors = _factors(*[(f"f{i}", ["1", "2", "3"]) for i in range(4)])

    rows = generate_pairwise_rows(factors)

    assert _all_pairs_covered(factors, rows)
    assert len(rows) < 81 / 3


def test_generation_is_deterministic() -> None:
    factors = _factors(("a", ["1", "2"]), ("b", ["x", "y", "z"]), ("c", ["p", "q"]))

    assert generate_pairwise_rows(factors) == generate_pairwise_rows(factors)


def test_rows_only_use_measured_values() -> None:
    factors = _factors(("plan", ["free", "pro"]), ("region", ["jp", "us"]))

    for row in generate_pairwise_rows(factors):
        assert row["plan"] in {"free", "pro"}
        assert row["region"] in {"jp", "us"}


def test_single_factor_yields_no_rows() -> None:
    assert generate_pairwise_rows(_factors(("only", ["1", "2"]))) == []


def test_two_factors_cover_full_cross_product() -> None:
    factors = _factors(("a", ["1", "2"]), ("b", ["x", "y"]))

    rows = generate_pairwise_rows(factors)

    assert len(rows) == 4  # 2因子なら全組合せ＝ペア被覆
    assert _all_pairs_covered(factors, rows)


# ─────────────────── 因子抽出 ───────────────────


def test_factors_come_from_select_radio_and_checkbox_only() -> None:
    screen = {
        "forms": [
            {
                "fields": [
                    {"name": "plan", "field_type": "select", "options": ["free", "pro"]},
                    {"name": "agree", "field_type": "checkbox", "options": []},
                    {"name": "memo", "field_type": "text", "options": []},
                    {"name": "single", "field_type": "select", "options": ["only-one"]},
                ]
            }
        ]
    }

    factors = extract_factors(screen)

    assert [f["name"] for f in factors] == ["plan", "agree"]
    assert factors[1]["values"] == ["on", "off"]


# ─────────────────── ケース組み立て ───────────────────


def test_cases_report_compression_and_claim_scope() -> None:
    report = {
        "screens": [
            {
                "page_id": "P010",
                "url": "https://e.com/search",
                "forms": [
                    {
                        "fields": [
                            {"name": "type", "field_type": "select", "options": ["a", "b", "c"]},
                            {"name": "area", "field_type": "select", "options": ["e", "w"]},
                            {"name": "sort", "field_type": "select", "options": ["new", "old"]},
                        ]
                    }
                ],
            }
        ]
    }

    cases = build_pairwise_cases(report)

    assert cases
    first = cases[0]
    assert first["case_id"] == "PW2-P010-001"
    assert first["exhaustive_total"] == 12
    assert first["pairwise_total"] == len(cases)
    assert first["pairwise_total"] < 12
    assert first["claim_scope"] == "measured_options_only"


def test_screens_without_combinable_factors_produce_nothing() -> None:
    report = {
        "screens": [
            {
                "page_id": "P020",
                "url": "u",
                "forms": [{"fields": [{"name": "q", "field_type": "text"}]}],
            }
        ]
    }

    assert build_pairwise_cases(report) == []
