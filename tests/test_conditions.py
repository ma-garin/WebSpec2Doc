"""test_conditions.derive_conditions のユニットテスト"""

from __future__ import annotations

from analyzer.test_conditions import derive_conditions
from crawler.page_crawler import FieldData


def _field(**kw) -> FieldData:
    base = dict(field_type="text", name="x", placeholder="", required=False)
    base.update(kw)
    return FieldData(**base)


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
