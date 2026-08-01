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


def test_list_templates_reports_metadata(templates_dir: Path) -> None:
    templates = list_templates()
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
    assert list_templates() == []


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


class TestIndustryTemplates:
    """業種別テンプレートは共通観点と併用する前提なので、重複しないこと。

    重複していると、共通＋業種を両方読み込んだ利用者が同じ確認を二度行う。
    """

    INDUSTRY_KEYS = ("industry_finance", "industry_medical", "industry_ec")

    def _names(self, data: dict) -> set[str]:
        return {i["name"] for f in data.get("folders", []) for i in f.get("items", [])}

    def test_industry_templates_exist(self) -> None:
        keys = {key for key, _ in _bundled_templates()}
        for key in self.INDUSTRY_KEYS:
            assert key in keys, f"{key} が無い"

    def test_no_overlap_with_common(self) -> None:
        """業種別が共通観点と同じ観点を持たないこと。"""
        templates = dict(_bundled_templates())
        common = self._names(templates["common_web"])
        for key in self.INDUSTRY_KEYS:
            overlap = common & self._names(templates[key])
            assert not overlap, f"{key} が共通観点と重複: {sorted(overlap)}"

    def test_industry_tag_is_present(self) -> None:
        """どの業種の観点かがタグで分かること（併用時に出所を追えるようにする）。"""
        templates = dict(_bundled_templates())
        expected = {"industry_finance": "金融", "industry_medical": "医療", "industry_ec": "EC"}
        for key, tag in expected.items():
            for folder in templates[key]["folders"]:
                for item in folder["items"]:
                    assert tag in item.get("tags", []), f"{key}: {item['name']} に「{tag}」タグが無い"

    def test_industry_risk_focus(self) -> None:
        """業種固有リスクに対応する分類を持つこと。

        共通観点で足りるものだけを並べても、業種別を分ける意味がない。
        """
        templates = dict(_bundled_templates())
        required = {
            "industry_finance": ("金額・計算", "残高・整合性", "誤送金の防止", "監査証跡"),
            "industry_medical": ("患者識別", "診療情報の保護", "処方・オーダ", "システム連携"),
            "industry_ec": ("価格・計算", "在庫管理", "決済", "注文・配送"),
        }
        for key, folders in required.items():
            actual = {f["name"] for f in templates[key]["folders"]}
            for name in folders:
                assert name in actual, f"{key} に「{name}」が無い"
