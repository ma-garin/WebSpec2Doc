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


class TestViewpointsAppearInGeneratedDocuments:
    """観点の中身が、生成される文書の本文に現れること。

    QA層に渡っただけでは届いたことにならない。`_load_qa_viewpoints()` の
    戻り値を検査するテストは、doc_generator が `.name` しか読まず
    期待結果を固定文言で上書きしていた間もずっと緑だった。
    渡した先で使われているかは、出力本文で確かめるしかない。
    """

    REPORT = {
        "screens": [
            {
                "page_id": "s1",
                "title": "トップ",
                "url": "https://x.test/",
                "forms": [],
                "buttons": [],
                "transitions": [],
            }
        ]
    }

    def _docs(self) -> tuple[str, str]:
        from web.services.qa import doc_generator

        items = [
            {"persistent_key": f"g{i}", **item}
            for i, item in enumerate(generate("domain-01")["items"])
        ]
        with use_viewpoint_snapshot(items):
            return (
                doc_generator._test_design("x.test", self.REPORT),
                doc_generator._test_cases("x.test", self.REPORT),
            )

    def test_expected_result_appears_in_test_design(self) -> None:
        design, _ = self._docs()
        expected = generate("domain-01")["items"][0]["expected_result"]
        assert expected in design, "期待結果が設計文書の本文に出ていない"

    def test_fixed_placeholder_text_is_gone(self) -> None:
        """全件を同じ文言で埋めていないこと。

        固定文言だと、どの観点でも同じ設計方針に見え、観点ごとの
        判定基準が文書から失われる。
        """
        design, _ = self._docs()
        assert "CSV観点を対象仕様へ適用し" not in design

    def test_steps_and_evidence_appear_in_test_cases(self) -> None:
        _, cases = self._docs()
        item = generate("domain-01")["items"][0]
        assert item["evidence"] in cases, "証跡がケース文書の本文に出ていない"
        assert item["expected_result"] in cases, "期待結果がケース文書の本文に出ていない"

    def test_truncation_is_disclosed(self) -> None:
        """表に載せきれなかった件数を隠さないこと。

        黙って切ると「これで全部」と読まれる。5,000観点のセットで
        12件しか載らないのに、その事実が文書から読み取れなければ、
        利用者は網羅したと誤認する。
        """
        design, cases = self._docs()
        total = len(generate("domain-01")["items"])
        for doc in (design, cases):
            assert f"このセットは {total} 観点あり" in doc
            assert "未掲載" in doc


class TestQualityAreaDoesNotCollideWithReservedWords:
    """分類の文字列が内部の予約語と一致しても、品質領域が消えないこと。

    かつては分類名（テストタイプ）を領域として流用しており、その文字列が
    `category_l2` 等の予約語と一致すると、領域の見出しが無言で消えた。
    領域は品質特性の値として持ち、文字列の一致に左右されないようにする。
    """

    LEGACY = [
        {"persistent_key": "l1", "name": "既定観点", "category": "category_l2"},
        {"persistent_key": "l2", "name": "セキュリティ", "category": "quality_area_l1"},
    ]

    def _areas(self, snapshot: list[dict[str, Any]]) -> list[str]:
        with use_viewpoint_snapshot(snapshot):
            return [str(vp["name"]) for vp in _viewpoints_by_type("quality_area_l1")]

    def test_reserved_word_as_category_still_yields_its_area(self) -> None:
        colliding = [
            {
                "persistent_key": "a1",
                "name": "予約語と衝突する観点",
                "category": "category_l2",
                "quality_area": "信頼性",
            }
        ]
        assert "信頼性" in self._areas(self.LEGACY + colliding)

    def test_quality_area_comes_from_the_characteristic_not_the_test_type(self) -> None:
        """品質領域が、テストタイプではなく品質特性であること。"""
        item = generate("domain-01")["items"][0]
        assert item["quality_area"], "品質特性が空"
        assert item["quality_area"] != item["category"], "テストタイプを領域に流用している"

    def test_generated_viewpoints_carry_quality_area_to_qa(self) -> None:
        items = [
            {"persistent_key": f"g{i}", **item}
            for i, item in enumerate(generate("domain-01")["items"][:5])
        ]
        areas = self._areas(items)
        assert areas, "品質領域が1件も出ない"
        assert all(area not in ("category_l2", "quality_area_l1") for area in areas)


class TestViewpointsDbPathResolution:
    """観点DBの場所が、そのつど環境変数から解決されること。

    モジュール定数は import 時に一度しか評価されない。テストが
    monkeypatch.setenv だけで隔離したつもりになり、黙って同じDBを
    共有する事故が起きる。
    """

    def test_change_is_reflected(self, monkeypatch: Any) -> None:
        from web.config import viewpoints_db_path

        monkeypatch.setenv("VIEWPOINTS_DB", "/tmp/first.db")
        assert str(viewpoints_db_path()) == "/tmp/first.db"
        monkeypatch.setenv("VIEWPOINTS_DB", "/tmp/second.db")
        assert str(viewpoints_db_path()) == "/tmp/second.db"

    def test_falls_back_to_default_when_unset(self, monkeypatch: Any) -> None:
        """環境変数を消したら既定へ戻ること。

        既定値に定数 VIEWPOINTS_DB を使うと、その定数自体が import 時の
        環境変数から作られているため、消しても最初の値が残る。
        """
        from web.config import DEFAULT_VIEWPOINTS_DB, viewpoints_db_path

        monkeypatch.setenv("VIEWPOINTS_DB", "/tmp/leftover.db")
        monkeypatch.delenv("VIEWPOINTS_DB")
        assert str(viewpoints_db_path()) == DEFAULT_VIEWPOINTS_DB

    def test_empty_value_is_treated_as_unset(self, monkeypatch: Any) -> None:
        """空文字は「指定なし」として扱うこと。"""
        from web.config import DEFAULT_VIEWPOINTS_DB, viewpoints_db_path

        monkeypatch.setenv("VIEWPOINTS_DB", "   ")
        assert str(viewpoints_db_path()) == DEFAULT_VIEWPOINTS_DB


class TestDocumentTablesSurviveHostileValues:
    """観点の値に表を壊す文字が含まれても、文書の表が崩れないこと。

    観点は利用者が編集でき、CSV取込でも入る。縦棒や改行を含む値が
    そのまま表へ流れると、以降の行がすべてずれて読めなくなる。
    """

    def test_pipes_and_newlines_are_escaped(self) -> None:
        from web.services.qa import doc_generator

        hostile = [
            {
                "persistent_key": "h1",
                "name": "攻撃|観点",
                "category": "category_l2",
                "expected_result": "期待|結果に縦棒\nと改行",
                "evidence": "証跡|にも縦棒",
                "recommended_checks": "操作: 手順|に縦棒\n判定点: x",
                "quality_area": "信頼性",
            }
        ]
        report = {
            "screens": [
                {
                    "page_id": "s1",
                    "title": "T",
                    "url": "https://x/",
                    "forms": [],
                    "buttons": [],
                    "transitions": [],
                }
            ]
        }
        with use_viewpoint_snapshot(hostile):
            design = doc_generator._test_design("x", report)

        header = next(line for line in design.splitlines() if line.startswith("| 観点ID"))
        row = next(line for line in design.splitlines() if "TD-VP-01" in line)
        # エスケープ済みの縦棒は列の区切りにならない
        assert row.replace("\\|", "").count("|") == header.count("|")
        assert "\n" not in row


class TestReservedCategoryDoesNotHideViewpoints:
    """分類名が予約語と一致した観点が、テスト設計・ケース表から消えないこと。

    品質領域の見出しかどうかを分類名だけで判定していたため、
    `category="quality_area_l1"` を持つ通常の観点が見出し扱いになり、
    エラーも警告もなく文書から抜け落ちていた。所属する品質領域を
    宣言している観点は、見出しではなく観点として扱う。
    """

    def test_viewpoint_with_reserved_category_still_appears_in_design_view(self) -> None:
        colliding = [
            {
                "persistent_key": "x",
                "name": "通常観点X",
                "category": "quality_area_l1",
                "quality_area": "機能性",
            }
        ]
        with use_viewpoint_snapshot(colliding):
            names = [str(vp["name"]) for vp in _viewpoints_by_type("category_l2")]
            areas = [str(vp["name"]) for vp in _viewpoints_by_type("quality_area_l1")]
        assert "通常観点X" in names, "設計ビューから消えている"
        assert areas == ["機能性"], "所属する品質領域が見出しとして出ていない"

    def test_area_heading_without_own_area_stays_a_heading(self) -> None:
        """自分の所属領域を持たない項目は、従来どおり見出しであること。"""
        headings = [
            {"persistent_key": "h", "name": "セキュリティ", "category": "quality_area_l1"}
        ]
        with use_viewpoint_snapshot(headings):
            names = [str(vp["name"]) for vp in _viewpoints_by_type("category_l2")]
            areas = [str(vp["name"]) for vp in _viewpoints_by_type("quality_area_l1")]
        assert names == []
        assert areas == ["セキュリティ"]


class TestCatalogReloadOnlyWhenChanged:
    """カタログのキャッシュを、実際に編集されたときだけ捨てること。

    毎回無条件に捨てると、キャッシュを置いた意味が消える。開発モードでは
    リクエストのたびに101定義 × 60領域の適用判定を回すことになる。
    """

    def test_unchanged_catalog_keeps_the_cache(self) -> None:
        from web.services.viewpoint_blueprints import list_domains, reload_catalogs

        list_domains()
        reload_catalogs()  # 現在の更新時刻を記録する
        assert reload_catalogs() is False

    def test_edited_catalog_drops_the_cache(self) -> None:
        """中身が変わったら捨て、変わっていなければ捨てないこと。

        更新時刻だけの変更では捨てない（中身の指紋で判定するため）。
        書き戻しや touch のたびに捨てると、キャッシュの意味が薄れる。
        """
        from pathlib import Path

        from web.services.viewpoint_blueprints import reload_catalogs

        target = Path("data/viewpoint_domains.json")
        original = target.read_bytes()
        reload_catalogs(force=True)
        try:
            target.write_bytes(
                original.replace(b'"schema_version": 1', b'"schema_version": 2', 1)
            )
            assert reload_catalogs() is True
            assert reload_catalogs() is False
        finally:
            target.write_bytes(original)
            reload_catalogs(force=True)


class TestRoleIsDecidedOnce:
    """観点の役割と所属領域を、1箇所で決めていること。

    役割を分類名から都度推測すると、推測箇所ごとに条件がずれる。実際、
    「予約語と衝突しても領域が消えない」を直した後に、逆方向（通常の観点が
    見出し扱いされて設計表から消える）が残っていた。判定を1箇所に集約し、
    以降は決まった結果だけを見る。
    """

    @pytest.mark.parametrize(
        "summary_type,quality_area,name,expected_role,expected_area",
        [
            # 所属を宣言していれば、分類名が何であれ観点として扱う
            ("機能テスト", "機能完全性", "X", "viewpoint", "機能完全性"),
            ("quality_area_l1", "機能性", "Y", "viewpoint", "機能性"),
            ("category_l2", "信頼性", "Z", "viewpoint", "信頼性"),
            # 所属を持たず分類が領域の予約語なら、それ自体が見出し
            ("quality_area_l1", "", "セキュリティ", "area_heading", "セキュリティ"),
            # 所属を持たず分類が設計の予約語なら、領域は無い
            ("category_l2", "", "既定観点", "viewpoint", ""),
            # それ以外は分類名を領域として代用する
            ("性能テスト", "", "W", "viewpoint", "性能テスト"),
        ],
    )
    def test_role_and_area_are_deterministic(
        self,
        summary_type: str,
        quality_area: str,
        name: str,
        expected_role: str,
        expected_area: str,
    ) -> None:
        from web.services.qa.helpers import _role_and_area

        assert _role_and_area(summary_type, quality_area, name) == (
            expected_role,
            expected_area,
        )

    def test_decided_role_is_carried_to_the_qa_layer(self) -> None:
        """決めた役割が観点に載って QA 層まで渡ること。"""
        snapshot = [
            {"persistent_key": "a", "name": "X", "category": "機能テスト", "quality_area": "機能完全性"}
        ]
        with use_viewpoint_snapshot(snapshot):
            delivered = _load_qa_viewpoints()[0]
        assert delivered["role"] == "viewpoint"
        assert delivered["area_label"] == "機能完全性"


class TestProviderViewpointsShareTheSameShape:
    """AI提案の観点も、ストア由来のものと同じ形を持つこと。

    役割と所属領域を持たない観点が混ざると、role だけを見る読み出し側で
    常に「観点」とみなされ、判定を1箇所に集約した意味が消える。
    集約したときに、この経路を通っていなかった。
    """

    class _Provider:
        def generate_viewpoints(self, screen_info: dict[str, Any]) -> list[dict[str, Any]]:
            return [
                {"viewpoint": "AI提案：入力の妥当性", "category": "機能テスト"},
                {"viewpoint": "AI提案：見出し扱いされうる観点", "category": "quality_area_l1"},
            ]

    REPORT = {
        "screens": [
            {
                "page_id": "s1",
                "title": "T",
                "url": "https://x/",
                "forms": [],
                "buttons": [],
                "transitions": [],
            }
        ]
    }

    def test_provider_viewpoints_carry_role_and_area(self) -> None:
        from web.services.qa import helpers

        delivered = helpers._load_qa_viewpoints("x", self.REPORT, self._Provider())
        proposed = [vp for vp in delivered if str(vp["name"]).startswith("AI提案")]
        assert proposed, "AI提案の観点が届いていない"
        for viewpoint in proposed:
            assert "role" in viewpoint, f"role を持たない: {viewpoint['name']}"
            assert "area_label" in viewpoint, f"area_label を持たない: {viewpoint['name']}"


class TestCatalogChangeDetectionUsesContent:
    """カタログの変更検知が、更新時刻ではなく中身を見ていること。

    更新時刻だけで比べると、編集後に時刻を元へ戻された変更を見逃す
    （git checkout や rsync で起こりうる）。
    """

    def test_content_change_with_restored_mtime_is_detected(self) -> None:
        import os
        from pathlib import Path

        from web.services.viewpoint_blueprints import reload_catalogs

        target = Path("data/viewpoint_domains.json")
        original = target.read_bytes()
        stat = target.stat()
        reload_catalogs(force=True)
        assert reload_catalogs() is False
        try:
            target.write_bytes(original.replace(b'"schema_version": 1', b'"schema_version": 2', 1))
            os.utime(target, (stat.st_atime, stat.st_mtime))  # 更新時刻を元へ戻す
            assert reload_catalogs() is True, "中身の変更を見逃している"
        finally:
            target.write_bytes(original)
            os.utime(target, (stat.st_atime, stat.st_mtime))
            reload_catalogs(force=True)


class TestEveryEntryPointDecidesRole:
    """観点がQA層へ入る全ての入口が、役割の決定を通ること。

    判定を1箇所に集約しても、その1箇所を通らない入口があれば意味がない。
    実際、集約した直後にAI提案の経路が漏れていた（role を持たない観点が
    混ざり、読み出し側で常に「観点」とみなされていた）。

    入口を目視で数えるのは今日4回失敗した形なので、機械的に固定する。
    入口が増えたらこのテストが落ちる。
    """

    REPORT = {
        "screens": [
            {
                "page_id": "s1",
                "title": "T",
                "url": "https://x/",
                "forms": [],
                "buttons": [],
                "transitions": [],
            }
        ]
    }
    REQUIRED_KEYS = ("role", "area_label", "expected_result", "evidence")

    class _Provider:
        def generate_viewpoints(self, screen_info: dict[str, Any]) -> list[dict[str, Any]]:
            return [{"viewpoint": "AI提案の観点", "category": "機能テスト"}]

    def _assert_shape(self, viewpoints: list[dict[str, Any]], entry: str) -> None:
        assert viewpoints, f"{entry}: 観点が届いていない"
        for viewpoint in viewpoints:
            missing = [k for k in self.REQUIRED_KEYS if k not in viewpoint]
            assert not missing, f"{entry}: {viewpoint.get('name')} に {missing} が無い"

    def test_override_entry(self) -> None:
        """AutoRun が固定したスナップショットを流す入口。"""
        items = [
            {"persistent_key": f"g{i}", **item}
            for i, item in enumerate(generate("domain-01")["items"][:3])
        ]
        with use_viewpoint_snapshot(items):
            self._assert_shape(_load_qa_viewpoints(), "override")

    def test_store_entry(self) -> None:
        """観点ストアの自動選択から読む入口。"""
        self._assert_shape(_load_qa_viewpoints(), "store")

    def test_provider_entry(self) -> None:
        """AI提案を足す入口。"""
        from web.services.qa import helpers

        delivered = helpers._load_qa_viewpoints("x", self.REPORT, self._Provider())
        self._assert_shape(delivered, "provider")

    def test_no_unaccounted_entry_point_exists(self) -> None:
        """観点を組み立てる箇所が、役割決定を通る3つの入口だけであること。

        新しい入口が足されたらここで落ちる。落ちたときは、その入口が
        _legacy_viewpoint を通っているかを確かめてから、この一覧を更新する。
        """
        import inspect

        from web.services.qa import helpers

        source = inspect.getsource(helpers._load_qa_viewpoints)
        # 入口は override / snapshot / provider の3つ。観点の組み立ては
        # いずれも _legacy_viewpoint の呼び出しでしか行わない。
        assert source.count("_legacy_viewpoint(") == 3, (
            "_load_qa_viewpoints 内の観点組み立て箇所が3つから変わった。"
            "増えた入口が _legacy_viewpoint を通っているか確認してから、"
            "この件数を更新すること。"
        )
        # 辞書リテラルで観点を直接組み立てていないこと（役割決定を迂回する形）
        assert '"summary_type":' not in source, (
            "_load_qa_viewpoints 内で観点を直接組み立てている。"
            "_legacy_viewpoint を通すこと。"
        )
