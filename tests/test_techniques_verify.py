"""techniques.verify（性質検証器）と委譲アダプタの整合検証。

検証器そのものの正しさ（未被覆を正しく検出するか）と、
委譲後の各アダプタが真の 2-way 被覆を返すことを確かめる。
旧 test_conditions.generate_pairwise_cases は被覆を保証しない近似だった
（回帰の主対象）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from analyzer.test_conditions import generate_pairwise_cases
from crawler.page_crawler import FieldData
from mbt.pairwise import extract_factors, generate_pairwise_rows
from techniques.combinatorial import generate_covering_array
from techniques.verify import verify_t_way_coverage


# =========================================================================
# 検証器そのものの正しさ
# =========================================================================
def test_verifier_detects_missing_pair() -> None:
    """1行しか無い表は未被覆を検出する（検証器が甘くないこと）。"""
    domains = [("a", "b"), ("x", "y")]
    report = verify_t_way_coverage((("a", "x"),), domains, 2)
    assert report.ok is False
    assert report.covered == 1
    assert report.total == 4
    assert len(report.missing) == 3


def test_verifier_passes_exhaustive_table() -> None:
    domains = [("a", "b"), ("x", "y")]
    rows = (("a", "x"), ("a", "y"), ("b", "x"), ("b", "y"))
    report = verify_t_way_coverage(rows, domains, 2)
    assert report.ok
    assert report.rate == 1.0


def test_verifier_excludes_forbidden_from_denominator() -> None:
    domains = [("a", "b"), ("x", "y")]
    forbidden = (((0, "a"), (1, "x")),)
    rows = (("a", "y"), ("b", "x"), ("b", "y"))
    report = verify_t_way_coverage(rows, domains, 2, forbidden=forbidden)
    assert report.ok
    assert report.excluded_by_constraint == 1
    assert report.total == 3


# =========================================================================
# アダプタ: analyzer/test_conditions.generate_pairwise_cases
# =========================================================================
def _field(name: str, field_type: str = "text", **kw: object) -> FieldData:
    return FieldData(
        name=name, field_type=field_type, placeholder="", required=False, **kw
    )  # type: ignore[arg-type]


def test_test_conditions_pairwise_is_truly_two_way_covered() -> None:
    """旧実装が保証しなかった 2-way 被覆が、委譲後は成立する。"""
    fields = [
        _field("a", "select", options=["1", "2", "3"]),
        _field("b", "select", options=["x", "y"]),
        _field("c", "checkbox"),
        _field("d", "select", options=["p", "q", "r"]),
    ]
    cases = generate_pairwise_cases(fields)
    assert cases

    names = [f.name for f in fields]
    # 生成ケースから因子ドメインを復元して被覆検証
    domains = [tuple(dict.fromkeys(c[n] for c in cases)) for n in names]
    rows = tuple(tuple(c[n] for n in names) for c in cases)
    report = verify_t_way_coverage(rows, list(domains), 2)
    assert report.ok, f"missing={report.missing[:5]}"


def test_test_conditions_pairwise_keeps_field_cap() -> None:
    """8フィールド超は先頭8つに縮退する従来仕様を維持する。"""
    fields = [_field(f"f{i}", "select", options=["1", "2"]) for i in range(10)]
    cases = generate_pairwise_cases(fields)
    assert cases
    assert all(len(c) == 8 for c in cases)


# =========================================================================
# アダプタ: mbt/pairwise.generate_pairwise_rows
# =========================================================================
def test_mbt_pairwise_rows_are_two_way_covered() -> None:
    screen = {
        "page_id": "P1",
        "forms": [
            {
                "fields": [
                    {"name": "plan", "field_type": "select", "options": ["A", "B", "C"]},
                    {"name": "pay", "field_type": "radio", "options": ["card", "bank"]},
                    {"name": "agree", "field_type": "checkbox"},
                ]
            }
        ],
    }
    factors = extract_factors(screen)
    rows = generate_pairwise_rows(factors)
    assert rows

    names = [f["name"] for f in factors]
    domains = [tuple(f["values"]) for f in factors]
    table = tuple(tuple(r[n] for n in names) for r in rows)
    assert verify_t_way_coverage(table, list(domains), 2).ok


# =========================================================================
# アダプタ: generator/test_design（委譲後も被覆が成立）
# =========================================================================
def test_test_design_pairwise_delegation_covers() -> None:
    from generator.test_design import TestDesignParams, build_test_design

    report = {
        "screens": [
            {
                "page_id": "P1",
                "title": "t",
                "forms": [
                    {
                        "fields": [
                            {"name": "a", "field_type": "select", "options": ["1", "2", "3"]},
                            {"name": "b", "field_type": "select", "options": ["x", "y"]},
                            {"name": "c", "field_type": "radio", "options": ["p", "q"]},
                        ]
                    }
                ],
            }
        ]
    }
    design = build_test_design(report, TestDesignParams())
    pw = design.screens[0].pairwise
    assert pw is not None
    domains = [p.values for p in pw.params]
    assert verify_t_way_coverage(pw.rows, list(domains), pw.strength).ok


def test_engine_result_matches_direct_call() -> None:
    """アダプタ経由と正準API直呼びが同一の表を返す（委譲が透過的）。"""
    domains = [("1", "2", "3"), ("x", "y"), ("p", "q")]
    direct = generate_covering_array(list(domains), 2)
    factors = [{"name": f"f{i}", "values": list(d)} for i, d in enumerate(domains)]
    via_mbt = generate_pairwise_rows(factors)
    assert [tuple(r[f"f{i}"] for i in range(3)) for r in via_mbt] == list(direct.rows)
