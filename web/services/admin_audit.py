"""管理操作を秘密値なしのJSONLへ追記・検索する。"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_MAX_LINE_BYTES = 64 * 1024
_MAX_STRING_LENGTH = 500
_SECRET_KEY_PARTS = frozenset(
    {"password", "secret", "token", "api_key", "apikey", "webhook", "endpoint"}
)
_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.Lock] = {}


@dataclass(frozen=True)
class AdminAuditEvent:
    version: int
    id: str
    at: str
    actor_id: str
    actor_email: str
    action: str
    target_type: str
    target_id: str
    outcome: str
    detail: dict[str, Any]


def append_admin_audit(
    path: Path,
    *,
    action: str,
    actor_id: str = "",
    actor_email: str = "",
    target_type: str = "",
    target_id: str = "",
    outcome: str = "success",
    detail: dict[str, Any] | None = None,
    now: datetime | None = None,
    event_id: str | None = None,
) -> AdminAuditEvent:
    event = AdminAuditEvent(
        version=1,
        id=event_id or uuid.uuid4().hex,
        at=(now or datetime.now(UTC)).replace(microsecond=0).isoformat(),
        actor_id=actor_id[:_MAX_STRING_LENGTH],
        actor_email=actor_email[:_MAX_STRING_LENGTH],
        action=action[:_MAX_STRING_LENGTH],
        target_type=target_type[:_MAX_STRING_LENGTH],
        target_id=target_id[:_MAX_STRING_LENGTH],
        outcome=outcome if outcome in {"success", "failure"} else "failure",
        detail=_sanitize_detail(detail or {}),
    )
    line = json.dumps(asdict(event), ensure_ascii=False, separators=(",", ":"))
    if len(line.encode("utf-8")) > _MAX_LINE_BYTES:
        event = AdminAuditEvent(**{**asdict(event), "detail": {"truncated": True}})
        line = json.dumps(asdict(event), ensure_ascii=False, separators=(",", ":"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with _path_lock(path):
        path.touch(mode=0o600, exist_ok=True)
        path.chmod(0o600)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
    return event


def read_admin_audit(
    path: Path,
    *,
    limit: int = 100,
    offset: int = 0,
    action: str = "",
    outcome: str = "",
    query: str = "",
) -> list[AdminAuditEvent]:
    if not path.is_file():
        return []
    events: list[AdminAuditEvent] = []
    normalized_query = query.casefold().strip()
    skipped = 0
    try:
        for line in _reverse_lines(path):
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            event = _event_from_data(data)
            if event is None:
                continue
            if action and event.action != action:
                continue
            if outcome and event.outcome != outcome:
                continue
            if normalized_query:
                searchable = " ".join(
                    (
                        event.actor_id,
                        event.actor_email,
                        event.action,
                        event.target_type,
                        event.target_id,
                        json.dumps(event.detail, ensure_ascii=False),
                    )
                ).casefold()
                if normalized_query not in searchable:
                    continue
            if skipped < max(0, offset):
                skipped += 1
                continue
            events.append(event)
            if len(events) >= max(1, min(limit, 101)):
                break
    except OSError:
        return events
    return events


def _event_from_data(data: object) -> AdminAuditEvent | None:
    if not isinstance(data, dict) or data.get("version") != 1:
        return None
    string_fields = (
        "id",
        "at",
        "actor_id",
        "actor_email",
        "action",
        "target_type",
        "target_id",
        "outcome",
    )
    if any(not isinstance(data.get(field), str) for field in string_fields):
        return None
    if data["outcome"] not in {"success", "failure"} or not isinstance(data.get("detail"), dict):
        return None
    try:
        return AdminAuditEvent(**data)
    except TypeError:
        return None


def _reverse_lines(path: Path, *, chunk_size: int = 8192):
    """監査ファイルを全体展開せず末尾から1行ずつ返す。"""
    with path.open("rb") as stream:
        stream.seek(0, 2)
        position = stream.tell()
        buffer = b""
        while position > 0:
            size = min(chunk_size, position)
            position -= size
            stream.seek(position)
            buffer = stream.read(size) + buffer
            parts = buffer.split(b"\n")
            buffer = parts[0]
            for raw_line in reversed(parts[1:]):
                if raw_line:
                    yield raw_line.decode("utf-8", errors="replace")
        if buffer:
            yield buffer.decode("utf-8", errors="replace")


def _sanitize_detail(value: Any, *, key: str = "") -> Any:
    lowered = key.lower()
    if any(part in lowered for part in _SECRET_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(item_key): _sanitize_detail(item, key=str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [_sanitize_detail(item) for item in value]
    if isinstance(value, str):
        return value[:_MAX_STRING_LENGTH]
    if value is None or isinstance(value, bool | int | float):
        return value
    return str(value)[:_MAX_STRING_LENGTH]


def _path_lock(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())
