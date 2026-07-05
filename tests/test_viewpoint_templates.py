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
