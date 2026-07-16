from __future__ import annotations

import json
import logging
import re
from collections import deque
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, request

from web.config import OUTPUT_DIR
from web.services.admin_audit import append_admin_audit
from web.tenancy import current_auth_user, scoped_instance_path, scoped_output_dir
from web.validation import _valid_domain, _valid_url

logger = logging.getLogger(__name__)

bp = Blueprint("schedule", __name__)
INSTANCE_DIR = Path("instance")


@bp.before_request
def _schedule_admin_guard():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        from web.auth import require_admin

        return require_admin()
    return None


def _out() -> Path:
    """テナントスコープ済みの出力ディレクトリ（リクエスト毎に解決）。"""
    return scoped_output_dir(OUTPUT_DIR)


_VALID_INTERVALS = frozenset({"daily", "weekly", "monthly", "disabled"})
_VALID_NOTIFY_TYPES = frozenset({"slack", "teams", "email", "webhook", "none"})
_VALID_SEVERITY_FILTERS = frozenset({"breaking", "warning", "all"})
_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_DEFAULT_TIMEZONE = "Asia/Tokyo"
_MAX_RETRIES = 5
_MAX_BACKOFF_SECONDS = 3600


def _schedule_path(domain: str) -> Path:
    return _out() / domain / "schedule.json"


def _default_config(domain: str) -> dict:
    return {
        "domain": domain,
        "interval": "disabled",
        "notify_type": "none",
        "notify_endpoint": "",
        "severity_filter": "breaking",
        "notify_template": "",
        "diff_summary_limit": 5,
        "timezone": _DEFAULT_TIMEZONE,
        "weekdays": [],
        "window_start": "",
        "window_end": "",
        "retry_max": 2,
        "retry_backoff_seconds": 60,
        "last_run_at": None,
        "next_run_at": None,
    }


def _load_config(domain: str) -> dict:
    path = _schedule_path(domain)
    if not path.is_file():
        return _default_config(domain)
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("schedule config must be an object")
        return {**_default_config(domain), **loaded}
    except (OSError, ValueError, json.JSONDecodeError):
        logger.warning("schedule.json の読み込みに失敗: %s", domain)
        return _default_config(domain)


def _public_config(config: dict) -> dict:
    """保存済み秘密値を除いたブラウザ向け設定を返す。"""
    public = dict(config)
    endpoint = str(public.pop("notify_endpoint", "")).strip()
    public["notify_endpoint_set"] = bool(endpoint)
    return public


def _save_config(domain: str, config: dict) -> None:
    path = _schedule_path(domain)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def _calc_next_run_at(interval: str, config: dict | None = None) -> str | None:
    from web.services.scheduler import _calc_next_run_at as calculate_next_run_at

    values = config or {}
    return calculate_next_run_at(
        interval,
        datetime.now().astimezone(),
        timezone_name=str(values.get("timezone", "")),
        weekdays=tuple(values.get("weekdays") or ()),
        window_start=str(values.get("window_start", "")),
        window_end=str(values.get("window_end", "")),
    )


def _operational_fields(body: dict) -> tuple[dict, str | None]:
    """運用設定を正規化する。エラー時は利用者向けメッセージを返す。"""
    timezone = str(body.get("timezone", _DEFAULT_TIMEZONE)).strip()
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return {}, "invalid timezone"

    raw_weekdays = body.get("weekdays", [])
    if not isinstance(raw_weekdays, list) or any(
        isinstance(day, bool) or not isinstance(day, int) or day < 0 or day > 6
        for day in raw_weekdays
    ):
        return {}, "invalid weekdays"
    weekdays = sorted(set(raw_weekdays))

    window_start = str(body.get("window_start", "")).strip()
    window_end = str(body.get("window_end", "")).strip()
    if bool(window_start) != bool(window_end):
        return {}, "window_start and window_end must both be set"
    if window_start and (
        not _TIME_RE.fullmatch(window_start)
        or not _TIME_RE.fullmatch(window_end)
        or window_start == window_end
    ):
        return {}, "invalid execution window"

    retry_max = body.get("retry_max", 2)
    retry_backoff_seconds = body.get("retry_backoff_seconds", 60)
    if (
        isinstance(retry_max, bool)
        or not isinstance(retry_max, int)
        or not 0 <= retry_max <= _MAX_RETRIES
    ):
        return {}, "invalid retry_max"
    if (
        isinstance(retry_backoff_seconds, bool)
        or not isinstance(retry_backoff_seconds, int)
        or not 1 <= retry_backoff_seconds <= _MAX_BACKOFF_SECONDS
    ):
        return {}, "invalid retry_backoff_seconds"
    return {
        "timezone": timezone,
        "weekdays": weekdays,
        "window_start": window_start,
        "window_end": window_end,
        "retry_max": retry_max,
        "retry_backoff_seconds": retry_backoff_seconds,
    }, None


@bp.get("/schedule/config")
def api_schedule_config_get() -> tuple[dict, int] | dict:
    domain = request.args.get("domain", "").strip()
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    return _public_config(_load_config(domain))


@bp.post("/schedule/config")
def api_schedule_config_post() -> tuple[dict, int] | dict:
    body = request.get_json(silent=True) or {}
    domain = str(body.get("domain", "")).strip()
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400

    interval = str(body.get("interval", "")).strip()
    if interval not in _VALID_INTERVALS:
        return {"error": f"invalid interval: {interval}"}, 400

    notify_type = str(body.get("notify_type", "")).strip()
    if notify_type not in _VALID_NOTIFY_TYPES:
        return {"error": f"invalid notify_type: {notify_type}"}, 400

    severity_filter = str(body.get("severity_filter", "")).strip()
    if severity_filter not in _VALID_SEVERITY_FILTERS:
        return {"error": f"invalid severity_filter: {severity_filter}"}, 400

    site_url = str(body.get("site_url", "")).strip()
    if site_url and not _valid_url(site_url):
        return {"error": "invalid site_url: http/https のみ対応しています"}, 400
    existing = _load_config(domain)
    submitted_endpoint = str(body.get("notify_endpoint", "")).strip()
    notify_endpoint = submitted_endpoint
    if not notify_endpoint and str(existing.get("notify_type", "")) == notify_type:
        notify_endpoint = str(existing.get("notify_endpoint", "")).strip()
    notify_template = str(body.get("notify_template", ""))
    from web.services.notifier import validate_notification_template

    template_error = validate_notification_template(notify_template)
    if template_error:
        return {"error": template_error}, 400
    diff_summary_limit = body.get("diff_summary_limit", 5)
    if (
        isinstance(diff_summary_limit, bool)
        or not isinstance(diff_summary_limit, int)
        or not 1 <= diff_summary_limit <= 20
    ):
        return {"error": "invalid diff_summary_limit"}, 400
    operational, operational_error = _operational_fields(body)
    if operational_error:
        return {"error": operational_error}, 400

    next_run_at = _calc_next_run_at(interval, operational)

    config: dict = {
        **existing,
        "domain": domain,
        "site_url": site_url,
        "interval": interval,
        "notify_type": notify_type,
        "notify_endpoint": notify_endpoint,
        "severity_filter": severity_filter,
        "notify_template": notify_template,
        "diff_summary_limit": diff_summary_limit,
        **operational,
        "next_run_at": next_run_at,
    }
    if "created_at" not in config:
        config["created_at"] = datetime.now().isoformat(timespec="seconds")

    _save_config(domain, config)
    actor = current_auth_user() or {}
    append_admin_audit(
        scoped_instance_path(INSTANCE_DIR / "admin_audit.jsonl"),
        action="schedule.settings_updated",
        actor_id=str(actor.get("id", "")),
        actor_email=str(actor.get("email", "local-admin")),
        target_type="site",
        target_id=domain,
        detail={"changed_fields": sorted(body)},
    )
    logger.info("schedule config saved: domain=%s interval=%s", domain, interval)
    return {"ok": True, "domain": domain, "next_run_at": next_run_at}


@bp.post("/schedule/run-now")
def api_schedule_run_now() -> tuple[dict, int] | dict:
    body = request.get_json(silent=True) or {}
    domain = str(body.get("domain", "")).strip()
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400

    config = _load_config(domain)
    now_iso = datetime.now().isoformat(timespec="seconds")
    config["last_run_at"] = now_iso
    config["next_run_at"] = _calc_next_run_at(config.get("interval", "disabled"), config)
    _save_config(domain, config)

    logger.info("schedule run-now queued: domain=%s", domain)
    return {
        "ok": True,
        "message": "スケジュールクロールをキューに追加しました",
        "domain": domain,
    }


@bp.get("/schedule/status")
def api_schedule_status() -> tuple[dict, int] | dict:
    domain = request.args.get("domain", "").strip()
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400

    config = _load_config(domain)
    return {
        "domain": domain,
        "interval": config.get("interval", "disabled"),
        "last_run_at": config.get("last_run_at"),
        "next_run_at": config.get("next_run_at"),
    }


@bp.get("/schedule/history")
def api_schedule_history() -> tuple[dict, int] | dict:
    domain = request.args.get("domain", "").strip()
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    try:
        limit = int(request.args.get("limit", "20"))
    except ValueError:
        return {"error": "invalid limit"}, 400
    if not 1 <= limit <= 100:
        return {"error": "invalid limit"}, 400

    history_path = _out() / domain / "schedule_history.jsonl"
    items: deque[dict] = deque(maxlen=limit)
    if history_path.is_file():
        try:
            with history_path.open(encoding="utf-8") as stream:
                for line in stream:
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(item, dict):
                        items.append(item)
        except OSError as exc:
            logger.warning("schedule history read failed: domain=%s, %s", domain, exc)
    return {"domain": domain, "items": list(reversed(items))}


@bp.post("/schedule/notify/test")
def api_schedule_notify_test() -> tuple[dict, int] | dict:
    body = request.get_json(silent=True) or {}
    domain = str(body.get("domain", "")).strip()
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    stored = _load_config(domain)
    values = {**stored, **body}
    if not str(body.get("notify_endpoint", "")).strip():
        values["notify_endpoint"] = stored.get("notify_endpoint", "")
    notifier_type = str(values.get("notify_type", "none")).strip()
    if notifier_type not in _VALID_NOTIFY_TYPES or notifier_type == "none":
        return {"error": "notification channel is not configured"}, 400
    site_url = str(values.get("site_url", "")).strip() or f"https://{domain}"
    if not _valid_url(site_url):
        return {"error": "invalid site_url"}, 400

    from web.services.notifier import (
        DriftNotification,
        notifier_config_from_mapping,
        send_drift_notification,
        validate_notification_template,
    )

    template_error = validate_notification_template(str(values.get("notify_template", "")))
    if template_error:
        return {"error": template_error}, 400
    notifier_config = notifier_config_from_mapping(values)
    if notifier_config is None:
        return {"error": "notification endpoint is not configured"}, 400
    notification = DriftNotification(
        site_url=site_url,
        added_pages=1,
        removed_pages=0,
        field_changes=0,
        api_changes=0,
        report_url="テスト通知（レポートは生成されません）",
        added_page_names=("テスト画面",),
    )
    if not send_drift_notification(notifier_config, notification):
        return {"error": "テスト通知を送信できませんでした"}, 502
    return {"ok": True, "message": "テスト通知を送信しました"}
