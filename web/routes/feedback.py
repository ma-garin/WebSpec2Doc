"""利用者フィードバックの受け口（POST /api/feedback）と一覧（GET /api/feedback）。

トップバーのユーザーメニュー →「フィードバック」で開くビューから呼ばれる。
送信者・テナント・画面名はサーバー側で補うため、クライアントは種類と本文だけを送る
（クライアント申告の身元を信じない）。
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, g, request

from web.auth import require_admin
from web.services.feedback_store import (
    FeedbackError,
    append_feedback,
    read_feedback,
    validate,
)
from web.tenancy import scoped_instance_path

logger = logging.getLogger(__name__)

bp = Blueprint("feedback", __name__)
INSTANCE_DIR = Path("instance")


def _feedback_path() -> Path:
    return scoped_instance_path(INSTANCE_DIR / "feedback.jsonl")


@bp.post("/api/feedback")
def api_submit_feedback() -> tuple[dict, int] | dict:
    payload = request.get_json(silent=True) or {}
    try:
        category, message = validate(
            str(payload.get("category", "")), str(payload.get("message", ""))
        )
    except FeedbackError as exc:
        return {"error": str(exc), "code": exc.code}, 400

    user = getattr(g, "auth_user", None) or {}
    tenant = getattr(g, "tenant", None) or {}
    try:
        entry = append_feedback(
            _feedback_path(),
            category=category,
            message=message,
            user_id=str(user.get("id", "")),
            user_email=str(user.get("email", "")),
            tenant_id=str(tenant.get("id", "")),
            # 画面名は表示の手がかりに過ぎないのでクライアント申告のままでよい
            view=str(payload.get("view", "")),
        )
    except OSError:
        # 書けなかったことを成功として返さない（送ったのに消えるのが最悪の結果）
        logger.exception("フィードバックの保存に失敗しました")
        return {
            "error": "保存に失敗しました。しばらくしてからもう一度お試しください。",
            "code": "write_failed",
        }, 500
    return {"ok": True, "id": entry.id, "at": entry.at}


@bp.get("/api/feedback")
def api_list_feedback() -> tuple[dict, int] | dict:
    """このテナントに届いたフィードバック一覧（管理者のみ）。

    閲覧用の画面は用意していない。届いたものを確認する手段がファイルの直接参照
    しかない状態を避けるため、API だけ先に置いてある。
    """
    denied = require_admin()
    if denied is not None:
        return denied
    return {"feedback": read_feedback(_feedback_path())}
