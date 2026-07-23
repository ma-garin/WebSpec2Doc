"""テスト技法の実適用（src/autorun/techniques.py）のテスト。

これまで段階11（テスト基本設計）は技法の**名前を割り当てるだけ**で、
「同値分割」と書かれていても実際の同値クラスは1つも作られていなかった。
本モジュールは観測データから技法を実際に適用する。その正しさを検証する。
"""

from __future__ import annotations

from autorun.techniques import (
    TECHNIQUE_BOUNDARY,
    TECHNIQUE_EQUIVALENCE,
    apply_all,
    boundary_values,
    decision_table,
    equivalence_classes,
    pairwise_pairs,
    state_transitions,
)


class TestEquivalencePartitioning:
    def test_required_field_treats_empty_as_invalid_class(self) -> None:
        values = equivalence_classes({"name": "x", "field_type": "text", "required": True})
        empty = next(v for v in values if v.value == "")
        assert empty.valid is False
        assert empty.technique == TECHNIQUE_EQUIVALENCE

    def test_optional_field_has_no_empty_invalid_class(self) -> None:
        values = equivalence_classes({"name": "x", "field_type": "text", "required": False})
        assert all(v.value != "" for v in values)

    def test_email_gets_format_classes(self) -> None:
        labels = {v.label for v in equivalence_classes({"field_type": "email"})}
        assert "@なし" in labels
        assert "ドメインなし" in labels

    def test_number_range_yields_in_and_out_of_range(self) -> None:
        values = equivalence_classes({"field_type": "number", "min_value": "1", "max_value": "9"})
        assert any(v.valid and v.label == "範囲内" for v in values)
        assert any(not v.valid and "下限未満" in v.label for v in values)
        assert any(not v.valid and "上限超過" in v.label for v in values)

    def test_select_treats_each_option_as_a_class(self) -> None:
        values = equivalence_classes({"field_type": "select", "options": ["no", "email", "tel"]})
        assert {v.value for v in values} >= {"no", "email", "tel"}


class TestBoundaryValueAnalysis:
    def test_three_point_boundary_at_lower_limit(self) -> None:
        """JSTQB の3値境界: 境界の直前・境界・直後。"""
        values = boundary_values({"min_value": "1", "max_value": "9"})
        by_value = {v.value: v for v in values}
        assert by_value["0"].valid is False  # 下限-1
        assert by_value["1"].valid is True  # 下限
        assert by_value["2"].valid is True  # 下限+1

    def test_three_point_boundary_at_upper_limit(self) -> None:
        by_value = {v.value: v for v in boundary_values({"min_value": "1", "max_value": "9"})}
        assert by_value["8"].valid is True
        assert by_value["9"].valid is True
        assert by_value["10"].valid is False

    def test_maxlength_boundary(self) -> None:
        values = boundary_values({"maxlength": 140})
        over = next(v for v in values if len(v.value) == 141)
        assert over.valid is False
        assert over.technique == TECHNIQUE_BOUNDARY

    def test_no_constraints_yields_nothing(self) -> None:
        assert boundary_values({"field_type": "text"}) == ()


class TestDecisionTable:
    def test_rules_cover_each_required_field_omission(self) -> None:
        fields = [
            {"name": "date", "required": True},
            {"name": "term", "required": True},
            {"name": "memo", "required": False},
        ]
        table = decision_table(fields)
        assert table["applicable"] is True
        # 全入力(1) + 必須項目ごとの欠落(2) = 3規則
        assert len(table["rules"]) == 3
        assert table["conditions"] == ["date", "term"]

    def test_first_rule_is_all_present_and_valid(self) -> None:
        table = decision_table([{"name": "a", "required": True}])
        assert table["rules"][0]["expected_valid"] is True

    def test_omission_rules_expect_rejection(self) -> None:
        table = decision_table([{"name": "a", "required": True}])
        assert table["rules"][1]["expected_valid"] is False
        assert "必須エラー" in table["rules"][1]["action"]

    def test_no_required_fields_is_not_applicable(self) -> None:
        assert decision_table([{"name": "a", "required": False}])["applicable"] is False

    def test_avoids_combinatorial_explosion(self) -> None:
        """必須10項目でも 2^10 ではなく 11 規則に収める。"""
        fields = [{"name": f"f{i}", "required": True} for i in range(10)]
        assert len(decision_table(fields)["rules"]) == 11


class TestStateTransition:
    def test_zero_switch_coverage_from_observed_transitions(self) -> None:
        screens = [
            {"page_id": "P001", "transitions": {"to": ["P002", "P003"]}},
            {"page_id": "P002", "transitions": {"to": ["P001"]}},
        ]
        result = state_transitions(screens)
        assert result["applicable"] is True
        assert len(result["transitions"]) == 3
        assert "0-switch" in result["coverage"]

    def test_no_transitions_is_not_applicable(self) -> None:
        assert state_transitions([{"page_id": "P001"}])["applicable"] is False


class TestPairwise:
    def test_pairs_are_generated_for_two_factors(self) -> None:
        fields = [
            {"name": "contact", "field_type": "select", "options": ["no", "email"]},
            {"name": "breakfast", "field_type": "checkbox"},
        ]
        result = pairwise_pairs(fields)
        assert result["applicable"] is True
        assert result["required_pairs"] == 4  # 2 x 2
        assert "2因子間網羅" in result["coverage"]

    def test_single_factor_is_not_applicable(self) -> None:
        fields = [{"name": "x", "field_type": "select", "options": ["a", "b"]}]
        assert pairwise_pairs(fields)["applicable"] is False


class TestApplyAll:
    def test_produces_concrete_cases_from_a_real_screen(self) -> None:
        """実観測に近い構造から、具体的なテスト値が導出されること。"""
        screen = {
            "page_id": "P011",
            "forms": [
                {
                    "fields": [
                        {"name": "date", "field_type": "text", "required": True},
                        {
                            "name": "term",
                            "field_type": "number",
                            "required": True,
                            "min_value": "1",
                            "max_value": "9",
                        },
                        {
                            "name": "contact",
                            "field_type": "select",
                            "required": True,
                            "options": ["Choose one", "no", "email"],
                        },
                        {"name": "plan-id", "field_type": "hidden"},
                    ]
                }
            ],
        }
        result = apply_all(screen)
        assert result["page_id"] == "P011"
        # hidden は除外される
        assert all(f["field"] != "plan-id" for f in result["fields"])
        assert result["total_cases"] > 0
        # 必須3項目 → 4規則
        assert len(result["decision_table"]["rules"]) == 4

    def test_empty_screen_yields_no_cases(self) -> None:
        result = apply_all({"page_id": "P001", "forms": []})
        assert result["total_cases"] == 0
        assert result["decision_table"]["applicable"] is False
