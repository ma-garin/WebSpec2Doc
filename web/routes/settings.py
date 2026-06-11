from __future__ import annotations

from flask import Blueprint, request

from web.config import DEFAULT_OPENAI_MODEL
from web.env_store import _mask_key, _read_env, _write_env
from web.validation import _sanitize

bp = Blueprint("settings", __name__)


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
