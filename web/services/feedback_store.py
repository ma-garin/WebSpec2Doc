"""利用者から届いたフィードバックを JSONL へ追記・読み出しする。

管理操作の監査ログ（web/services/admin_audit.py）とは別物。あちらは「誰が何をしたか」
の記録で、こちらは「利用者が何を言ったか」の記録。混ぜると保持期間もマスキング方針も
噛み合わなくなるため、ファイルもモジュールも分けている。

保存先はテナント別（web.tenancy.scoped_instance_path）。テナントをまたいで
他社の要望が見えることのないようにする。
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

#: 受け付ける種別。UI のラジオボタンと 1:1 で対応する。
CATEGORIES: tuple[str, ...] = ("bug", "request", "other")

MAX_MESSAGE_LENGTH = 4000
_MAX_FIELD_LENGTH = 200

_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.Lock] = {}


class FeedbackError(Exception):
    """フィードバックの業務エラー。code は UI の分岐に使う。"""

    def __init__(self, message: str, code: str = "error") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class FeedbackEntry:
    version: int
    id: str
    at: str
    category: str
    message: str
    user_id: str
    user_email: str
    tenant_id: str
    view: str


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve() if path.is_absolute() else path)
    with _LOCKS_GUARD:
        if key not in _LOCKS:
            _LOCKS[key] = threading.Lock()
        return _LOCKS[key]


def _clip(value: str, limit: int = _MAX_FIELD_LENGTH) -> str:
    return (value or "").strip()[:limit]


def validate(category: str, message: str) -> tuple[str, str]:
    """入力を検証して正規化した (category, message) を返す。

    境界で弾き切ることで、保存層より下は値が正しい前提で書ける。
    """
    normalized_category = (category or "").strip().lower()
    if normalized_category not in CATEGORIES:
        raise FeedbackError("種類を選択してください。", "invalid_category")
    normalized_message = (message or "").strip()
    if not normalized_message:
        raise FeedbackError("内容を入力してください。", "empty_message")
    if len(normalized_message) > MAX_MESSAGE_LENGTH:
        raise FeedbackError(
            f"内容は{MAX_MESSAGE_LENGTH}文字以内にしてください。", "message_too_long"
        )
    return normalized_category, normalized_message


def append_feedback(
    path: Path,
    *,
    category: str,
    message: str,
    user_id: str = "",
    user_email: str = "",
    tenant_id: str = "",
    view: str = "",
    now: datetime | None = None,
    entry_id: str | None = None,
) -> FeedbackEntry:
    """1 件追記して、書いたレコードを返す。検証は validate() で先に済ませておく。"""
    entry = FeedbackEntry(
        version=1,
        id=entry_id or uuid.uuid4().hex,
        at=(now or datetime.now(UTC)).replace(microsecond=0).isoformat(),
        category=category,
        message=message[:MAX_MESSAGE_LENGTH],
        user_id=_clip(user_id),
        user_email=_clip(user_email),
        tenant_id=_clip(tenant_id),
        view=_clip(view),
    )
    line = json.dumps(asdict(entry), ensure_ascii=False)
    with _lock_for(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    return entry


def read_feedback(path: Path, limit: int = 100) -> list[dict]:
    """新しい順に読み出す。壊れた行は捨てる（1 行の破損で全体を失わせない）。"""
    if not path.is_file():
        return []
    entries: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                entries.append(parsed)
    entries.reverse()
    return entries[: max(1, min(limit, 1000))]
