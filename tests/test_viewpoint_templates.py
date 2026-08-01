from __future__ import annotations

import json
from pathlib import Path

import pytest
import web.services.viewpoint_templates as viewpoint_templates
from web.services.viewpoint_store import ViewpointStore
from web.services.viewpoint_templates import (
    TemplateNotFoundError,
    apply_template,
    list_templates,
)


@pytest.fixture()
def templates_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "templates"
    directory.mkdir()
    (directory / "sample.json").write_text(
        json.dumps(
            {
                "name": "サンプル観点セット",
                "description": "テスト用の最小プリセット。",
                "folders": [
                    {
                        "name": "フォルダA",
                        "items": [
                            {
                                "name": "観点1",
                                "category": "カテゴリA",
                                "purpose": "目的1",
                                "recommended_checks": "確認事項1",
                                "risk_weight": 3,
                                "automation": "manual",
                                "standards": "サンプル標準",
                                "tags": ["tag1"],
                            },
                            {
                                "name": "観点2",
                                "category": "カテゴリA",
                                "automation": "automated",
                            },
                        ],
                    },
                    {"name": "フォルダB（空）", "items": []},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (directory / "broken.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(viewpoint_templates, "VIEWPOINT_TEMPLATES_DIR", directory)
    return directory


@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ViewpointStore:
    seed = tmp_path / "seed.csv"
    seed.write_text("summary_type,name,count\ncategory_l2,既定観点,1\n", encoding="utf-8")
    result = ViewpointStore(tmp_path / "viewpoints.db", seed)
    result.initialize()
    monkeypatch.setattr(viewpoint_templates, "get_viewpoint_store", lambda: result)
    return result


def _file_entries(templates: list[dict[str, object]]) -> list[dict[str, object]]:
    """ファイル由来のテンプレートだけを取り出す。

    一覧には領域から生成する分（60件）も混ざる。ここで見たいのは
    ディレクトリの読み取りとメタ情報の組み立てなので、出どころで絞る。
    """
    return [t for t in templates if t["source"] == "file"]


def test_list_templates_reports_metadata(templates_dir: Path) -> None:
    templates = _file_entries(list_templates())
    assert len(templates) == 1  # broken.json は不正形式のためスキップされる
    entry = templates[0]
    assert entry["key"] == "sample"
    assert entry["name"] == "サンプル観点セット"
    assert entry["folder_count"] == 2
    assert entry["item_count"] == 2


def test_list_templates_empty_dir_returns_empty_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "empty"
    monkeypatch.setattr(viewpoint_templates, "VIEWPOINT_TEMPLATES_DIR", empty)
    assert _file_entries(list_templates()) == []


def test_list_templates_includes_generated_domains() -> None:
    """領域から生成する分が一覧に出ること。

    ここが出ないと、60領域を用意しても利用者は選べない。
    """
    domains = [t for t in list_templates() if t["source"] == "domain"]
    assert len(domains) == 60
    assert all(t["item_count"] > 0 for t in domains)


def test_apply_template_creates_folders_and_items(
    templates_dir: Path, store: ViewpointStore
) -> None:
    created_set = store.create_set({"name": "適用先セット"})
    result = apply_template(created_set["id"], "sample")

    assert result["created_folders"] == 2
    assert result["created_items"] == 2
    assert result["template_name"] == "サンプル観点セット"

    tree = store.get_tree(created_set["id"])
    folder_names = {node["name"] for node in tree if node["node_type"] == "folder"}
    assert folder_names == {"フォルダA", "フォルダB（空）"}
    item_names = {node["name"] for node in tree if node["node_type"] == "viewpoint"}
    assert item_names == {"観点1", "観点2"}

    child_a = next(node for node in tree if node["name"] == "観点1")
    assert child_a["category"] == "カテゴリA"
    assert child_a["risk_weight"] == 3


def test_apply_template_unknown_key_raises(store: ViewpointStore, templates_dir: Path) -> None:
    created_set = store.create_set({"name": "適用先セット"})
    with pytest.raises(TemplateNotFoundError):
        apply_template(created_set["id"], "does-not-exist")


def test_load_broken_template_raises(templates_dir: Path) -> None:
    from web.services.viewpoint_templates import _load_template_file

    with pytest.raises(TemplateNotFoundError):
        _load_template_file("broken")


# ---------- 同梱テンプレートの妥当性（data/viewpoint_templates/*.json） ----------


def _bundled_templates() -> list[tuple[str, dict]]:
    """リポジトリに同梱している観点テンプレートを読み込む。"""
    import json

    root = Path(__file__).resolve().parent.parent / "data" / "viewpoint_templates"
    return [(p.stem, json.loads(p.read_text(encoding="utf-8"))) for p in sorted(root.glob("*.json"))]


class TestBundledTemplates:
    """同梱テンプレートが投入可能な形であることを、投入前に静的に確かめる。

    apply_template は create_item を通すため、必須項目が欠けていると
    実行時に 400 で落ちる。実際に「category 欠落」で落ちたことがあるので、
    ファイル側で止める。
    """

    def test_required_fields_present(self) -> None:
        """name と category は create_item の必須項目。"""
        for key, data in _bundled_templates():
            for folder in data.get("folders", []):
                for item in folder.get("items", []):
                    assert item.get("name"), f"{key}: name が空"
                    assert item.get("category"), f"{key}: {item.get('name')} の category が空"

    def test_automation_values_are_valid(self) -> None:
        """automation は許容値のみ（不正値は正規化で落ちる）。"""
        from web.services.viewpoint_store import AUTOMATION_VALUES

        for key, data in _bundled_templates():
            for folder in data.get("folders", []):
                for item in folder.get("items", []):
                    value = item.get("automation", "manual")
                    assert value in AUTOMATION_VALUES, f"{key}: {item['name']} の automation={value}"

    def test_no_duplicate_names_within_template(self) -> None:
        """同一テンプレート内で観点名が重複しないこと。

        重複していると、利用者が同じ確認を二度行うことになる。
        """
        for key, data in _bundled_templates():
            names = [i["name"] for f in data.get("folders", []) for i in f.get("items", [])]
            duplicated = {n for n in names if names.count(n) > 1}
            assert not duplicated, f"{key}: 観点名が重複 {duplicated}"

    def test_common_web_covers_analyzable_surfaces(self) -> None:
        """共通観点が、解析で得られる対象を一通り覆っていること。

        画面・フォーム・遷移・API といった WebSpec2Doc が実際に抽出する
        対象に対応していないと、観点があっても確認に使えない。
        """
        data = dict(_bundled_templates())["common_web"]
        folders = {f["name"] for f in data["folders"]}
        for required in ("画面表示", "入力フォーム", "画面遷移", "API・連携", "認証・認可"):
            assert required in folders, f"共通観点に「{required}」が無い"

    def test_common_web_has_enough_items(self) -> None:
        """実務で使える規模（250件）を保つ。減った場合は意図を確認する。"""
        data = dict(_bundled_templates())["common_web"]
        total = sum(len(f["items"]) for f in data["folders"])
        assert total >= 250, f"共通観点が {total} 件に減っている"


class TestCreateSetFromTemplate:
    """テンプレートから観点セットを直接作れること。

    既存の apply_template は「開いているセットに足す」動作で、テンプレートを
    用意してもセット一覧には現れなかった。使い始めるまでに
    「セットを作る → テンプレートを選ぶ」の2手が要り、存在に気づけなかった。
    """

    def test_creates_a_new_set(self, store: ViewpointStore, templates_dir: Path) -> None:
        from web.services.viewpoint_templates import create_set_from_template

        before = len(store.list_sets())
        result = create_set_from_template("sample")
        assert len(store.list_sets()) == before + 1
        assert result["set"]["name"]
        assert result["created_items"] >= 1

    def test_uses_template_name_by_default(self, store: ViewpointStore, templates_dir: Path) -> None:
        from web.services.viewpoint_templates import _load_template_file, create_set_from_template

        expected = _load_template_file("sample")["name"]
        result = create_set_from_template("sample")
        assert result["set"]["name"] == expected

    def test_custom_name_wins(self, store: ViewpointStore, templates_dir: Path) -> None:
        from web.services.viewpoint_templates import create_set_from_template

        result = create_set_from_template("sample", "自分でつけた名前")
        assert result["set"]["name"] == "自分でつけた名前"

    def test_unknown_template_does_not_create_set(
        self, store: ViewpointStore, templates_dir: Path
    ) -> None:
        """存在しないキーでセットだけ作られる、を起こさない。"""
        from web.services.viewpoint_templates import create_set_from_template

        before = len(store.list_sets())
        with pytest.raises(TemplateNotFoundError):
            create_set_from_template("does-not-exist")
        assert len(store.list_sets()) == before
