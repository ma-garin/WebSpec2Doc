from __future__ import annotations

import json
import stat
from datetime import UTC, datetime
from pathlib import Path

from web.services.admin_audit import append_admin_audit, read_admin_audit


def test_append_and_read_admin_audit_redacts_secret_values(tmp_path: Path) -> None:
    path = tmp_path / "instance" / "admin_audit.jsonl"

    written = append_admin_audit(
        path,
        action="schedule.settings_updated",
        actor_id="admin-1",
        actor_email="admin@example.com",
        target_type="site",
        target_id="example.com",
        outcome="success",
        detail={
            "changed_fields": ["interval", "notify_endpoint"],
            "notify_endpoint": "https://example.invalid/secret-token",
        },
        now=datetime(2026, 7, 17, tzinfo=UTC),
        event_id="event-1",
    )

    assert written.id == "event-1"
    assert written.at == "2026-07-17T00:00:00+00:00"
    assert written.detail["notify_endpoint"] == "[REDACTED]"
    assert "secret-token" not in path.read_text(encoding="utf-8")
    assert read_admin_audit(path) == [written]


def test_read_admin_audit_filters_newest_first_and_skips_broken_lines(tmp_path: Path) -> None:
    path = tmp_path / "admin_audit.jsonl"
    append_admin_audit(
        path,
        action="user.login",
        actor_email="member@example.com",
        target_type="user",
        target_id="member-1",
        outcome="failure",
        now=datetime(2026, 7, 16, tzinfo=UTC),
        event_id="older",
    )
    append_admin_audit(
        path,
        action="retention.settings_updated",
        actor_email="admin@example.com",
        target_type="workspace",
        target_id="workspace-1",
        outcome="success",
        now=datetime(2026, 7, 17, tzinfo=UTC),
        event_id="newer",
    )
    with path.open("a", encoding="utf-8") as stream:
        stream.write("broken json\n")

    events = read_admin_audit(
        path,
        action="user.login",
        outcome="failure",
        query="member@example.com",
    )

    assert [event.id for event in events] == ["older"]
    assert [event.id for event in read_admin_audit(path)] == ["newer", "older"]


def test_read_admin_audit_skips_json_with_invalid_field_types(tmp_path: Path) -> None:
    path = tmp_path / "admin_audit.jsonl"
    append_admin_audit(path, action="user.login", actor_email="valid@example.com")
    invalid = {
        "version": 1,
        "id": "invalid",
        "at": "2026-07-17T00:00:00+00:00",
        "actor_id": 123,
        "actor_email": "broken@example.com",
        "action": "user.login",
        "target_type": "user",
        "target_id": "broken",
        "outcome": "success",
        "detail": {},
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(invalid) + "\n")

    events = read_admin_audit(path, query="example.com")

    assert len(events) == 1
    assert events[0].actor_email == "valid@example.com"


def test_admin_audit_file_is_owner_read_write_only(tmp_path: Path) -> None:
    path = tmp_path / "admin_audit.jsonl"

    append_admin_audit(path, action="retention.settings_updated")

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
