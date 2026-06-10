from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from flask import Blueprint, request

from web.config import OUTPUT_DIR
from web.validation import _valid_domain

logger = logging.getLogger(__name__)

bp = Blueprint("schedule", __name__)

_VALID_INTERVALS = frozenset({"daily", "weekly", "monthly", "disabled"})
_VALID_NOTIFY_TYPES = frozenset({"slack", "email", "webhook", "none"})
_VALID_SEVERITY_FILTERS = frozenset({"breaking", "warning", "all"})


def _schedule_path(domain: str) -> Path:
    return OUTPUT_DIR / domain / "schedule.json"


def _default_config(domain: str) -> dict:
    return {
        "domain": domain,
        "interval": "disabled",
        "notify_type": "none",
        "notify_endpoint": "",
        "severity_filter": "breaking",
        "last_run_at": None,
        "next_run_at": None,
    }


def _load_config(domain: str) -> dict:
    path = _schedule_path(domain)
    if not path.is_file():
        return _default_config(domain)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("schedule.json の読み込みに失敗: %s", domain)
        return _default_config(domain)


def _save_config(domain: str, config: dict) -> None:
    path = _schedule_path(domain)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def _calc_next_run_at(interval: str) -> str | None:
    now = datetime.now()
    if interval == "daily":
        return (now + timedelta(hours=24)).isoformat(timespec="seconds")
    if interval == "weekly":
        return (now + timedelta(days=7)).isoformat(timespec="seconds")
    if interval == "monthly":
        return (now + timedelta(days=30)).isoformat(timespec="seconds")
    return None


def _validate_domain(domain: str) -> str | None:
    """Return error string if domain is invalid, else None."""
    if not domain or ".." in domain or not _valid_domain(domain):
        return "invalid domain"
    return None


@bp.get("/schedule/config")
def api_schedule_config_get() -> tuple[dict, int] | dict:
    domain = request.args.get("domain", "").strip()
    err = _validate_domain(domain)
    if err:
        return {"error": err}, 400
    return _load_config(domain)


@bp.post("/schedule/config")
def api_schedule_config_post() -> tuple[dict, int] | dict:
    body = request.get_json(silent=True) or {}
    domain = str(body.get("domain", "")).strip()
    err = _validate_domain(domain)
    if err:
        return {"error": err}, 400

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
    notify_endpoint = str(body.get("notify_endpoint", "")).strip()

    existing = _load_config(domain)
    next_run_at = _calc_next_run_at(interval)

    config: dict = {
        **existing,
        "domain": domain,
        "site_url": site_url,
        "interval": interval,
        "notify_type": notify_type,
        "notify_endpoint": notify_endpoint,
        "severity_filter": severity_filter,
        "next_run_at": next_run_at,
    }
    if "created_at" not in config:
        config["created_at"] = datetime.now().isoformat(timespec="seconds")

    _save_config(domain, config)
    logger.info("schedule config saved: domain=%s interval=%s", domain, interval)
    return {"ok": True, "domain": domain, "next_run_at": next_run_at}


@bp.post("/schedule/run-now")
def api_schedule_run_now() -> tuple[dict, int] | dict:
    body = request.get_json(silent=True) or {}
    domain = str(body.get("domain", "")).strip()
    err = _validate_domain(domain)
    if err:
        return {"error": err}, 400

    config = _load_config(domain)
    now_iso = datetime.now().isoformat(timespec="seconds")
    config["last_run_at"] = now_iso
    config["next_run_at"] = _calc_next_run_at(config.get("interval", "disabled"))
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
    err = _validate_domain(domain)
    if err:
        return {"error": err}, 400

    config = _load_config(domain)
    return {
        "domain": domain,
        "interval": config.get("interval", "disabled"),
        "last_run_at": config.get("last_run_at"),
        "next_run_at": config.get("next_run_at"),
    }
