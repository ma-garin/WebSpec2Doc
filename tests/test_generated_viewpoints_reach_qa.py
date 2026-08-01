"""生成した観点が QA 出力まで届くことを検証する。

観点は WebSpec2Doc のエンジンである。観点ストアに保存できただけでは
何も動いていない。保存 → 選択 → QA 生成 → 出力 の経路を通って初めて
利用者に届く。

このテストが無かったため、60領域・2,600観点を生成しながら、それが
QA 生成側の分類（category_l2 / quality_area_l1）と噛み合わず1件も
使われない状態を検出できなかった。既定セット（38件）が別に存在し、
エンジンはそちらだけを見ていたので、既存テストは全て緑のままだった。
"""

from __future__ import annotations

from typing import Any

import pytest

from web.services.qa.helpers import (
    _load_qa_viewpoints,
    _viewpoint_names,
    _viewpoints_by_type,
    use_viewpoint_snapshot,
)
from web.services.viewpoint_blueprints import generate


def _generated_items(domain_key: str = "domain-01") -> list[dict[str, Any]]:
    """領域から生成した観点を、観点ストアが返す形に整える。

    ストアを経由せず生成物だけを見る。ここで見たいのは
    「生成した観点が QA 側の絞り込みを通過するか」であり、
    DB の読み書きは別のテストが担保している。
    """
    result = generate(domain_key)
    return [
        {
            "persistent_key": f"gen-{index}",
            "name": item["name"],
            "category": item["category"],
            "purpose": item["purpose"],
            "recommended_checks": item["recommended_checks"],
            "expected_result": item["expected_result"],
            "evidence": item["evidence"],
            "technique": item["technique"],
            "test_level": item["test_level"],
            "risk_weight": item["risk_weight"],
            "automation": item["automation"],
            "standards": item["standards"],
            "tags": item["tags"],
            "enabled": True,
            "deleted_at": None,
        }
        for index, item in enumerate(result["items"])
    ]


class TestGeneratedViewpointsAreConsumable:
    def test_qa_layer_receives_every_generated_viewpoint(self) -> None:
        """生成した観点が QA 層に全件渡ること。"""
        items = _generated_items()
        with use_viewpoint_snapshot(items):
            assert len(_load_qa_viewpoints()) == len(items)

    def test_test_design_tables_are_not_empty(self) -> None:
        """テスト設計表に観点が1件以上載ること。

        `doc_generator` は観点を `category_l2` / `quality_area_l1` の2値で
        絞り込む。生成した観点の分類がこれと噛み合わないと、表が空になる。
        表が空でも例外は出ないため、この検査が無いと気づけない。
        """
        items = _generated_items()
        with use_viewpoint_snapshot(items):
            design_rows = _viewpoints_by_type("category_l2")
            quality_rows = _viewpoints_by_type("quality_area_l1")
        assert design_rows or quality_rows, (
            "生成した観点が QA 側の分類に1件も一致しない。"
            f"生成側の分類: {sorted({i['category'] for i in items})}"
        )

    def test_viewpoint_names_reach_the_document(self) -> None:
        """観点名がドキュメントの一覧に載ること。"""
        items = _generated_items()
        with use_viewpoint_snapshot(items):
            names = _viewpoint_names("category_l2", 12) + _viewpoint_names("quality_area_l1", 12)
        assert names, "観点名が1件もドキュメントに載らない"

    @pytest.mark.parametrize(
        "field", ["purpose", "recommended_checks", "expected_result", "evidence"]
    )
    def test_expected_result_and_evidence_survive_to_qa(self, field: str) -> None:
        """期待結果・証跡を含む項目が QA 層まで残ること。

        `_legacy_viewpoint` は観点を8項目に切り詰める。そこから漏れると、
        「操作・判定点・期待結果・証跡」を作り込んでも出力には出ない。
        観点が指示書で終わるか、実行できるテストになるかの分かれ目。
        """
        items = _generated_items()
        with use_viewpoint_snapshot(items):
            delivered = _load_qa_viewpoints()
        assert delivered, "観点が1件も届いていない"
        assert any(str(vp.get(field, "")).strip() for vp in delivered), (
            f"{field} が QA 層に届いていない。届いた項目: {sorted(delivered[0].keys())}"
        )


class TestMixedTaxonomiesBothSurvive:
    """既定観点と生成観点が混ざっても、どちらも QA 文書に載ること。

    分類体系は出どころで違う（既定観点は category_l2 / quality_area_l1、
    生成観点はテストタイプ）。「求めた分類が0件なら別の分類を返す」形で
    吸収すると、既定側が1件でもあれば生成側が丸ごと消える。どちらが出るかが
    データの並びで決まる状態を作らない。
    """

    LEGACY = [
        {"persistent_key": "l1", "name": "既定観点", "category": "category_l2"},
        {"persistent_key": "l2", "name": "機能適合性", "category": "quality_area_l1"},
    ]
    GENERATED = [
        {"persistent_key": "g1", "name": "到達性：画面の網羅", "category": "機能テスト"},
        {"persistent_key": "g2", "name": "定常負荷：応答時間", "category": "性能テスト"},
    ]

    def _names(self, snapshot: list[dict[str, Any]], summary_type: str) -> list[str]:
        with use_viewpoint_snapshot(snapshot):
            return [str(vp["name"]) for vp in _viewpoints_by_type(summary_type)]

    def test_generated_viewpoints_survive_alongside_legacy(self) -> None:
        names = self._names(self.LEGACY + self.GENERATED, "category_l2")
        assert "既定観点" in names
        assert "到達性：画面の網羅" in names
        assert "定常負荷：応答時間" in names

    def test_quality_areas_include_both_taxonomies(self) -> None:
        """品質領域には、既定の領域名と生成観点のテストタイプが両方出ること。"""
        names = self._names(self.LEGACY + self.GENERATED, "quality_area_l1")
        assert "機能適合性" in names
        assert "機能テスト" in names
        assert "性能テスト" in names

    def test_quality_areas_are_not_duplicated(self) -> None:
        """同じテストタイプの観点が複数あっても、領域は1件にまとまること。"""
        many = self.GENERATED + [
            {"persistent_key": "g3", "name": "入力妥当性：境界値", "category": "機能テスト"}
        ]
        names = self._names(many, "quality_area_l1")
        assert names.count("機能テスト") == 1

    def test_legacy_only_snapshot_is_unchanged(self) -> None:
        """既定観点だけのときは、従来どおりの振る舞いであること。"""
        assert self._names(self.LEGACY, "category_l2") == ["既定観点"]
        assert self._names(self.LEGACY, "quality_area_l1") == ["機能適合性"]
