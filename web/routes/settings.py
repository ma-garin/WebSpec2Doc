from __future__ import annotations

import logging

from flask import Blueprint, request

from web.config import DEFAULT_OPENAI_MODEL
from web.env_store import _mask_key, _read_env, _write_env
from web.services.openai_qa import test_openai_connection
from web.services.test_design_settings import (
    get_test_design_settings,
    save_test_design_settings,
)
from web.validation import _sanitize

bp = Blueprint("settings", __name__)


@bp.before_request
def _settings_admin_guard():
    """設定の変更（APIキー・Slack・許可設定など）は管理者のみ。

    認証が無効な場合（ローカル単独利用）は従来どおり制限しない。
    """
    from web.auth import require_admin

    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        return require_admin()
    return None


@bp.get("/api/settings")
def get_settings() -> dict:
    env = _read_env()
    key = env.get("OPENAI_API_KEY", "")
    slack_url = env.get("SLACK_WEBHOOK_URL", "")
    return {
        "openai_key_set": bool(key),
        "openai_key_masked": _mask_key(key),
        "openai_model": env.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        "openai_org_id": env.get("OPENAI_ORG_ID", ""),
        "openai_project_id": env.get("OPENAI_PROJECT_ID", ""),
        "slack_webhook_set": bool(slack_url),
        "slack_webhook_masked": (_mask_key(slack_url) if slack_url else ""),
    }


@bp.post("/api/settings")
def post_settings() -> dict:
    updates: dict[str, str] = {}
    api_key = _sanitize(request.form.get("api_key", ""))
    if api_key:
        updates["OPENAI_API_KEY"] = api_key
    if "model" in request.form:
        updates["OPENAI_MODEL"] = _sanitize(request.form.get("model", "")) or DEFAULT_OPENAI_MODEL
    if "org_id" in request.form:
        updates["OPENAI_ORG_ID"] = _sanitize(request.form.get("org_id", ""))
    if "project_id" in request.form:
        updates["OPENAI_PROJECT_ID"] = _sanitize(request.form.get("project_id", ""))
    slack_url = _sanitize(request.form.get("slack_webhook_url", ""))
    if "slack_webhook_url" in request.form:
        updates["SLACK_WEBHOOK_URL"] = slack_url
    if updates:
        _write_env(updates)
    env = _read_env()
    return {
        "ok": True,
        "openai_key_set": bool(env.get("OPENAI_API_KEY")),
        "slack_webhook_set": bool(env.get("SLACK_WEBHOOK_URL")),
    }


@bp.post("/api/settings/test-connection")
def post_test_connection() -> dict:
    ok, message = test_openai_connection()
    return {"ok": ok, "message": message}


@bp.get("/api/settings/test-design")
def get_test_design() -> dict:
    return get_test_design_settings()


@bp.post("/api/settings/test-design")
def post_test_design() -> tuple[dict, int] | dict:
    payload = request.get_json(force=False, silent=True)
    if not isinstance(payload, dict):
        return {"error": "リクエスト形式が不正です。"}, 400
    return save_test_design_settings(payload)


@bp.get("/api/settings/allow-local")
def get_allow_local() -> dict:
    env = _read_env()
    return {"allow_local": env.get("WEBSPEC2DOC_ALLOW_LOCAL", "") == "1"}


@bp.post("/api/settings/allow-local")
def post_allow_local() -> tuple[dict, int] | dict:
    payload = request.get_json(force=False, silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("enabled"), bool):
        return {"error": "enabled must be a boolean"}, 400

    enabled = payload["enabled"]
    _write_env({"WEBSPEC2DOC_ALLOW_LOCAL": "1" if enabled else ""})
    env = _read_env()
    allow_local = env.get("WEBSPEC2DOC_ALLOW_LOCAL", "") == "1"
    logging.warning("WEBSPEC2DOC_ALLOW_LOCAL changed to %s", allow_local)
    return {"ok": True, "allow_local": allow_local}
