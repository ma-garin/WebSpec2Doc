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

    @pytest.mark.parametrize("field", ["purpose", "recommended_checks"])
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
