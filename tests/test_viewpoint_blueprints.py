"""観点定義 × 領域プロファイルの生成を検証する。

領域ごとに観点表を手書きしないことが、この仕組みの目的である。
そのため「生成できること」より「生成結果が観点として成立していること」を見る。
"""

from __future__ import annotations

import pytest

from web.services.viewpoint_blueprints import (
    ViewpointGeneratorError,
    _blueprints,
    _evidence_by_id,
    generate,
    get_domain,
    list_domains,
)


def _searchable(*fields: str, lower: bool = False) -> str:
    """観点定義の指定フィールドを繋いだ検索用文字列を返す。

    体系の網羅を確かめるテストは「その語が定義群のどこかに現れるか」を見る。
    クラスごとに同じ連結処理を書くと、対象フィールドがずれて測る範囲が
    変わっても気づけない。1箇所に集約する。
    """
    text = " | ".join(
        "|".join(str(b.get(f, "")) for f in fields) for b in _blueprints()["blueprints"]
    )
    return text.lower() if lower else text


class TestDomainCatalog:
    def test_all_domains_have_capabilities_and_vocabulary(self) -> None:
        """全領域が能力タグと語彙を持つこと。

        どちらか一方でも欠けると、適用判定かプレースホルダ展開のどちらかが
        黙って壊れ、意味の通らない観点が生成される。
        """
        required = [
            "primary_object",
            "primary_flow",
            "external_interface",
            "data_asset",
            "scheduled_process",
            "output_artifact",
            "critical_risk",
        ]
        for meta in list_domains():
            domain = get_domain(meta["key"])
            assert domain["capabilities"], f"{meta['name']}: 能力タグが空"
            for field in required:
                assert str(domain.get(field, "")).strip(), f"{meta['name']}: {field} が空"

    def test_unknown_domain_is_rejected(self) -> None:
        with pytest.raises(ViewpointGeneratorError):
            generate("domain-999")

    def test_listed_item_count_matches_generated(self) -> None:
        """一覧に出る件数と、実際に生成される件数が一致すること。

        ここがずれると「44観点入ります」と表示して43件しか入らない状態になり、
        利用者は差分に気づけない。
        """
        for meta in list_domains():
            assert meta["item_count"] == len(generate(meta["key"])["items"]), meta["name"]


class TestGeneratedViewpoints:
    def test_names_are_unique_within_domain(self) -> None:
        """同一領域内で観点名が重複しないこと。

        重複していると公開時に弾かれ、セットとして使えない。
        """
        for meta in list_domains():
            names = [item["name"] for item in generate(meta["key"])["items"]]
            duplicated = {n for n in names if names.count(n) > 1}
            assert not duplicated, f"{meta['name']}: {sorted(duplicated)}"

    def test_no_unexpanded_placeholder_remains(self) -> None:
        """プレースホルダが展開されずに残らないこと。

        `{primary_object}` のまま出ると、観点が何を指しているか読めない。
        """
        for meta in list_domains():
            for item in generate(meta["key"])["items"]:
                for field in ("name", "purpose", "recommended_checks", "expected_result", "evidence"):
                    assert "{" not in item[field], f"{meta['name']} / {item['name']} / {field}"

    def test_each_item_carries_expected_result_and_evidence(self) -> None:
        """全観点が期待結果と証跡を持つこと。

        「何を見るか」だけでは合否を判定できない。期待結果と、判定の根拠になる
        証跡が揃って初めてテスト設計に使える。
        """
        for meta in list_domains():
            for item in generate(meta["key"])["items"]:
                assert item["expected_result"].strip(), f"{meta['name']} / {item['name']}"
                assert item["evidence"].strip(), f"{meta['name']} / {item['name']}"

    def test_items_are_placed_in_declared_folders(self) -> None:
        for meta in list_domains():
            result = generate(meta["key"])
            folders = set(result["folders"])
            for item in result["items"]:
                assert item["folder"] in folders, f"{meta['name']} / {item['name']}"

    def test_risk_weight_and_automation_are_within_store_constraints(self) -> None:
        """観点ストアが受け付ける値域に収まること。

        外れると create_item が 400 を返し、セット作成が途中で止まる。
        """
        for meta in list_domains():
            for item in generate(meta["key"])["items"]:
                assert 1 <= item["risk_weight"] <= 5
                assert item["automation"] in {"manual", "semi_automated", "automated"}


class TestApplicability:
    def test_exclusions_are_recorded_not_silently_dropped(self) -> None:
        """適用しなかった観点定義を、除外として記録すること。

        件数合わせで消すのと、適用外だと判断して記録するのは別物である。
        記録がないと「なぜこの領域にこの観点が無いのか」を後から説明できない。
        """
        total = list_domains()[0]["total_definitions"]
        for meta in list_domains():
            result = generate(meta["key"])
            assert meta["applied_definitions"] + len(result["excluded_definitions"]) == total

    def test_no_ui_domain_excludes_ui_definitions(self) -> None:
        """画面を持たない領域に、画面前提の観点が入らないこと。"""
        database = next(m for m in list_domains() if m["name"] == "データベース")
        assert "ui" not in database["capabilities"]
        assert "accessibility" not in database["capabilities"]

    def test_money_domain_includes_money_definitions(self) -> None:
        """金額を扱う領域に、金額固有の観点が入ること。"""
        finance = next(m for m in list_domains() if m["name"] == "金融")
        assert "money" in finance["capabilities"]


class TestGeneratedSetRecordsApplicability:
    """生成したセットが、適用と除外の記録を持つこと。

    観点表に或る観点が無いとき、意図的な除外なのか作り忘れなのかを
    後から説明できないと、抜けを指摘されても答えられない。
    """

    def test_set_carries_applied_and_excluded_definitions(self) -> None:
        from web.services.viewpoint_store import get_viewpoint_store
        from web.services.viewpoint_templates import create_set_from_template

        store = get_viewpoint_store()
        created = create_set_from_template("domain-16", "【テスト】適用可否")
        try:
            record = store.get_set(created["set"]["id"])["applicability"]
            assert record["source"] == "domain_blueprint"
            assert record["domain_key"] == "domain-16"
            total = list_domains()[0]["total_definitions"]
            assert len(record["applied"]) + len(record["excluded"]) == total
            # データベース領域は画面を持たないので、画面前提の観点が除外される
            assert {"U01", "X01", "X02"}.issubset(set(record["excluded"]))
        finally:
            store.delete_set(created["set"]["id"])


class TestStandardCoverage:
    """参考ページに掲げた標準を、項目単位で観点が覆っていること。

    「その標準に触れている観点が1件でもあるか」の 0/1 判定では、
    ISO 25010 の8特性のうち1つしか見ていなくても満点になる。
    標準の中の項目を単位にして測る。
    """

    def _haystack(self) -> str:
        return _searchable("theme", "kind", "technique", "quality", "test_type", lower=True)

    @pytest.mark.parametrize(
        "characteristic",
        [
            "機能適合性", "性能効率性", "互換性", "相互作用性", "信頼性",
            "セキュリティ", "保守性", "柔軟性", "安全性",
        ],
    )
    def test_iso25010_characteristics_are_covered(self, characteristic: str) -> None:
        assert characteristic.lower() in self._haystack()

    @pytest.mark.parametrize("principle", ["知覚可能", "操作可能", "理解可能", "堅牢"])
    def test_wcag_principles_are_covered(self, principle: str) -> None:
        assert principle.lower() in self._haystack()

    @pytest.mark.parametrize(
        "category",
        [
            "アクセス制御", "インジェクション", "安全でない設計", "設定不備",
            "脆弱なコンポーネント", "認証の失敗", "完全性の失敗", "ログと監視", "SSRF",
        ],
    )
    def test_owasp_categories_are_covered(self, category: str) -> None:
        assert category.lower() in self._haystack()

    @pytest.mark.parametrize(
        "technique",
        [
            "同値分割", "境界値分析", "デシジョンテーブル", "状態遷移テスト",
            "ユースケーステスト", "ペアワイズ", "エラー推測",
        ],
    )
    def test_istqb_techniques_are_covered(self, technique: str) -> None:
        assert technique.lower() in self._haystack()


class TestPipelineStageCoverage:
    """URL→画面遷移図→テスト設計→テストケース→実行→レポートの各工程に、
    対応する観点定義があること。

    観点はこの製品のエンジンなので、製品が生成する成果物そのものを
    検証する観点が無いと、生成物の正しさを誰も確かめない。
    """

    STAGES = {
        "URL・クロール": ["WE01", "WE02"],
        "画面遷移図": ["WE03"],
        "テスト設計": ["WQ02", "WQ03"],
        "テストケース": ["WE05"],
        "テスト実行": ["WE06", "WE07"],
        "レポート・証跡": ["WE08", "WE09"],
        "追跡性": ["WE04"],
    }

    @pytest.mark.parametrize("stage,identifiers", list(STAGES.items()))
    def test_stage_has_dedicated_definitions(self, stage: str, identifiers: list[str]) -> None:
        available = {b["identifier"] for b in _blueprints()["blueprints"]}
        missing = [i for i in identifiers if i not in available]
        assert not missing, f"{stage}: {missing} が無い"


class TestQualityManagementCoverage:
    """品質保証・品質マネジメントの体系が、観点の根拠として使われていること。

    移植元の定義は製品品質（ISO 25010）とテスト技法（29119-4）に寄っており、
    「正しく作ったか」は問えても「正しいものを作ったか」を問う観点が無かった。
    ISO 9000 系・要求工学・検証と妥当性確認・レビューの体系を持たないまま
    観点を名乗ると、テストの網羅性を品質保証の網羅性と取り違える。
    """

    def _referenced_documents(self) -> str:
        evidence = _evidence_by_id()
        used = {s for b in _blueprints()["blueprints"] for s in b["sources"]}
        return " | ".join(str(evidence.get(s, {}).get("document", "")) for s in used).lower()

    @pytest.mark.parametrize(
        "standard",
        [
            "ISO 9000", "ISO 9001", "90003", "19011", "12207",
            "29148", "1012", "1028", "33002", "31000", "25019", "20000",
        ],
    )
    def test_quality_management_standard_is_referenced(self, standard: str) -> None:
        assert standard.lower() in self._referenced_documents()

    @pytest.mark.parametrize(
        "theme",
        [
            "妥当性確認", "要求の検証可能性", "要求集合の健全性", "レビュー",
            "不適合の処理", "リスク対応", "変更とリリース", "利用時品質",
            "客観的証拠", "検証と妥当性確認の分離", "構成管理", "ソフトウェア品質保証",
        ],
    )
    def test_quality_management_theme_exists(self, theme: str) -> None:
        assert theme in {b["theme"] for b in _blueprints()["blueprints"]}

    def test_every_referenced_source_exists_in_catalog(self) -> None:
        """観点が参照する出典が、すべてカタログに実在すること。

        存在しない出典IDを参照していると、根拠のリンクが切れたまま
        「規格に準拠」と表示され、利用者が確かめられない。
        """
        evidence = _evidence_by_id()
        missing = sorted(
            {s for b in _blueprints()["blueprints"] for s in b["sources"] if s not in evidence}
        )
        assert not missing, f"カタログに無い出典を参照: {missing}"


class TestQualityModelCoverage:
    """品質モデルの層と、顧客満足への写像が観点に含まれること。

    既存の定義は「動かしたときに仕様どおりか」に寄っていた。静的な作りを見る
    内部品質が無いと変更に耐えられるかを問えず、狩野モデルの分類が無いと
    全ての品質要求を同じ重みで扱い、当たり前品質を欠いたまま魅力的品質に
    工数を割く判断が起きる。

    「外部品質」は語として持たない。ISO/IEC 25010:2023 で内部/外部の区別は
    廃され製品品質へ統合されたため、機能・性能・セキュリティ等の既存定義が
    実質的にそれにあたる。層の名前を後付けしない。
    """

    def _strict(self) -> str:
        return _searchable("theme", "kind", "quality")

    @pytest.mark.parametrize("layer", ["内部品質", "利用時品質"])
    def test_quality_layers_are_present(self, layer: str) -> None:
        assert layer in self._strict()

    @pytest.mark.parametrize(
        "classification",
        ["当たり前品質", "一元的品質", "魅力的品質", "逆品質", "無関心品質"],
    )
    def test_kano_classifications_are_present(self, classification: str) -> None:
        assert classification in self._strict()

    @pytest.mark.parametrize(
        "sub", ["モジュール性", "再利用性", "解析性", "修正性", "試験性"]
    )
    def test_maintainability_subcharacteristics_are_present(self, sub: str) -> None:
        assert sub in self._strict()

    def test_must_be_quality_outranks_attractive_quality(self) -> None:
        """当たり前品質の観点が、魅力的品質より高い優先度を持つこと。

        当たり前品質は満たしても満足が上がらないため後回しにされやすいが、
        1つでも欠けると利用が止まる。優先度が逆転していると、観点表が
        誤った工数配分を誘導する。
        """
        by_theme = {b["theme"]: b for b in _blueprints()["blueprints"]}
        order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        assert order[by_theme["当たり前品質"]["priority"]] < order[by_theme["魅力的品質"]["priority"]]


class TestAutomationReflectsDefinition:
    """自動化区分が、観点定義の記述から決まること。

    生成器は長らく全件を semi_automated に固定しており、定義側の記述は
    一度も使われていなかった。そのため「この製品はクロールのみを行うため
    実行できない」観点まで半自動と表示され、実行できるかのように読めた。
    実際には手作業が要るものを自動と表示するほうが、逆より害が大きい。
    """

    def test_not_every_item_has_the_same_automation(self) -> None:
        """全件が同じ値に潰れていないこと。

        ここが1種類なら、定義側の記述が捨てられている。
        """
        values = {item["automation"] for item in generate("domain-13")["items"]}
        assert len(values) > 1, f"自動化区分が1種類しかない: {values}"

    def test_unexecutable_viewpoints_are_marked_manual(self) -> None:
        """この製品で実行できない観点が、手動として扱われること。"""
        for item in generate("domain-13")["items"]:
            if "実行できない" in item["recommended_checks"]:
                assert item["automation"] == "manual", item["name"]

    def test_crawl_checkable_viewpoints_are_marked_automated(self) -> None:
        """クロール結果から検査できる観点が、自動として扱われること。"""
        found = False
        for item in generate("domain-13")["items"]:
            if "クロール結果から自動検査できる" in item["recommended_checks"]:
                assert item["automation"] == "automated", item["name"]
                found = True
        assert found, "クロールで検査できる観点が1件も無い"

    def test_execution_means_is_carried_into_the_item(self) -> None:
        """実施手段の但し書きが観点に残ること。

        ストアの3値では「なぜ手動なのか」が伝わらない。リポジトリ参照が
        要るのか、単に人の判断が要るのかで、利用者の次の行動が変わる。
        """
        for meta in list_domains():
            for item in generate(meta["key"])["items"]:
                assert "実施手段: " in item["recommended_checks"], item["name"]

    def test_unknown_automation_text_falls_back_to_manual(self) -> None:
        """判別できない記述は手動として扱うこと。"""
        from web.services.viewpoint_blueprints import _automation_of

        assert _automation_of({"automation": "見たことのない書き方"}) == "manual"
        assert _automation_of({}) == "manual"
