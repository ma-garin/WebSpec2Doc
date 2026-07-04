from __future__ import annotations

from pathlib import Path

from analyzer.test_conditions import TestCondition
from llm.viewpoint_generator import TestViewpoint

# SPEC-6-1: pytest の PytestCollectionWarning（Test 接頭辞クラスが __init__ を持つ）を
# ドメインモデルの命名変更なしに解消する回帰テスト。


class TestDomainModelsNotCollected:
    """TestViewpoint / TestCondition は pytest の収集対象ではないことを検証する。"""

    def test_viewpoint_opts_out_of_collection(self) -> None:
        """TestViewpoint は __test__ = False で pytest 収集対象外である。"""
        assert TestViewpoint.__test__ is False

    def test_condition_opts_out_of_collection(self) -> None:
        """TestCondition は __test__ = False で pytest 収集対象外である。"""
        assert TestCondition.__test__ is False

    def test_test_dunder_is_not_a_dataclass_field(self) -> None:
        """__test__ はアノテーション無しのクラス属性であり、
        frozen dataclass のフィールドとして扱われない（コンストラクタ引数に現れない）。"""
        viewpoint_fields = {f.name for f in TestViewpoint.__dataclass_fields__.values()}
        condition_fields = {f.name for f in TestCondition.__dataclass_fields__.values()}

        assert "__test__" not in viewpoint_fields
        assert "__test__" not in condition_fields


class TestGetdataNotUsed:
    """screenshot_diff.py が getdata() に依存していないことの静的ガード（AC-1 再発防止）。"""

    def test_screenshot_diff_source_has_no_getdata_call(self) -> None:
        """Pillow 14 で削除される Image.getdata() 呼び出しがソースに存在しないこと。"""
        source_path = Path(__file__).resolve().parent.parent / "src" / "diff" / "screenshot_diff.py"
        source = source_path.read_text(encoding="utf-8")

        assert ".getdata(" not in source
