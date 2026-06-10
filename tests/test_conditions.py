"""test_conditions のユニットテスト"""

from __future__ import annotations

from analyzer.test_conditions import (
    compute_risk_score,
    derive_conditions,
    generate_decision_table,
    generate_pairwise_cases,
)
from crawler.page_crawler import FieldData, FormData


def _field(**kw) -> FieldData:
    base = dict(field_type="text", name="x", placeholder="", required=False)
    base.update(kw)
    return FieldData(**base)


def _form(*fields: FieldData) -> FormData:
    return FormData(action="/", method="post", fields=fields)


class TestDeriveConditions:
    def test_required_adds_empty_check(self) -> None:
        assert any("未入力" in c for c in derive_conditions(_field(required=True)))

    def test_maxlength_boundary(self) -> None:
        assert any("19/20/21" in c for c in derive_conditions(_field(maxlength=20)))

    def test_minlength(self) -> None:
        assert any("最小長" in c for c in derive_conditions(_field(minlength=8)))

    def test_email_format(self) -> None:
        assert any("メール形式" in c for c in derive_conditions(_field(field_type="email")))

    def test_number_range(self) -> None:
        conds = derive_conditions(_field(field_type="number", min_value="1", max_value="10"))
        assert any("範囲" in c for c in conds)

    def test_date_no_range(self) -> None:
        assert any("日付" in c for c in derive_conditions(_field(field_type="date")))

    def test_select_options(self) -> None:
        conds = derive_conditions(_field(field_type="select", options=("a", "b", "c")))
        assert any("選択肢3件" in c for c in conds)

    def test_pattern(self) -> None:
        assert any("パターン" in c for c in derive_conditions(_field(pattern="[0-9]+")))

    def test_checkbox(self) -> None:
        assert any("ON / OFF" in c for c in derive_conditions(_field(field_type="checkbox")))

    def test_fallback_when_no_constraints(self) -> None:
        assert derive_conditions(_field()) == ("正常値 / 空値 / 特殊文字",)


class TestGeneratePairwiseCases:
    def test_generate_pairwise_cases_two_fields(self) -> None:
        # 2フィールドで全組み合わせが生成される
        f1 = _field(name="email", field_type="email")
        f2 = _field(name="password", field_type="password")
        cases = generate_pairwise_cases([f1, f2])
        assert len(cases) > 0
        # 各ケースに両フィールドが存在する
        for case in cases:
            assert "email" in case
            assert "password" in case

    def test_generate_pairwise_cases_handles_empty(self) -> None:
        # フィールドなしで空リストを返す
        assert generate_pairwise_cases([]) == []

    def test_generate_pairwise_cases_caps_at_twenty(self) -> None:
        # 多フィールドで20ケース以内に収まる
        fields = [
            _field(name=f"f{i}", field_type="text")
            for i in range(10)
        ]
        cases = generate_pairwise_cases(fields)
        assert len(cases) <= 20

    def test_generate_pairwise_cases_single_field(self) -> None:
        f = _field(name="q", field_type="text")
        cases = generate_pairwise_cases([f])
        assert len(cases) > 0
        assert all("q" in c for c in cases)

    def test_generate_pairwise_cases_covers_field_names(self) -> None:
        # 3フィールドで各ケースに全フィールドキーが含まれる
        fields = [_field(name=f"n{i}") for i in range(3)]
        cases = generate_pairwise_cases(fields)
        for case in cases:
            for f in fields:
                assert f.name in case

    def test_generate_pairwise_cases_options_field(self) -> None:
        # options フィールドは先頭・末尾・空/invalid から代表値を選ぶ
        f = _field(name="sel", field_type="select", options=("a", "b", "c"))
        cases = generate_pairwise_cases([f])
        values = {c["sel"] for c in cases}
        assert "a" in values
        assert "c" in values

    def test_generate_pairwise_cases_eight_field_cap(self) -> None:
        # 9フィールドでも先頭8フィールドのキーのみ含む
        fields = [_field(name=f"f{i}") for i in range(9)]
        cases = generate_pairwise_cases(fields)
        assert all("f8" not in c for c in cases)


class TestGenerateDecisionTable:
    def test_returns_empty_when_no_fields(self) -> None:
        assert generate_decision_table([], ["/ok"]) == []

    def test_returns_empty_when_no_transitions(self) -> None:
        assert generate_decision_table([_field(name="x")], []) == []

    def test_rows_contain_conditions_and_transition(self) -> None:
        fields = [_field(name="user", required=True), _field(name="pass", required=True)]
        rows = generate_decision_table(fields, ["/home", "/error"])
        assert len(rows) > 0
        for row in rows:
            assert "conditions" in row
            assert "expected_transition" in row

    def test_required_field_uses_fulfilled_labels(self) -> None:
        f = _field(name="mail", required=True)
        rows = generate_decision_table([f], ["/next"])
        all_states = {row["conditions"]["mail"] for row in rows}  # type: ignore[index]
        assert "充足" in all_states or "未充足" in all_states

    def test_optional_field_uses_input_labels(self) -> None:
        f = _field(name="note", required=False)
        rows = generate_decision_table([f], ["/next"])
        all_states = {row["conditions"]["note"] for row in rows}  # type: ignore[index]
        assert "入力" in all_states or "未入力" in all_states

    def test_five_fields_reduces_rows(self) -> None:
        # 5フィールド以上はペアワイズで縮退するため全組み合わせ(2^5=32)より少ない
        fields = [_field(name=f"f{i}", required=True) for i in range(5)]
        rows = generate_decision_table(fields, ["/ok"])
        assert len(rows) < 32


class TestComputeRiskScore:
    def test_compute_risk_score_payment_page_has_high_criticality(self) -> None:
        # 見出しに「決済」を含む場合 criticality=3.0
        form = _form(
            _field(name="amount", field_type="number", required=True),
            _field(name="card", field_type="text", required=True),
        )
        score_payment = compute_risk_score([form], ("決済フォーム",))
        score_normal = compute_risk_score([form], ("問い合わせ",))
        assert score_payment > score_normal
        assert score_payment == score_normal * 3.0

    def test_compute_risk_score_empty_form_minimal(self) -> None:
        # フォームなしで低いスコア（0.0）
        score = compute_risk_score([], ("お問い合わせ",))
        assert score == 0.0

    def test_compute_risk_score_caps_at_100(self) -> None:
        # 大量フィールド＋決済キーワードでも100を超えない
        fields = tuple(
            _field(name=f"f{i}", required=True, maxlength=10, options=("a", "b", "c"))
            for i in range(20)
        )
        form = _form(*fields)
        score = compute_risk_score([form], ("決済", "クレジット"), change_freq=1.0)
        assert score <= 100.0

    def test_compute_risk_score_change_freq_increases_score(self) -> None:
        form = _form(_field(name="q", required=True))
        score_low = compute_risk_score([form], ("検索",), change_freq=0.0)
        score_high = compute_risk_score([form], ("検索",), change_freq=1.0)
        assert score_high > score_low

    def test_compute_risk_score_password_keyword(self) -> None:
        form = _form(_field(name="pw", field_type="password", required=True))
        score = compute_risk_score([form], ("password reset",))
        assert score > 0.0
        # password キーワードで高 criticality
        score_plain = compute_risk_score([form], ("設定",))
        assert score > score_plain

    def test_compute_risk_score_multiple_forms(self) -> None:
        form1 = _form(_field(name="a", required=True))
        form2 = _form(_field(name="b", required=True), _field(name="c"))
        score = compute_risk_score([form1, form2], ("一般",))
        assert score > 0.0
