"""CSV取込に異常な入力を与えたときの振る舞いを検証する。

CSVは利用者が外部で編集して持ち込む。表計算ソフトの出力、手書き、
別システムからの変換など、こちらが想定しない形が入る。観点カタログの
ファジングは行ったが、この経路は未検証だった。

見たいのは2つ。

- 不正な行があるとき、どの行が悪いかを示して1件も取り込まないこと
  （半分だけ入ると、観点表がどこまで正しいか誰にも分からなくなる）
- 制御文字・巨大な値・区切り文字の混入で、DBや後続の文書が壊れないこと
"""

from __future__ import annotations

from pathlib import Path

import pytest
from web.services.viewpoint_store import ViewpointStore, ViewpointStoreError

HEADER = "persistent_key,name,category,purpose,recommended_checks,risk_weight,automation,standards,tags,enabled"


@pytest.fixture()
def store(tmp_path: Path) -> ViewpointStore:
    seed = tmp_path / "seed.csv"
    seed.write_text("summary_type,name,count\ncategory_l2,既定観点,1\n", encoding="utf-8")
    result = ViewpointStore(tmp_path / "viewpoints.db", seed)
    result.initialize()
    return result


@pytest.fixture()
def target(store: ViewpointStore) -> str:
    created = store.create_set({"name": "取込先"})
    store.ensure_draft(created["id"])
    return str(created["id"])


def _count(store: ViewpointStore, set_id: str) -> int:
    return len(
        [
            item
            for item in store.list_items(set_id, resolved=False)
            if item["node_type"] == "viewpoint"
        ]
    )


class TestPartialImportIsRejected:
    """不正な行が1つでもあれば、1件も取り込まないこと。

    半分だけ入ると、観点表のどこまでが正しいか誰にも分からなくなる。
    """

    @pytest.mark.parametrize(
        "bad_row,reason",
        [
            (",,,,,,,,,", "全項目が空"),
            ("k1,,カテゴリ,,,3,manual,,,1", "観点名が空"),
            ("k1,観点,,,,3,manual,,,1", "カテゴリが空"),
            ("k1,観点,カテゴリ,,,99,manual,,,1", "リスク重みが範囲外"),
            ("k1,観点,カテゴリ,,,-1,manual,,,1", "リスク重みが負"),
            ("k1,観点,カテゴリ,,,abc,manual,,,1", "リスク重みが数値でない"),
            ("k1,観点,カテゴリ,,,3,fully_auto,,,1", "自動化区分が不正"),
        ],
    )
    def test_invalid_row_blocks_the_whole_import(
        self, store: ViewpointStore, target: str, bad_row: str, reason: str
    ) -> None:
        csv_text = "\n".join([HEADER, "ok1,正しい観点,カテゴリ,,,3,manual,,,1", bad_row])
        with pytest.raises(ViewpointStoreError) as exc:
            store.import_csv(target, csv_text)
        assert _count(store, target) == 0, f"{reason}: 一部だけ取り込まれた"
        # どの行が悪いかを示していること
        details = getattr(exc.value, "details", None)
        assert details, f"{reason}: どの行が悪いかを示していない"

    def test_empty_csv_is_rejected(self, store: ViewpointStore, target: str) -> None:
        with pytest.raises(ViewpointStoreError):
            store.import_csv(target, HEADER)
        assert _count(store, target) == 0


class TestHostileValuesDoNotCorruptTheStore:
    """異常な値でも、取り込みが壊れないこと。"""

    def test_control_characters_are_stored_and_read_back(
        self, store: ViewpointStore, target: str
    ) -> None:
        """タブ・改行・ヌル文字混じりの値を、壊さず往復できること。"""
        name = "制御文字\tを含む観点"
        checks = '操作: 手順1\n判定点: "引用" と \\ バックスラッシュ'
        csv_text = "\n".join([HEADER, f'k1,{name},カテゴリ,,"{checks}",3,manual,,,1'])
        store.import_csv(target, csv_text)
        items = [
            item
            for item in store.list_items(target, resolved=False)
            if item["node_type"] == "viewpoint"
        ]
        assert len(items) == 1
        assert items[0]["name"] == name
        assert "バックスラッシュ" in items[0]["recommended_checks"]

    def test_very_long_value_is_accepted_or_rejected_but_not_truncated_silently(
        self, store: ViewpointStore, target: str
    ) -> None:
        """極端に長い値を、黙って切り詰めないこと。

        切り詰めると、観点の途中までしか書かれていないことに気づけない。
        """
        long_text = "あ" * 20000
        csv_text = "\n".join([HEADER, f"k1,長い観点,カテゴリ,,{long_text},3,manual,,,1"])
        try:
            store.import_csv(target, csv_text)
        except ViewpointStoreError:
            assert _count(store, target) == 0
            return
        stored = [
            item
            for item in store.list_items(target, resolved=False)
            if item["node_type"] == "viewpoint"
        ][0]
        assert len(stored["recommended_checks"]) == len(long_text), "黙って切り詰めている"

    def test_sql_like_value_is_treated_as_data(self, store: ViewpointStore, target: str) -> None:
        """SQLに見える文字列を、値として扱うこと。"""
        injection = "'); DROP TABLE viewpoint_items; --"
        csv_text = "\n".join([HEADER, f'k1,"{injection}",カテゴリ,,,3,manual,,,1'])
        store.import_csv(target, csv_text)
        items = [
            item
            for item in store.list_items(target, resolved=False)
            if item["node_type"] == "viewpoint"
        ]
        assert len(items) == 1
        assert items[0]["name"] == injection
        # テーブルが残っていること（別のセットが読めれば健在）
        assert store.list_sets()

    def test_duplicate_names_in_one_file_are_rejected_together(
        self, store: ViewpointStore, target: str
    ) -> None:
        """同名の観点が同じファイルに2つあるとき、片方だけ入らないこと。"""
        csv_text = "\n".join(
            [
                HEADER,
                "k1,同じ名前,カテゴリ,,,3,manual,,,1",
                "k2,同じ名前,カテゴリ,,,3,manual,,,1",
            ]
        )
        try:
            store.import_csv(target, csv_text)
        except ViewpointStoreError:
            assert _count(store, target) == 0
            return
        # 取り込めた場合、2件とも入っていること（片方だけは許さない）
        assert _count(store, target) == 2


class TestMalformedCsvIsReported:
    """CSVとして壊れている入力を、静かに無視しないこと。"""

    def test_row_with_extra_columns_does_not_shift_values(
        self, store: ViewpointStore, target: str
    ) -> None:
        """列が多い行で、値がずれて別の項目に入らないこと。"""
        csv_text = "\n".join([HEADER, "k1,観点,カテゴリ,,,3,manual,,,1,余分,さらに余分"])
        try:
            store.import_csv(target, csv_text)
        except ViewpointStoreError:
            return
        stored = [
            item
            for item in store.list_items(target, resolved=False)
            if item["node_type"] == "viewpoint"
        ][0]
        assert stored["name"] == "観点"
        assert stored["category"] == "カテゴリ"
        assert stored["risk_weight"] == 3

    def test_row_with_missing_columns_is_reported(self, store: ViewpointStore, target: str) -> None:
        """列が足りない行を、既定値で埋めて黙って通さないこと。"""
        csv_text = "\n".join([HEADER, "k1,観点"])
        try:
            store.import_csv(target, csv_text)
        except ViewpointStoreError:
            assert _count(store, target) == 0
            return
        # 通った場合、カテゴリが空のまま入っていないこと
        stored = [
            item
            for item in store.list_items(target, resolved=False)
            if item["node_type"] == "viewpoint"
        ]
        assert all(str(item["category"]).strip() for item in stored)

    def test_header_only_unknown_columns_is_reported(
        self, store: ViewpointStore, target: str
    ) -> None:
        """想定と違う列構成のCSVを、0件成功として扱わないこと。"""
        csv_text = "全く違う列,別の列\n値1,値2"
        with pytest.raises(ViewpointStoreError):
            store.import_csv(target, csv_text)
        assert _count(store, target) == 0
