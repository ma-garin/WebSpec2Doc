from __future__ import annotations

from pathlib import Path

import pytest
import web.routes.viewpoints as viewpoints_routes
import web.services.viewpoint_templates as viewpoint_templates
from flask import Flask
from web.services.viewpoint_store import ViewpointStore


@pytest.fixture()
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    seed = tmp_path / "seed.csv"
    seed.write_text("summary_type,name,count\ncategory_l2,既定観点,1\n", encoding="utf-8")
    store = ViewpointStore(tmp_path / "viewpoints.db", seed)
    store.initialize()
    monkeypatch.setattr(viewpoints_routes, "get_viewpoint_store", lambda: store)
    monkeypatch.setattr(viewpoints_routes, "has_openai_api_key", lambda: False)
    monkeypatch.setattr(viewpoint_templates, "get_viewpoint_store", lambda: store)
    app = Flask(__name__)
    app.register_blueprint(viewpoints_routes.bp)
    return app.test_client(), store


def test_viewpoint_crud_publish_and_conflict(api) -> None:
    client, store = api
    created = client.post("/api/viewpoint-sets", json={"name": "APIセット"})
    assert created.status_code == 201
    set_id = created.get_json()["set"]["id"]
    version = store.get_version(set_id, status="draft")

    item_response = client.post(
        f"/api/viewpoint-sets/{set_id}/versions/{version['version_number']}/items",
        json={"name": "認証切れ", "category": "認証", "automation": "manual"},
    )
    assert item_response.status_code == 201
    item = item_response.get_json()["item"]

    updated = client.patch(
        f"/api/viewpoint-items/{item['id']}",
        json={"revision": item["revision"], "name": "認証切れ時の遷移"},
    )
    assert updated.status_code == 200

    conflict = client.patch(
        f"/api/viewpoint-items/{item['id']}",
        json={"revision": item["revision"], "name": "古い更新"},
    )
    assert conflict.status_code == 409
    assert "current" in conflict.get_json()["details"]

    version = store.get_version(set_id, version["version_number"])
    published = client.post(
        f"/api/viewpoint-sets/{set_id}/versions/{version['version_number']}/publish",
        json={"revision": version["revision"], "change_reason": "APIテスト"},
    )
    assert published.status_code == 200
    assert published.get_json()["version"]["status"] == "published"


def test_ai_proposal_is_unavailable_without_key(api) -> None:
    client, store = api
    set_id = store.list_sets()[0]["id"]

    response = client.post(f"/api/viewpoint-sets/{set_id}/proposals", json={"notes": "EC"})

    assert response.status_code == 503
    assert "OpenAI設定" in response.get_json()["error"]


def test_selection_endpoint_returns_published_snapshot(api) -> None:
    client, _store = api

    response = client.get("/api/viewpoint-selection?url=https://example.com")

    assert response.status_code == 200
    data = response.get_json()
    assert data["recommended"]["set_name"] == "WebSpec2Doc標準観点"
    assert data["recommended"]["viewpoint_count"] == 1


def _new_set(client) -> str:
    """テスト用に新規セット（下書き版付き）を作成してset_idを返す。"""
    resp = client.post("/api/viewpoint-sets", json={"name": "テストセット"})
    assert resp.status_code == 201
    return resp.get_json()["set"]["id"]


def test_tree_and_folder_crud(api) -> None:
    client, store = api
    set_id = _new_set(client)

    # ツリー取得（初期状態：フォルダなし）
    tree_resp = client.get(f"/api/viewpoint-sets/{set_id}/tree")
    assert tree_resp.status_code == 200
    nodes = tree_resp.get_json()["nodes"]
    assert all(n["node_type"] != "folder" for n in nodes)

    # フォルダ作成
    folder_resp = client.post(
        f"/api/viewpoint-sets/{set_id}/folders",
        json={"name": "認証"},
    )
    assert folder_resp.status_code == 201
    folder = folder_resp.get_json()["item"]
    assert folder["node_type"] == "folder"
    assert folder["name"] == "認証"

    # ツリー再取得（フォルダが含まれる）
    tree_resp2 = client.get(f"/api/viewpoint-sets/{set_id}/tree")
    nodes2 = tree_resp2.get_json()["nodes"]
    folder_nodes = [n for n in nodes2 if n["node_type"] == "folder"]
    assert len(folder_nodes) == 1
    assert folder_nodes[0]["name"] == "認証"

    # 観点を作成してフォルダに移動
    version = store.get_version(set_id, status="draft")
    item_resp = client.post(
        f"/api/viewpoint-sets/{set_id}/versions/{version['version_number']}/items",
        json={"name": "ログインテスト", "category": "認証", "automation": "manual"},
    )
    assert item_resp.status_code == 201
    item_id = item_resp.get_json()["item"]["id"]

    move_resp = client.patch(
        f"/api/viewpoint-items/{item_id}/move",
        json={"parent_key": folder["persistent_key"]},
    )
    assert move_resp.status_code == 200
    assert move_resp.get_json()["item"]["parent_key"] == folder["persistent_key"]

    # フォルダ削除
    del_resp = client.delete(f"/api/viewpoint-folders/{folder['id']}")
    assert del_resp.status_code == 200
    assert del_resp.get_json()["undo_available"] is True

    # 削除後はフォルダが消える
    tree_resp3 = client.get(f"/api/viewpoint-sets/{set_id}/tree")
    nodes3 = tree_resp3.get_json()["nodes"]
    assert all(n["node_type"] != "folder" for n in nodes3)


def test_folder_name_is_required(api) -> None:
    client, _store = api
    set_id = _new_set(client)

    resp = client.post(f"/api/viewpoint-sets/{set_id}/folders", json={"name": ""})
    assert resp.status_code in {400, 409, 500}


def test_reorder_items(api) -> None:
    client, store = api
    set_id = _new_set(client)
    version = store.get_version(set_id, status="draft")

    item1 = client.post(
        f"/api/viewpoint-sets/{set_id}/versions/{version['version_number']}/items",
        json={"name": "A観点", "category": "機能", "automation": "manual"},
    ).get_json()["item"]
    item2 = client.post(
        f"/api/viewpoint-sets/{set_id}/versions/{version['version_number']}/items",
        json={"name": "B観点", "category": "機能", "automation": "manual"},
    ).get_json()["item"]

    resp = client.patch(
        f"/api/viewpoint-sets/{set_id}/items/reorder",
        json={
            "orders": [{"id": item1["id"], "sort_order": 2}, {"id": item2["id"], "sort_order": 1}]
        },
    )
    assert resp.status_code == 200


def test_viewpoint_templates_listing_includes_real_presets(api) -> None:
    """data/viewpoint_templates/*.json（ISTQB/ISO25010/非機能要求グレード2018/PMBOK）が
    実際に一覧に出ること（R1-18: プリセットが空フォルダのみだった問題への対応）。"""
    client, _store = api
    resp = client.get("/api/viewpoint-templates")
    assert resp.status_code == 200
    keys = {t["key"] for t in resp.get_json()["templates"]}
    assert {"istqb", "iso25010", "nfr2018", "pmbok"} <= keys
    for template in resp.get_json()["templates"]:
        assert template["item_count"] > 0, f"{template['key']} にはアイテムが必要"


def test_apply_viewpoint_template_seeds_folders_and_items(api) -> None:
    client, store = api
    set_id = _new_set(client)

    resp = client.post(f"/api/viewpoint-sets/{set_id}/templates/istqb/apply")
    assert resp.status_code == 200
    result = resp.get_json()["result"]
    assert result["created_folders"] == 4
    assert result["created_items"] > 0

    tree = store.get_tree(set_id)
    assert any(node["name"] == "単体テスト" and node["node_type"] == "folder" for node in tree)
    assert any(node["name"] == "境界値分析" and node["node_type"] == "viewpoint" for node in tree)


def test_apply_viewpoint_template_unknown_key_returns_404(api) -> None:
    client, _store = api
    set_id = _new_set(client)
    resp = client.post(f"/api/viewpoint-sets/{set_id}/templates/does-not-exist/apply")
    assert resp.status_code == 404
