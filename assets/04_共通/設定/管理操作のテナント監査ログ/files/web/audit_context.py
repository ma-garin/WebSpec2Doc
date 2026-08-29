"""Flaskリクエストの操作者・テナントを管理監査イベントへ接続する。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from web.services.admin_audit import append_admin_audit
from web.tenancy import current_auth_user, scoped_instance_path

logger = logging.getLogger(__name__)


def record_admin_event(
    instance_dir: Path,
    *,
    action: str,
    target_type: str,
    target_id: str,
    outcome: str = "success",
    detail: dict[str, Any] | None = None,
) -> None:
    """秘密値を受け取らないルート用のbest-effort監査境界。"""
    actor = current_auth_user() or {}
    try:
        append_admin_audit(
            scoped_instance_path(instance_dir / "admin_audit.jsonl"),
            action=action,
            actor_id=str(actor.get("id", "")),
            actor_email=str(actor.get("email", "local-admin")),
            target_type=target_type,
            target_id=target_id,
            outcome=outcome,
            detail=detail,
        )
    except OSError as exc:
        logger.warning("管理監査ログを保存できませんでした: action=%s error=%s", action, exc)
