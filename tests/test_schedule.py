"""スケジュール API のテスト"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.routes.schedule as schedule_mod


@pytest.fixture(autouse=True)
def _isolated_schedule_audit(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(schedule_mod, "INSTANCE_DIR", tmp_path / "instance")


def _client():
    return appmod.app.test_client()


# ---------- GET /schedule/config ----------


def test_schedule_config_default_when_no_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().get("/schedule/config?domain=example.com")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["interval"] == "disabled"
    assert data["domain"] == "example.com"
    assert data["last_run_at"] is None
    assert data["next_run_at"] is None


def test_schedule_config_rejects_dotdot_domain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().get("/schedule/config?domain=../etc")
    assert resp.status_code == 400


def test_schedule_config_rejects_empty_domain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().get("/schedule/config")
    assert resp.status_code == 400


# ---------- POST /schedule/config ----------


def test_schedule_config_save_and_read(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)

    payload = {
        "domain": "example.com",
        "site_url": "https://example.com",
        "interval": "weekly",
        "notify_type": "slack",
        "notify_endpoint": "https://hooks.slack.com/xxx",
        "severity_filter": "all",
        "timezone": "Asia/Tokyo",
        "weekdays": [0, 1, 2, 3, 4],
        "window_start": "02:00",
        "window_end": "05:00",
        "retry_max": 2,
        "retry_backoff_seconds": 60,
    }
    resp = _client().post(
        "/schedule/config",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    post_data = resp.get_json()
    assert post_data["ok"] is True
    assert post_data["domain"] == "example.com"
    assert post_data["next_run_at"] is not None
    next_run = datetime.fromisoformat(post_data["next_run_at"])
    assert next_run.utcoffset() is not None
    assert next_run.weekday() in {0, 1, 2, 3, 4}
    assert 2 <= next_run.hour < 5

    # 保存されたファイルを確認
    schedule_file = tmp_path / "example.com" / "schedule.json"
    assert schedule_file.is_file()
    saved = json.loads(schedule_file.read_text(encoding="utf-8"))
    assert saved["interval"] == "weekly"
    assert saved["notify_type"] == "slack"
    assert saved["severity_filter"] == "all"
    assert saved["timezone"] == "Asia/Tokyo"
    assert saved["weekdays"] == [0, 1, 2, 3, 4]

    public = _client().get("/schedule/config?domain=example.com").get_json()
    assert "notify_endpoint" not in public
    assert public["notify_endpoint_set"] is True
    assert public["interval"] == "weekly"
    assert public["timezone"] == "Asia/Tokyo"
    assert public["weekdays"] == [0, 1, 2, 3, 4]


def test_schedule_config_blank_endpoint_preserves_saved_secret(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    base = {
        "domain": "example.com",
        "site_url": "https://example.com",
        "interval": "daily",
        "notify_type": "teams",
        "notify_endpoint": "https://example.invalid/secret",
        "severity_filter": "all",
        "timezone": "Asia/Tokyo",
        "weekdays": [],
        "window_start": "",
        "window_end": "",
        "retry_max": 2,
        "retry_backoff_seconds": 60,
        "notify_template": "",
        "diff_summary_limit": 5,
    }
    assert _client().post("/schedule/config", json=base).status_code == 200

    assert (
        _client().post("/schedule/config", json={**base, "notify_endpoint": ""}).status_code == 200
    )

    saved = json.loads((tmp_path / "example.com" / "schedule.json").read_text(encoding="utf-8"))
    assert saved["notify_endpoint"] == "https://example.invalid/secret"


def test_schedule_config_default_has_operational_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().get("/schedule/config?domain=example.com")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["timezone"] == "Asia/Tokyo"
    assert data["weekdays"] == []
    assert data["window_start"] == ""
    assert data["window_end"] == ""
    assert data["retry_max"] == 2
    assert data["retry_backoff_seconds"] == 60


def test_schedule_config_rejects_invalid_operational_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    base = {
        "domain": "example.com",
        "site_url": "https://example.com",
        "interval": "daily",
        "notify_type": "none",
        "notify_endpoint": "",
        "severity_filter": "all",
        "timezone": "Asia/Tokyo",
        "weekdays": [],
        "window_start": "",
        "window_end": "",
        "retry_max": 2,
        "retry_backoff_seconds": 60,
    }
    invalid = (
        {"timezone": "Mars/Olympus"},
        {"weekdays": [0, 7]},
        {"window_start": "2:00", "window_end": "05:00"},
        {"window_start": "02:00", "window_end": ""},
        {"window_start": "02:00", "window_end": "02:00"},
        {"retry_max": 6},
        {"retry_backoff_seconds": 0},
    )
    for override in invalid:
        resp = _client().post("/schedule/config", json={**base, **override})
        assert resp.status_code == 400, override


def test_schedule_config_saves_teams_template_and_summary_limit(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().post(
        "/schedule/config",
        json={
            "domain": "example.com",
            "site_url": "https://example.com",
            "interval": "daily",
            "notify_type": "teams",
            "notify_endpoint": "https://prod.example.logic.azure.com/workflows/example",
            "severity_filter": "all",
            "notify_template": "{{ site_url }} {{ added_pages }}",
            "diff_summary_limit": 3,
        },
    )
    assert resp.status_code == 200
    saved = json.loads((tmp_path / "example.com" / "schedule.json").read_text(encoding="utf-8"))
    assert saved["notify_type"] == "teams"
    assert saved["notify_template"] == "{{ site_url }} {{ added_pages }}"
    assert saved["diff_summary_limit"] == 3


def test_schedule_config_rejects_invalid_template_and_summary_limit(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    base = {
        "domain": "example.com",
        "site_url": "https://example.com",
        "interval": "daily",
        "notify_type": "teams",
        "notify_endpoint": "https://prod.example.logic.azure.com/workflows/example",
        "severity_filter": "all",
    }
    assert (
        _client()
        .post("/schedule/config", json={**base, "notify_template": "{{ broken"})
        .status_code
        == 400
    )
    assert (
        _client().post("/schedule/config", json={**base, "diff_summary_limit": 0}).status_code
        == 400
    )


def test_schedule_config_rejects_invalid_interval(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().post(
        "/schedule/config",
        data=json.dumps(
            {
                "domain": "example.com",
                "site_url": "https://example.com",
                "interval": "hourly",
                "notify_type": "none",
                "notify_endpoint": "",
                "severity_filter": "all",
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_schedule_config_rejects_invalid_notify_type(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().post(
        "/schedule/config",
        data=json.dumps(
            {
                "domain": "example.com",
                "site_url": "https://example.com",
                "interval": "daily",
                "notify_type": "sms",
                "notify_endpoint": "",
                "severity_filter": "all",
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_schedule_config_rejects_invalid_severity_filter(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().post(
        "/schedule/config",
        data=json.dumps(
            {
                "domain": "example.com",
                "site_url": "https://example.com",
                "interval": "daily",
                "notify_type": "none",
                "notify_endpoint": "",
                "severity_filter": "critical",
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_schedule_config_rejects_dotdot_domain_on_post(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().post(
        "/schedule/config",
        data=json.dumps(
            {
                "domain": "../etc/passwd",
                "site_url": "https://example.com",
                "interval": "daily",
                "notify_type": "none",
                "notify_endpoint": "",
                "severity_filter": "all",
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_schedule_config_disabled_sets_next_run_at_null(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().post(
        "/schedule/config",
        data=json.dumps(
            {
                "domain": "example.com",
                "site_url": "https://example.com",
                "interval": "disabled",
                "notify_type": "none",
                "notify_endpoint": "",
                "severity_filter": "breaking",
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["next_run_at"] is None


# ---------- POST /schedule/run-now ----------


def test_schedule_run_now(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)

    # 事前に schedule.json を作成
    domain_dir = tmp_path / "example.com"
    domain_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "domain": "example.com",
        "site_url": "https://example.com",
        "interval": "weekly",
        "notify_type": "none",
        "notify_endpoint": "",
        "severity_filter": "breaking",
        "last_run_at": None,
        "next_run_at": None,
    }
    (domain_dir / "schedule.json").write_text(json.dumps(config), encoding="utf-8")

    resp = _client().post(
        "/schedule/run-now",
        data=json.dumps({"domain": "example.com"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["domain"] == "example.com"
    assert "スケジュールクロール" in data["message"]

    # last_run_at が更新されていることを確認
    saved = json.loads((domain_dir / "schedule.json").read_text(encoding="utf-8"))
    assert saved["last_run_at"] is not None


def test_schedule_run_now_rejects_invalid_domain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().post(
        "/schedule/run-now",
        data=json.dumps({"domain": "../etc"}),
        content_type="application/json",
    )
    assert resp.status_code == 400


# ---------- GET /schedule/status ----------


def test_schedule_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)

    # 事前に schedule.json を作成
    domain_dir = tmp_path / "example.com"
    domain_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "domain": "example.com",
        "site_url": "https://example.com",
        "interval": "monthly",
        "notify_type": "none",
        "notify_endpoint": "",
        "severity_filter": "warning",
        "last_run_at": "2026-06-01T00:00:00",
        "next_run_at": "2026-07-01T00:00:00",
    }
    (domain_dir / "schedule.json").write_text(json.dumps(config), encoding="utf-8")

    resp = _client().get("/schedule/status?domain=example.com")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["interval"] == "monthly"
    assert data["last_run_at"] == "2026-06-01T00:00:00"
    assert data["next_run_at"] == "2026-07-01T00:00:00"
    assert data["domain"] == "example.com"


def test_schedule_status_default_when_no_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().get("/schedule/status?domain=example.com")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["interval"] == "disabled"
    assert data["last_run_at"] is None
    assert data["next_run_at"] is None


def test_schedule_status_rejects_invalid_domain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().get("/schedule/status?domain=../etc")
    assert resp.status_code == 400


# ---------- GET /schedule/history ----------


def test_schedule_history_returns_latest_valid_records(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    domain_dir = tmp_path / "example.com"
    domain_dir.mkdir(parents=True)
    records = (
        {"run_id": "old", "status": "failed", "started_at": "2026-07-15T02:00:00+09:00"},
        {"run_id": "new", "status": "complete", "started_at": "2026-07-16T02:00:00+09:00"},
    )
    history = domain_dir / "schedule_history.jsonl"
    history.write_text(
        json.dumps(records[0]) + "\nnot-json\n" + json.dumps(records[1]) + "\n",
        encoding="utf-8",
    )

    resp = _client().get("/schedule/history?domain=example.com&limit=1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["domain"] == "example.com"
    assert [item["run_id"] for item in data["items"]] == ["new"]


def test_schedule_history_rejects_invalid_limit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().get("/schedule/history?domain=example.com&limit=1000")
    assert resp.status_code == 400


# ---------- POST /schedule/notify/test ----------


def test_schedule_notify_test_sends_without_echoing_endpoint(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(schedule_mod, "INSTANCE_DIR", tmp_path / "instance")
    with patch("web.services.notifier.send_drift_notification", return_value=True) as mock_send:
        resp = _client().post(
            "/schedule/notify/test",
            json={
                "domain": "example.com",
                "site_url": "https://example.com",
                "notify_type": "teams",
                "notify_endpoint": "https://prod.example.logic.azure.com/secret",
                "notify_template": "テスト: {{ site_url }}",
            },
        )
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True, "message": "テスト通知を送信しました"}
    config, notification = mock_send.call_args.args
    assert config.notifier_type == "teams"
    assert notification.site_url == "https://example.com"
    from web.services.admin_audit import read_admin_audit

    events = read_admin_audit(tmp_path / "instance" / "admin_audit.jsonl")
    assert events[0].action == "notification.tested"
    assert events[0].outcome == "success"
    assert events[0].detail == {"channel": "teams"}


def test_schedule_notify_test_failure_is_audited(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(schedule_mod, "INSTANCE_DIR", tmp_path / "instance")
    with patch("web.services.notifier.send_drift_notification", return_value=False):
        resp = _client().post(
            "/schedule/notify/test",
            json={
                "domain": "example.com",
                "site_url": "https://example.com",
                "notify_type": "slack",
                "notify_endpoint": "https://example.invalid/webhook-secret",
            },
        )

    assert resp.status_code == 502
    from web.services.admin_audit import read_admin_audit

    events = read_admin_audit(tmp_path / "instance" / "admin_audit.jsonl")
    assert events[0].action == "notification.tested"
    assert events[0].outcome == "failure"
    assert events[0].detail == {"channel": "slack"}


def test_schedule_notify_test_uses_saved_endpoint_when_browser_sends_blank(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    domain_dir = tmp_path / "example.com"
    domain_dir.mkdir(parents=True)
    (domain_dir / "schedule.json").write_text(
        json.dumps(
            {
                "domain": "example.com",
                "site_url": "https://example.com",
                "notify_type": "teams",
                "notify_endpoint": "https://example.invalid/saved-secret",
            }
        ),
        encoding="utf-8",
    )
    with patch("web.services.notifier.send_drift_notification", return_value=True) as mock_send:
        resp = _client().post(
            "/schedule/notify/test",
            json={
                "domain": "example.com",
                "site_url": "https://example.com",
                "notify_type": "teams",
                "notify_endpoint": "",
            },
        )

    assert resp.status_code == 200
    config, _notification = mock_send.call_args.args
    assert config.endpoint == "https://example.invalid/saved-secret"


def test_schedule_notify_test_rejects_missing_channel(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().post(
        "/schedule/notify/test",
        json={"domain": "example.com", "notify_type": "none", "notify_endpoint": ""},
    )
    assert resp.status_code == 400
