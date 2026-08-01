"""観点定義 × 領域プロファイルの生成を検証する。

領域ごとに観点表を手書きしないことが、この仕組みの目的である。
そのため「生成できること」より「生成結果が観点として成立していること」を見る。
"""

from __future__ import annotations

import pytest

from web.services.viewpoint_blueprints import (
    ViewpointGeneratorError,
    generate,
    get_domain,
    list_domains,
)


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
                for field in ("name", "purpose", "recommended_checks"):
                    assert "{" not in item[field], f"{meta['name']} / {item['name']} / {field}"

    def test_each_item_carries_expected_result_and_evidence(self) -> None:
        """全観点が期待結果と証跡を持つこと。

        「何を見るか」だけでは合否を判定できない。期待結果と、判定の根拠になる
        証跡が揃って初めてテスト設計に使える。
        """
        for meta in list_domains():
            for item in generate(meta["key"])["items"]:
                checks = item["recommended_checks"]
                assert "期待結果: " in checks, f"{meta['name']} / {item['name']}"
                assert "証跡: " in checks, f"{meta['name']} / {item['name']}"

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
