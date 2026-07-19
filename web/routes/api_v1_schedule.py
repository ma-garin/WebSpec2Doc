"""/api/v1 のスケジュール・通知設定 CRUD。

検証規則は web/routes/schedule.py（画面用API）と同一の実装を再利用する。
規則を二重に持つと、片方だけ直して不整合を起こすため。

認可: 変更系（PUT/DELETE）は管理者のみ。テナント分離は _out() が担う。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Blueprint, request

from web.audit_context import record_admin_event
from web.routes.schedule import (
    _VALID_INTERVALS,
    _VALID_NOTIFY_TYPES,
    _VALID_SEVERITY_FILTERS,
    _calc_next_run_at,
    _default_config,
    _load_config,
    _operational_fields,
    _public_config,
    _save_config,
    _schedule_path,
)
from web.validation import _valid_domain, _valid_url

bp = Blueprint("api_v1_schedule", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

INSTANCE_DIR = Path("instance")

NOTIFICATION_FIELDS = (
    "notify_type",
    "notify_endpoint",
    "severity_filter",
    "notify_template",
)


@bp.before_request
def _admin_guard() -> Any:
    """設定の変更は管理者のみ。読み取りは既存の認証・テナント境界に従う。"""
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        from web.auth import require_admin

        return require_admin()
    return None


# ─────────────────── スケジュール ───────────────────


@bp.get("/sites/<domain>/schedule")
def api_v1_schedule_get(domain: str) -> tuple[dict, int] | dict:
    """定期クロール設定を返す。未設定なら既定値を返す。"""
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    return {"schedule": _public_config(_load_config(domain))}


@bp.put("/sites/<domain>/schedule")
def api_v1_schedule_put(domain: str) -> tuple[dict, int] | dict:
    """定期クロール設定を作成・更新する。"""
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    body = request.get_json(silent=True) or {}

    config, error = _validated_schedule(domain, body)
    if error:
        return {"error": error}, 400

    _save_config(domain, config)
    record_admin_event(
        INSTANCE_DIR,
        action="schedule.updated",
        target_type="site",
        target_id=domain,
        detail={"interval": config.get("interval", "")},
    )
    return {"schedule": _public_config(config)}


@bp.delete("/sites/<domain>/schedule")
def api_v1_schedule_delete(domain: str) -> tuple[dict, int] | dict:
    """定期クロール設定を削除する。存在しない場合も 404 にはしない（冪等）。"""
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    path = _schedule_path(domain)
    existed = path.is_file()
    if existed:
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("スケジュール設定を削除できませんでした: %s", exc)
            return {"error": "スケジュール設定を削除できませんでした"}, 500
    record_admin_event(
        INSTANCE_DIR,
        action="schedule.deleted",
        target_type="site",
        target_id=domain,
        outcome="success" if existed else "noop",
    )
    return {"deleted": existed}


# ─────────────────── 通知設定 ───────────────────


@bp.get("/sites/<domain>/notifications")
def api_v1_notifications_get(domain: str) -> tuple[dict, int] | dict:
    """通知設定を返す（送信先は _public_config の方針に従う）。"""
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    config = _public_config(_load_config(domain))
    return {"notifications": {key: config.get(key, "") for key in NOTIFICATION_FIELDS}}


@bp.put("/sites/<domain>/notifications")
def api_v1_notifications_put(domain: str) -> tuple[dict, int] | dict:
    """通知設定のみを更新する（スケジュール間隔などは変更しない）。"""
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    body = request.get_json(silent=True) or {}
    existing = _load_config(domain)

    merged = {**existing, **{key: body[key] for key in NOTIFICATION_FIELDS if key in body}}
    error = _validate_notification_fields(merged)
    if error:
        return {"error": error}, 400

    _save_config(domain, merged)
    record_admin_event(
        INSTANCE_DIR,
        action="notification.updated",
        target_type="site",
        target_id=domain,
        detail={"notify_type": str(merged.get("notify_type", ""))},
    )
    config = _public_config(merged)
    return {"notifications": {key: config.get(key, "") for key in NOTIFICATION_FIELDS}}


# ─────────────────── 検証 ───────────────────


def _validated_schedule(domain: str, body: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """PUT 本文を検証し、保存できる設定を返す。エラー時は第2要素にメッセージ。"""
    existing = _load_config(domain) or _default_config(domain)

    interval = str(body.get("interval", existing.get("interval", "disabled"))).strip()
    if interval not in _VALID_INTERVALS:
        return {}, f"invalid interval: {interval}"

    site_url = str(body.get("site_url", existing.get("site_url", ""))).strip()
    if site_url and not _valid_url(site_url):
        return {}, "invalid site_url: http/https のみ対応しています"

    merged = {**existing, **body, "domain": domain, "interval": interval, "site_url": site_url}
    error = _validate_notification_fields(merged)
    if error:
        return {}, error

    limit = merged.get("diff_summary_limit", 5)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        return {}, "invalid diff_summary_limit"

    operational, operational_error = _operational_fields(merged)
    if operational_error:
        return {}, operational_error

    config = {**merged, **operational}
    config["next_run_at"] = _calc_next_run_at(interval, operational)
    return config, ""


def _validate_notification_fields(config: dict[str, Any]) -> str:
    from web.services.notifier import validate_notification_template

    notify_type = str(config.get("notify_type", "none")).strip()
    if notify_type not in _VALID_NOTIFY_TYPES:
        return f"invalid notify_type: {notify_type}"

    severity_filter = str(config.get("severity_filter", "breaking")).strip()
    if severity_filter not in _VALID_SEVERITY_FILTERS:
        return f"invalid severity_filter: {severity_filter}"

    template_error = validate_notification_template(str(config.get("notify_template", "")))
    return template_error or ""
