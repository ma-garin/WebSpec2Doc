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
        with path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
    return event


def read_admin_audit(
    path: Path,
    *,
    limit: int = 100,
    action: str = "",
    outcome: str = "",
    query: str = "",
) -> list[AdminAuditEvent]:
    if not path.is_file():
        return []
    events: list[AdminAuditEvent] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    normalized_query = query.casefold().strip()
    for line in reversed(lines):
        try:
            data = json.loads(line)
            event = AdminAuditEvent(**data)
        except (json.JSONDecodeError, TypeError):
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
        events.append(event)
        if len(events) >= max(1, min(limit, 100)):
            break
    return events


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
