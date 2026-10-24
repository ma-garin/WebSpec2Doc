"""/api/v1 スケジュール・通知 CRUD の契約。

画面用APIと同じ検証規則が効くこと、変更が実ファイルへ落ちること、
不正入力が拒否されることを固定する。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture()
def client():
    import app as appmod

    return appmod.app.test_client()


@pytest.fixture()
def scoped(tmp_path: Path):
    """出力先を一時ディレクトリへ差し替える。"""
    with (
        patch("web.routes.schedule.OUTPUT_DIR", tmp_path),
        patch("web.tenancy.scoped_output_dir", return_value=tmp_path),
    ):
        yield tmp_path


def _schedule_file(root: Path, domain: str = "example.com") -> Path:
    return root / domain / "schedule.json"


# ─────────────────── スケジュール ───────────────────


def test_get_returns_defaults_when_not_configured(client, scoped) -> None:
    response = client.get("/api/v1/sites/example.com/schedule")

    assert response.status_code == 200
    schedule = response.get_json()["schedule"]
    assert schedule["domain"] == "example.com"
    assert schedule["interval"] == "disabled"


def test_put_persists_configuration_to_disk(client, scoped) -> None:
    response = client.put(
        "/api/v1/sites/example.com/schedule",
        json={"interval": "daily", "site_url": "https://example.com"},
    )

    assert response.status_code == 200
    assert response.get_json()["schedule"]["interval"] == "daily"
    saved = json.loads(_schedule_file(scoped).read_text(encoding="utf-8"))
    assert saved["interval"] == "daily"
    assert saved["site_url"] == "https://example.com"


def test_put_computes_next_run_at_for_active_interval(client, scoped) -> None:
    client.put("/api/v1/sites/example.com/schedule", json={"interval": "daily"})

    saved = json.loads(_schedule_file(scoped).read_text(encoding="utf-8"))
    assert saved.get("next_run_at")


def test_put_rejects_unknown_interval(client, scoped) -> None:
    response = client.put("/api/v1/sites/example.com/schedule", json={"interval": "hourly"})

    assert response.status_code == 400
    assert "interval" in response.get_json()["error"]
    assert not _schedule_file(scoped).exists()


def test_put_rejects_non_http_site_url(client, scoped) -> None:
    response = client.put(
        "/api/v1/sites/example.com/schedule",
        json={"interval": "daily", "site_url": "file:///etc/passwd"},
    )

    assert response.status_code == 400
    assert not _schedule_file(scoped).exists()


def test_put_rejects_out_of_range_diff_summary_limit(client, scoped) -> None:
    response = client.put(
        "/api/v1/sites/example.com/schedule",
        json={"interval": "daily", "diff_summary_limit": 99},
    )

    assert response.status_code == 400


def test_invalid_domain_is_rejected_before_touching_disk(client, scoped) -> None:
    response = client.get("/api/v1/sites/..%2Fetc/schedule")

    assert response.status_code in (400, 404)


def test_delete_removes_file_and_is_idempotent(client, scoped) -> None:
    client.put("/api/v1/sites/example.com/schedule", json={"interval": "daily"})
    assert _schedule_file(scoped).is_file()

    first = client.delete("/api/v1/sites/example.com/schedule")
    second = client.delete("/api/v1/sites/example.com/schedule")

    assert first.status_code == 200
    assert first.get_json()["deleted"] is True
    assert second.status_code == 200
    assert second.get_json()["deleted"] is False
    assert not _schedule_file(scoped).exists()


# ─────────────────── 通知設定 ───────────────────


def test_notifications_get_returns_only_notification_fields(client, scoped) -> None:
    response = client.get("/api/v1/sites/example.com/notifications")

    assert response.status_code == 200
    assert set(response.get_json()["notifications"]) == {
        "notify_type",
        "notify_endpoint",
        "severity_filter",
        "notify_template",
    }


def test_notifications_put_updates_without_touching_interval(client, scoped) -> None:
    client.put("/api/v1/sites/example.com/schedule", json={"interval": "daily"})

    response = client.put(
        "/api/v1/sites/example.com/notifications",
        json={"notify_type": "slack", "severity_filter": "all"},
    )

    assert response.status_code == 200
    saved = json.loads(_schedule_file(scoped).read_text(encoding="utf-8"))
    assert saved["notify_type"] == "slack"
    assert saved["severity_filter"] == "all"
    assert saved["interval"] == "daily"


def test_notifications_put_rejects_unknown_type(client, scoped) -> None:
    response = client.put(
        "/api/v1/sites/example.com/notifications", json={"notify_type": "carrier-pigeon"}
    )

    assert response.status_code == 400


def test_notifications_put_rejects_invalid_severity_filter(client, scoped) -> None:
    response = client.put(
        "/api/v1/sites/example.com/notifications", json={"severity_filter": "whatever"}
    )

    assert response.status_code == 400


# ─────────────────── 認可 ───────────────────


def test_mutations_require_admin_when_auth_is_enabled(client, scoped) -> None:
    from flask import jsonify

    def deny():
        response = jsonify({"error": "この操作には管理者権限が必要です。"})
        response.status_code = 403
        return response

    with patch("web.auth.require_admin", side_effect=deny):
        put = client.put("/api/v1/sites/example.com/schedule", json={"interval": "daily"})
        delete = client.delete("/api/v1/sites/example.com/schedule")
        get = client.get("/api/v1/sites/example.com/schedule")

    assert put.status_code == 403
    assert delete.status_code == 403
    assert get.status_code == 200
    assert not _schedule_file(scoped).exists()
