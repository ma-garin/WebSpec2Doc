"""スケジュール API のテスト"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.routes.schedule as schedule_mod


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

    # 保存されたファイルを確認
    schedule_file = tmp_path / "example.com" / "schedule.json"
    assert schedule_file.is_file()
    saved = json.loads(schedule_file.read_text(encoding="utf-8"))
    assert saved["interval"] == "weekly"
    assert saved["notify_type"] == "slack"
    assert saved["severity_filter"] == "all"

    # GET で読み返す
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    resp2 = _client().get("/schedule/config?domain=example.com")
    assert resp2.status_code == 200
    get_data = resp2.get_json()
    assert get_data["interval"] == "weekly"
    assert get_data["notify_endpoint"] == "https://hooks.slack.com/xxx"


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
