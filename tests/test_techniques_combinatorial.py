"""techniques.combinatorial（被覆配列の正準実装）の検証。

被覆性はアルゴリズムを信用せず techniques.verify の数え上げ検査で確かめる。
固定パラメータ格子（水準数2-5 × 因子数2-8）の全組合せで property test を行う。
"""

from __future__ import annotations

import sys
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from techniques.combinatorial import (
    CoverageRequirement,
    generate_covering_array,
)
from techniques.verify import verify_t_way_coverage


def _domains(levels: int, factors: int) -> list[tuple[str, ...]]:
    return [tuple(f"f{i}v{j}" for j in range(levels)) for i in range(factors)]


# =========================================================================
# 被覆性（property test: 水準2-5 × 因子2-8 の全組合せ）
# =========================================================================
@pytest.mark.parametrize(
    ("levels", "factors"),
    [(lv, fc) for lv, fc in product(range(2, 6), range(2, 9))],
)
def test_two_way_coverage_holds_on_grid(levels: int, factors: int) -> None:
    domains = _domains(levels, factors)
    result = generate_covering_array(domains, 2)
    report = verify_t_way_coverage(result.rows, domains, 2)
    assert report.ok, f"levels={levels} factors={factors} missing={report.missing[:3]}"
    assert result.uncoverable == ()


@pytest.mark.parametrize(("levels", "factors"), [(2, 4), (3, 4), (2, 6), (3, 5)])
def test_three_way_coverage_holds(levels: int, factors: int) -> None:
    domains = _domains(levels, factors)
    result = generate_covering_array(domains, 3)
    report = verify_t_way_coverage(result.rows, domains, 3)
    assert report.ok


def test_rows_are_smaller_than_exhaustive() -> None:
    """被覆配列の意義: 全数より十分小さいこと（3^4=81 全数に対し2-wayは十数行）。"""
    domains = _domains(3, 4)
    result = generate_covering_array(domains, 2)
    assert 0 < len(result.rows) < 81 / 2


# =========================================================================
# 決定性
# =========================================================================
def test_generation_is_deterministic() -> None:
    domains = _domains(3, 5)
    assert generate_covering_array(domains, 2) == generate_covering_array(domains, 2)


# =========================================================================
# 制約（forbidden tuples）
# =========================================================================
def test_forbidden_tuple_never_appears_in_any_row() -> None:
    domains = _domains(3, 4)
    forbidden = (((0, "f0v0"), (1, "f1v1")),)
    result = generate_covering_array(domains, 2, forbidden=forbidden)
    for row in result.rows:
        assert not (row[0] == "f0v0" and row[1] == "f1v1")
    # 禁止組は分母から除いた上で残りは全被覆
    report = verify_t_way_coverage(result.rows, domains, 2, forbidden=forbidden)
    assert report.ok
    assert report.excluded_by_constraint == 1


def test_conflicting_constraints_report_uncoverable_instead_of_looping() -> None:
    """因子0のある値が他因子の全値と禁止 → その値絡みの組は被覆不能として記録される。"""
    domains = [("a", "b"), ("x", "y")]
    forbidden = (((0, "a"), (1, "x")), ((0, "a"), (1, "y")))
    result = generate_covering_array(domains, 2, forbidden=forbidden)
    # "a" を含む行は構成できないが、関数は停止し、行は b 側だけで構成される
    for row in result.rows:
        assert row[0] == "b"
    report = verify_t_way_coverage(result.rows, domains, 2, forbidden=forbidden)
    assert report.ok  # 禁止組を除いた残り（b,x)(b,y) は被覆


# =========================================================================
# seeding
# =========================================================================
def test_seeds_reduce_generated_rows() -> None:
    domains = _domains(3, 4)
    base = generate_covering_array(domains, 2)
    # 既存ケースとして base の先頭3行を種に渡すと、生成行数は減る
    seeds = base.rows[:3]
    seeded = generate_covering_array(domains, 2, seeds=seeds)
    assert seeded.covered_by_seeds > 0
    assert len(seeded.rows) < len(base.rows)
    # 種 + 生成行で全被覆
    report = verify_t_way_coverage(tuple(seeds) + seeded.rows, domains, 2)
    assert report.ok


# =========================================================================
# mixed-strength
# =========================================================================
def test_mixed_strength_covers_both_requirements() -> None:
    """全体2-way + 先頭3因子だけ3-way の混在要求。"""
    domains = _domains(2, 5)
    reqs = (
        CoverageRequirement(strength=2),
        CoverageRequirement(strength=3, factor_indices=(0, 1, 2)),
    )
    result = generate_covering_array(domains, requirements=reqs)
    assert verify_t_way_coverage(result.rows, domains, 2).ok
    # 部分集合の3-way: 因子0-2のみの射影で全 2^3=8 組が現れる
    projections = {(row[0], row[1], row[2]) for row in result.rows}
    assert len(projections) == 8


# =========================================================================
# 境界入力
# =========================================================================
def test_empty_and_degenerate_inputs() -> None:
    assert generate_covering_array([], 2).rows == ()
    assert generate_covering_array([("a",)], 2).rows == ()  # 強度>因子数
    single = generate_covering_array([("a", "b")], 1)
    assert verify_t_way_coverage(single.rows, [("a", "b")], 1).ok
