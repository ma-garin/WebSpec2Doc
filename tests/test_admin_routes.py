from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
from web import validation
from web.routes import admin, report, schedule

H = {"Host": "127.0.0.1"}


@pytest.fixture(autouse=True)
def _local_admin_scope(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_MODE", "off")
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_DB", str(tmp_path / "instance" / "auth.db"))
    monkeypatch.setattr(admin, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(admin, "INSTANCE_DIR", tmp_path / "instance")


def _setup_owner(client) -> None:
    response = client.post(
        "/auth/setup",
        data={
            "tenant_name": "QA Team",
            "name": "Owner",
            "email": "owner@example.com",
            "password": "secret-pass-123",
            "password_confirm": "secret-pass-123",
        },
        headers=H,
    )
    assert response.status_code == 302


def _login(client, email: str, password: str) -> None:
    response = client.post(
        "/auth/login",
        data={"email": email, "password": password, "next": "/"},
        headers=H,
    )
    assert response.status_code == 302


def test_local_admin_can_read_and_update_retention_policy() -> None:
    client = appmod.app.test_client()

    before = client.get("/api/admin/retention", headers=H)
    updated = client.put(
        "/api/admin/retention",
        json={"mode": "generations", "generations": 12},
        headers=H,
    )
    after = client.get("/api/admin/retention", headers=H)

    assert before.status_code == 200
    assert before.get_json()["policy"]["mode"] == "unlimited"
    assert updated.status_code == 200
    assert updated.get_json()["policy"]["generations"] == 12
    assert after.get_json()["policy"]["mode"] == "generations"
    assert after.get_json()["policy"]["generations"] == 12


def test_local_admin_can_inspect_storage_usage_by_site(tmp_path: Path) -> None:
    (admin.OUTPUT_DIR / "example.com" / "snapshots").mkdir(parents=True)
    (admin.OUTPUT_DIR / "example.com" / "snapshots" / "20260717-010203.json").write_text(
        "1234", encoding="utf-8"
    )
    (admin.OUTPUT_DIR / "example.com" / "report.md").write_text("abcdef", encoding="utf-8")
    admin.INSTANCE_DIR.mkdir(parents=True)
    (admin.INSTANCE_DIR / "schedule.json").write_text("123", encoding="utf-8")

    response = appmod.app.test_client().get("/api/admin/storage", headers=H)

    assert response.status_code == 200
    assert response.get_json() == {
        "storage": {
            "output_bytes": 10,
            "instance_bytes": 3,
            "total_bytes": 13,
            "sites": [
                {
                    "domain": "example.com",
                    "snapshot_count": 1,
                    "snapshot_bytes": 4,
                    "total_bytes": 10,
                    "updated_at": response.get_json()["storage"]["sites"][0]["updated_at"],
                }
            ],
        }
    }


def test_retention_update_is_visible_in_filtered_admin_audit() -> None:
    client = appmod.app.test_client()
    updated = client.put(
        "/api/admin/retention",
        json={"mode": "days", "days": 30},
        headers=H,
    )

    response = client.get(
        "/api/admin/audit?action=retention.settings_updated&outcome=success&query=local-admin",
        headers=H,
    )

    assert updated.status_code == 200
    assert response.status_code == 200
    events = response.get_json()["events"]
    assert len(events) == 1
    assert events[0]["actor_email"] == "local-admin"
    assert events[0]["action"] == "retention.settings_updated"
    assert events[0]["detail"] == {"changed_fields": ["days", "mode"]}


def test_member_cannot_read_admin_operations_data(monkeypatch) -> None:
    monkeypatch.delenv("WEBSPEC2DOC_AUTH_MODE")
    owner = appmod.app.test_client()
    _setup_owner(owner)
    created = owner.post(
        "/api/auth/users",
        json={
            "email": "member@example.com",
            "name": "Member",
            "password": "member-pass-123",
            "role": "member",
        },
        headers=H,
    )
    assert created.status_code == 200
    member = appmod.app.test_client()
    _login(member, "member@example.com", "member-pass-123")

    assert member.get("/api/admin/storage", headers=H).status_code == 403
    assert member.get("/api/admin/retention", headers=H).status_code == 403
    assert member.get("/api/admin/audit", headers=H).status_code == 403
    assert member.post("/schedule/config", json={}, headers=H).status_code == 403
    member_settings = member.get("/settings", headers=H).get_data(as_text=True)
    assert 'id="set-tab-data"' not in member_settings
    assert 'id="set-tab-audit"' not in member_settings
    assert owner.get("/api/admin/storage", headers=H).status_code == 200


def test_schedule_settings_update_is_recorded_without_endpoint_secret(monkeypatch) -> None:
    monkeypatch.setattr(schedule, "OUTPUT_DIR", admin.OUTPUT_DIR)
    monkeypatch.setattr(schedule, "INSTANCE_DIR", admin.INSTANCE_DIR)
    endpoint = "https://hooks.example.invalid/private-token"
    response = appmod.app.test_client().post(
        "/schedule/config",
        json={
            "domain": "example.com",
            "site_url": "https://example.com",
            "interval": "daily",
            "notify_type": "webhook",
            "notify_endpoint": endpoint,
            "severity_filter": "all",
            "timezone": "Asia/Tokyo",
            "weekdays": [],
            "window_start": "",
            "window_end": "",
            "retry_max": 2,
            "retry_backoff_seconds": 60,
        },
        headers=H,
    )

    audit = appmod.app.test_client().get(
        "/api/admin/audit?action=schedule.settings_updated",
        headers=H,
    )

    assert response.status_code == 200
    events = audit.get_json()["events"]
    assert len(events) == 1
    assert events[0]["target_id"] == "example.com"
    assert "notify_endpoint" in events[0]["detail"]["changed_fields"]
    assert endpoint not in (admin.INSTANCE_DIR / "admin_audit.jsonl").read_text(encoding="utf-8")


def test_login_success_and_failure_are_recorded_in_tenant_audit(monkeypatch) -> None:
    monkeypatch.delenv("WEBSPEC2DOC_AUTH_MODE")
    owner = appmod.app.test_client()
    _setup_owner(owner)
    visitor = appmod.app.test_client()
    failed = visitor.post(
        "/auth/login",
        data={
            "email": "owner@example.com",
            "password": "wrong-password",
            "next": "/",
        },
        headers=H,
    )
    _login(visitor, "owner@example.com", "secret-pass-123")

    failures = owner.get(
        "/api/admin/audit?action=user.login&outcome=failure&query=owner@example.com",
        headers=H,
    ).get_json()["events"]
    successes = owner.get(
        "/api/admin/audit?action=user.login&outcome=success&query=owner@example.com",
        headers=H,
    ).get_json()["events"]

    assert failed.status_code == 401
    assert len(failures) == 1
    assert failures[0]["target_type"] == "user"
    assert len(successes) == 1


def test_member_creation_and_update_are_attributed_to_admin(monkeypatch) -> None:
    monkeypatch.delenv("WEBSPEC2DOC_AUTH_MODE")
    owner = appmod.app.test_client()
    _setup_owner(owner)
    created = owner.post(
        "/api/auth/users",
        json={
            "email": "member@example.com",
            "name": "Member",
            "password": "member-pass-123",
            "role": "member",
        },
        headers=H,
    ).get_json()["user"]
    updated = owner.patch(
        f"/api/auth/users/{created['id']}",
        json={"is_active": False},
        headers=H,
    )

    events = owner.get(
        "/api/admin/audit?query=member@example.com",
        headers=H,
    ).get_json()["events"]

    assert updated.status_code == 200
    member_events = [
        event for event in events if event["action"] in {"user.created", "user.updated"}
    ]
    assert {event["action"] for event in member_events} == {"user.created", "user.updated"}
    assert all(event["actor_email"] == "owner@example.com" for event in member_events)
    assert all(event["target_type"] == "user" for event in member_events)
    assert all(event["target_id"] == created["id"] for event in member_events)


def test_report_download_is_recorded_as_export_event(monkeypatch) -> None:
    monkeypatch.setattr(report, "OUTPUT_DIR", admin.OUTPUT_DIR)
    monkeypatch.setattr(report, "INSTANCE_DIR", admin.INSTANCE_DIR)
    monkeypatch.setattr(validation, "OUTPUT_DIR", admin.OUTPUT_DIR)
    report_file = admin.OUTPUT_DIR / "example.com" / "report.pdf"
    report_file.parent.mkdir(parents=True)
    report_file.write_bytes(b"pdf")

    downloaded = appmod.app.test_client().get(
        f"/download?path={report_file}",
        headers=H,
    )
    events = (
        appmod.app.test_client()
        .get(
            "/api/admin/audit?action=report.exported",
            headers=H,
        )
        .get_json()["events"]
    )

    assert downloaded.status_code == 200
    assert len(events) == 1
    assert events[0]["target_type"] == "report"
    assert events[0]["target_id"] == "example.com/report.pdf"


def test_settings_page_exposes_on_demand_data_and_audit_tabs() -> None:
    response = appmod.app.test_client().get("/settings", headers=H)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'id="set-tab-data"' in html
    assert 'id="set-panel-data"' in html
    assert 'id="set-tab-audit"' in html
    assert 'id="set-panel-audit"' in html
    assert 'id="retention-mode"' in html
    assert 'id="admin-audit-table"' in html
    assert 'id="ci-drift-command"' in html


def test_admin_can_open_backup_and_restore_guide() -> None:
    response = appmod.app.test_client().get("/api/admin/backup-guide", headers=H)

    assert response.status_code == 200
    assert response.mimetype == "text/markdown"
    assert "output/" in response.get_data(as_text=True)
    assert "instance/" in response.get_data(as_text=True)
