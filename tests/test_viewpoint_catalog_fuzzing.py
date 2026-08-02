"""観点カタログに異常値が混ざったときの振る舞いを検証する。

これまでの検証は「今のデータは壊れていない」ことの確認に留まっており、
「壊れたデータを与えたらどうなるか」を見ていなかった。カタログは
人が編集するJSONで、キーの打ち間違い・型の取り違え・値の欠落は起こる。

方針は2つ。

- 生成が続行できない不備は、どの定義が悪いかを名指しして落とす
- 壊れたデータを黙って既定値へ倒し、それらしい観点を作らない

「気づかないまま不正な観点表が出る」のが最も害が大きい。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from web.services.viewpoint_blueprints import (
    ViewpointGeneratorError,
    generate,
    list_domains,
    reload_catalogs,
)

BLUEPRINTS = Path("data/viewpoint_blueprints.json")
DOMAINS = Path("data/viewpoint_domains.json")


@contextmanager
def _mutated(path: Path, mutate: Any) -> Iterator[None]:
    """カタログを一時的に書き換える。終了時に必ず元へ戻す。"""
    original = path.read_bytes()
    try:
        data = json.loads(original.decode("utf-8"))
        mutate(data)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        reload_catalogs(force=True)
        yield
    finally:
        path.write_bytes(original)
        reload_catalogs(force=True)


class TestBrokenBlueprintIsRejected:
    """観点定義が壊れていたら、どれが悪いかを名指しして落ちること。"""

    @pytest.mark.parametrize(
        "field,value",
        [
            ("automation_level", None),
            ("automation_level", "auto"),
            ("automation_level", 1),
            ("automation_level", ""),
        ],
    )
    def test_invalid_automation_level_names_the_definition(
        self, field: str, value: Any
    ) -> None:
        def mutate(data: dict[str, Any]) -> None:
            data["blueprints"][0][field] = value

        with _mutated(BLUEPRINTS, mutate):
            with pytest.raises(ViewpointGeneratorError) as exc:
                generate("domain-01")
            assert "F01" in str(exc.value), "どの定義が不正かを示していない"

    def test_missing_capabilities_is_not_silently_applied(self) -> None:
        """能力タグが欠けた定義を、黙って全領域へ適用しないこと。"""

        def mutate(data: dict[str, Any]) -> None:
            del data["blueprints"][0]["capabilities"]

        with _mutated(BLUEPRINTS, mutate):
            with pytest.raises((ViewpointGeneratorError, KeyError, TypeError)):
                generate("domain-01")

    def test_unknown_placeholder_is_not_swallowed(self) -> None:
        """領域プロファイルに無いプレースホルダを、黙って空文字にしないこと。

        黙って埋めると「何を確認するのか書かれていない観点」が出力に並ぶ。
        """

        def mutate(data: dict[str, Any]) -> None:
            data["blueprints"][0]["expected"] = "{存在しない項目}が一致する"

        with _mutated(BLUEPRINTS, mutate):
            with pytest.raises((KeyError, ViewpointGeneratorError)):
                generate("domain-01")

    def test_unknown_test_level_is_not_swallowed(self) -> None:
        """定義されていないテストレベルを、黙って無視しないこと。"""

        def mutate(data: dict[str, Any]) -> None:
            data["blueprints"][0]["levels"] = ["架空テスト"]

        with _mutated(BLUEPRINTS, mutate):
            with pytest.raises((KeyError, ViewpointGeneratorError)):
                generate("domain-01")


class TestBrokenDomainIsRejected:
    """領域プロファイルが壊れていたら、意味の通らない観点を作らないこと。"""

    def test_missing_vocabulary_is_not_replaced_by_placeholder_text(self) -> None:
        """語彙が欠けた領域で、プレースホルダのまま観点を作らないこと。"""

        def mutate(data: dict[str, Any]) -> None:
            del data["domains"][0]["primary_flow"]

        with _mutated(DOMAINS, mutate):
            with pytest.raises((KeyError, ViewpointGeneratorError)):
                generate("domain-01")

    def test_capabilities_of_wrong_type_is_rejected(self) -> None:
        """能力タグが配列でなければ、観点0件のセットを黙って作らないこと。

        文字列を集合として扱うと1文字ずつに分解され、`{"c","o","r","e"}`
        との包含判定になる。実測では適用定義が 89 → 0 になり、エラーも
        警告もないまま「観点が1件も無いセット」ができる。
        利用者は打ち間違いに気づけない。
        """

        def mutate(data: dict[str, Any]) -> None:
            data["domains"][0]["capabilities"] = "core"

        with _mutated(DOMAINS, mutate):
            with pytest.raises(ViewpointGeneratorError) as exc:
                generate("domain-01")
            assert "capabilities" in str(exc.value)

    def test_empty_domain_list_is_reported(self) -> None:
        """領域が空なら、0領域として静かに成功しないこと。"""

        def mutate(data: dict[str, Any]) -> None:
            data["domains"] = []

        with _mutated(DOMAINS, mutate):
            assert list_domains() == []
            with pytest.raises(ViewpointGeneratorError):
                generate("domain-01")


class TestCatalogIsRestoredAfterFuzzing:
    """ファジングの後、カタログが元通りであること。

    検証がデータを壊したまま終わると、以降の全テストが無意味になる。
    """

    def test_catalog_is_intact(self) -> None:
        assert len(list_domains()) == 60
        result = generate("domain-01")
        assert result["items"]
        assert all("{" not in item["expected_result"] for item in result["items"])
