from __future__ import annotations

from pathlib import Path

import pytest
import web.routes.viewpoints as viewpoints_routes
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
