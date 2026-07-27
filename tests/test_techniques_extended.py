"""追加したテスト技法（分類ツリー法・直交表・原因結果グラフ・ドメイン分析・
エラー推測・ユースケーステスト）の検証。

各技法について次を確認する:

- 実測属性が無い入力では適用外（applicable=False）になり、値を捏造しない
- 技法固有の数学的性質（直交表の均等割付け、分類ツリーのクラス被覆）が成り立つ
- 同一入力から同一出力になる（決定的）
"""

from __future__ import annotations

import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from autorun.cause_effect import CONSTRAINT_MASKS, build_graph, cause_effect_graph
from autorun.classification_tree import (
    build_classification_tree,
    classification_tree,
)
from autorun.domain_analysis import domain_analysis
from autorun.error_guessing import (
    CATALOG_CONFIDENCE,
    CATEGORY_STANDARD,
    error_guessing,
)
from autorun.orthogonal_array import (
    build_array,
    orthogonal_array,
    verify_orthogonality,
)
from autorun.techniques import apply_all, apply_cross_screen
from autorun.use_case_testing import use_case_testing

# =========================================================================
# 共通のテストデータ
# =========================================================================
FIELDS = [
    {"name": "email", "field_type": "email", "required": True, "maxlength": 255},
    {"name": "age", "field_type": "number", "required": True, "min_value": 18, "max_value": 120},
    {"name": "plan", "field_type": "select", "options": ["A", "B", "C"]},
    {"name": "pay", "field_type": "select", "options": ["card", "bank", "cod"]},
    {"name": "agree", "field_type": "checkbox", "required": True},
]

SCREEN = {
    "page_id": "p1",
    "title": "申込フォーム",
    "forms": [{"name": "apply", "fields": FIELDS}],
    "transitions": {"to": ["p2"]},
}

GOAL_SCREEN = {"page_id": "p2", "title": "完了", "transitions": {"to": []}}

EMPTY_SCREEN = {"page_id": "p0", "title": "案内", "forms": [], "transitions": {"to": []}}


# =========================================================================
# 分類ツリー法
# =========================================================================
def test_classification_tree_covers_every_class_at_least_once() -> None:
    """クラス被覆: 全クラスが組合せ表に最低 1 回現れる。"""
    tree = build_classification_tree(SCREEN)
    assert tree.branches

    for branch in tree.branches:
        appeared: set[tuple[str, str]] = set()
        for row in branch.combinations:
            for name, label in row["selection"].items():
                appeared.add((name, label))
        for classification in branch.classifications:
            for cls in classification.classes:
                assert (classification.name, cls.label) in appeared, (
                    f"{classification.name} のクラス「{cls.label}」が被覆されていない"
                )


def test_classification_tree_row_count_is_lower_bound() -> None:
    """行数は最大クラス数に一致する（クラス被覆の下限）。"""
    tree = build_classification_tree(SCREEN)
    for branch in tree.branches:
        expected = max(len(c.classes) for c in branch.classifications)
        assert len(branch.combinations) == expected


def test_classification_tree_does_not_combine_across_forms() -> None:
    """別フォームの項目は同時送信されないため、組合せを作らない。"""
    screen = {
        "page_id": "p1",
        "forms": [
            {"name": "search", "fields": [{"name": "q", "field_type": "text"}]},
            {"name": "login", "fields": [{"name": "user", "field_type": "text"}]},
        ],
    }
    tree = build_classification_tree(screen)
    assert len(tree.branches) == 2
    for branch in tree.branches:
        for row in branch.combinations:
            assert set(row["selection"]) <= {c.name for c in branch.classifications}


def test_classification_tree_not_applicable_without_fields() -> None:
    result = classification_tree(EMPTY_SCREEN)
    assert result["applicable"] is False
    assert "reason" in result


# =========================================================================
# 直交表
# =========================================================================
@pytest.mark.parametrize(
    ("prime", "factors", "expected_name"),
    [
        (2, 3, "L4(2^3)"),
        (2, 7, "L8(2^7)"),
        (3, 4, "L9(3^4)"),
        (3, 13, "L27(3^13)"),
        (5, 6, "L25(5^6)"),
    ],
)
def test_build_array_produces_standard_arrays(
    prime: int, factors: int, expected_name: str
) -> None:
    """文献の標準直交表と同じ形（行数・列数）が生成される。"""
    array = build_array(prime, factors)
    assert array is not None
    assert array.name == expected_name


@pytest.mark.parametrize(("prime", "factors"), [(2, 3), (2, 7), (3, 4), (3, 13), (5, 6)])
def test_generated_arrays_are_orthogonal(prime: int, factors: int) -> None:
    """任意の 2 列で全水準組が同数回現れる（均等割付け）ことを数え上げで検査する。"""
    array = build_array(prime, factors)
    assert array is not None
    assert verify_orthogonality(array) is True

    expected = len(array.rows) // (prime**2)
    for i, j in combinations(range(array.column_count), 2):
        counts: dict[tuple[int, int], int] = {}
        for row in array.rows:
            counts[(row[i], row[j])] = counts.get((row[i], row[j]), 0) + 1
        assert len(counts) == prime**2
        assert set(counts.values()) == {expected}


def test_orthogonal_array_reports_collapsed_factors() -> None:
    """水準を畳み込んだ因子は均等性が崩れるため、必ず報告される。"""
    result = orthogonal_array(FIELDS)
    assert result["applicable"] is True
    assert "agree" in result["collapsed_factors"]
    assert result["notice"]


def test_orthogonal_array_not_applicable_with_few_factors() -> None:
    result = orthogonal_array([{"name": "q", "field_type": "text"}])
    assert result["applicable"] is False


# =========================================================================
# 原因結果グラフ
# =========================================================================
def test_cause_effect_derives_causes_only_from_measured_attributes() -> None:
    """属性の無い項目からは原因を作らない。"""
    graph = build_graph([{"name": "free", "field_type": "text"}])
    assert graph.causes == ()


def test_cause_effect_masks_constraint_for_multi_condition_field() -> None:
    """同一項目に複数条件があるとき、M（マスク）制約が付く。"""
    result = cause_effect_graph(FIELDS)
    assert result["applicable"] is True
    kinds = {c["kind"] for c in result["graph"]["constraints"]}
    assert CONSTRAINT_MASKS in kinds


def test_cause_effect_rule_count_is_causes_plus_one() -> None:
    """全真の 1 規則 + 各原因を単独で偽にする n 規則。"""
    result = cause_effect_graph(FIELDS)
    assert result["case_count"] == result["cause_count"] + 1


# =========================================================================
# ドメイン分析
# =========================================================================
def test_domain_analysis_produces_on_off_in_out_points() -> None:
    result = domain_analysis(FIELDS)
    assert result["applicable"] is True
    for row in result["matrix"]:
        assert set(row) >= {"on", "off", "in", "out", "source_attribute"}
        assert row["in"]["valid"] is True
        assert row["out"]["valid"] is False


def test_domain_analysis_off_point_is_invalid_for_closed_boundary() -> None:
    """閉境界（min/max）の OFF 点は領域外なので無効。"""
    result = domain_analysis([{"name": "age", "field_type": "number", "min_value": 18}])
    row = result["matrix"][0]
    assert row["on"]["value"] == "18"
    assert row["off"]["value"] == "17"
    assert row["on"]["valid"] is True
    assert row["off"]["valid"] is False


def test_domain_analysis_not_applicable_without_boundaries() -> None:
    result = domain_analysis([{"name": "free", "field_type": "text"}])
    assert result["applicable"] is False


# =========================================================================
# エラー推測
# =========================================================================
def test_error_guessing_marks_knowledge_based_confidence() -> None:
    """一般知識由来のため confidence は実測（1.0）未満で固定される。"""
    result = error_guessing(FIELDS)
    assert result["applicable"] is True
    assert result["confidence"] == CATALOG_CONFIDENCE
    assert result["confidence"] < 1.0
    for guess in result["guesses"]:
        assert guess["confidence"] == CATALOG_CONFIDENCE
        assert "未実測" in guess["evidence"]


def test_error_guessing_includes_form_level_defects() -> None:
    result = error_guessing(FIELDS, has_form=True)
    targets = {g["target"] for g in result["guesses"]}
    assert "画面全体" in targets


def test_error_guessing_skips_unknown_field_types() -> None:
    result = error_guessing([{"name": "x", "field_type": "color"}], has_form=False)
    assert result["applicable"] is False


def test_every_defect_category_maps_to_an_external_taxonomy() -> None:
    """自作分類を独自体系として出さない。全分類が外部体系へ対応付けられている。"""
    all_fields = [
        {"name": n, "field_type": t}
        for n, t in [
            ("a", "text"),
            ("b", "textarea"),
            ("c", "number"),
            ("d", "email"),
            ("e", "date"),
            ("f", "password"),
            ("g", "tel"),
            ("h", "file"),
        ]
    ]
    result = error_guessing(all_fields)
    assert result["unmapped_categories"] == [], (
        f"外部体系へ対応付けられていない分類がある: {result['unmapped_categories']}"
    )
    for category in result["categories"]:
        assert CATEGORY_STANDARD[category]


def test_error_guessing_declares_mapping_is_not_official() -> None:
    """対応付けが本システム独自であることを出力で明示する。"""
    result = error_guessing(FIELDS)
    assert "公式に定めた" in result["notice"]
    assert result["reference_taxonomies"]


# =========================================================================
# ユースケーステスト
# =========================================================================
def test_use_case_builds_basic_and_exception_flows() -> None:
    result = use_case_testing([SCREEN, GOAL_SCREEN])
    assert result["applicable"] is True
    flows = [f for uc in result["use_cases"] for f in uc["flows"]]
    types = {f["type"] for f in flows}
    assert "基本フロー" in types
    assert "例外フロー" in types


def test_use_case_declares_candidates_are_not_guaranteed() -> None:
    """業務ユースケースとの一致を保証しない旨が出力に含まれる。"""
    result = use_case_testing([SCREEN, GOAL_SCREEN])
    assert "保証しない" in result["notice"]


def test_use_case_not_applicable_without_transitions() -> None:
    result = use_case_testing([{"page_id": "only", "transitions": {"to": []}}])
    assert result["applicable"] is False


def test_use_case_records_dropped_paths_not_silently() -> None:
    """上限で捨てた迂回路を、件数と内容の両方で残す（黙って切らない）。"""
    screens = [
        {"page_id": "P1", "title": "入口", "transitions": {"to": ["P2", "P3", "P4", "GOAL"]}},
        {"page_id": "P2", "title": "A", "transitions": {"to": ["P3", "GOAL"]}},
        {"page_id": "P3", "title": "B", "transitions": {"to": ["P4", "GOAL"]}},
        {"page_id": "P4", "title": "C", "transitions": {"to": ["GOAL"]}},
        {"page_id": "GOAL", "title": "完了", "transitions": {"to": []}},
    ]
    result = use_case_testing(screens)
    assert result["dropped_count"] > 0
    assert len(result["dropped_paths"]) == result["dropped_count"]
    for item in result["dropped_paths"]:
        assert item["steps"]
        assert "上限" in item["reason"] or "超過" in item["reason"]
    assert "除外している" in result["notice"]


def test_use_case_reports_no_drop_when_all_paths_fit() -> None:
    result = use_case_testing([SCREEN, GOAL_SCREEN])
    assert result["dropped_count"] == 0
    assert "除外している" not in result["notice"]


# =========================================================================
# 統合
# =========================================================================
def test_apply_all_exposes_every_technique_block() -> None:
    result = apply_all(SCREEN)
    for key in (
        "decision_table",
        "pairwise",
        "classification_tree",
        "orthogonal_array",
        "cause_effect",
        "domain_analysis",
        "error_guessing",
    ):
        assert key in result, f"{key} が apply_all の出力に無い"
        assert "applicable" in result[key]


def test_apply_all_is_deterministic() -> None:
    """同一入力からは同一出力（差分比較のため）。"""
    assert apply_all(SCREEN) == apply_all(SCREEN)


def test_apply_cross_screen_is_deterministic() -> None:
    screens = [SCREEN, GOAL_SCREEN]
    assert apply_cross_screen(screens) == apply_cross_screen(screens)


def test_technique_case_counts_covers_applied_techniques() -> None:
    counts = apply_all(SCREEN)["technique_case_counts"]
    assert counts["分類ツリー法"] > 0
    assert counts["直交表"] > 0
    assert counts["原因結果グラフ"] > 0
    assert counts["ドメイン分析"] > 0
    assert counts["エラー推測"] > 0


def test_no_technique_fabricates_values_on_empty_screen() -> None:
    """観測が無い画面では、どの技法もケースを作らない（evidence-only）。"""
    result = apply_all(EMPTY_SCREEN)
    assert result["total_cases"] == 0
    for key in (
        "decision_table",
        "pairwise",
        "classification_tree",
        "orthogonal_array",
        "cause_effect",
        "domain_analysis",
        "error_guessing",
    ):
        assert result[key]["applicable"] is False
