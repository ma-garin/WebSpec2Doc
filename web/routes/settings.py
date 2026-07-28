from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from flask import Blueprint, request

from web.audit_context import record_admin_event
from web.config import DEFAULT_OPENAI_MODEL
from web.env_store import _mask_key, _read_env, _write_env
from web.services.openai_qa import test_openai_connection
from web.services.test_design_settings import (
    get_test_design_settings,
    save_test_design_settings,
)
from web.validation import _sanitize

logger = logging.getLogger(__name__)

bp = Blueprint("settings", __name__)
INSTANCE_DIR = Path("instance")

# LLM 接続先。src/llm/openai_client.py が同名の環境変数を読む。
ENV_LLM_BASE_URL = "WEBSPEC2DOC_LLM_BASE_URL"
ENV_LLM_MODEL = "WEBSPEC2DOC_LLM_MODEL"
OLLAMA_DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
OLLAMA_DEFAULT_MODEL = "qwen2.5:3b"


def _provider_of(base_url: str) -> str:
    """ベース URL からプロバイダ種別を導出する。

    空または OpenAI 公式エンドポイントなら ``openai``、それ以外は
    OpenAI 互換のローカルサーバ（Ollama）とみなす。
    """
    if not base_url or "api.openai.com" in base_url:
        return "openai"
    return "ollama"


def _is_local_base_url(base_url: str) -> bool:
    """ベース URL がローカルホスト宛かを判定する（SSRF 防止）。"""
    try:
        host = urllib.parse.urlparse(base_url).hostname or ""
    except ValueError:
        return False
    return host in {"127.0.0.1", "localhost", "::1"}


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
    llm_base_url = env.get(ENV_LLM_BASE_URL, "")
    return {
        "openai_key_set": bool(key),
        "openai_key_masked": _mask_key(key),
        "openai_model": env.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        "openai_org_id": env.get("OPENAI_ORG_ID", ""),
        "openai_project_id": env.get("OPENAI_PROJECT_ID", ""),
        "slack_webhook_set": bool(slack_url),
        "slack_webhook_masked": (_mask_key(slack_url) if slack_url else ""),
        "llm_provider": _provider_of(llm_base_url),
        "llm_base_url": llm_base_url,
        "llm_model": env.get(ENV_LLM_MODEL, ""),
    }


@bp.get("/api/settings/llm-models")
def list_llm_models() -> dict:
    """ローカル LLM サーバ（Ollama 等）が提供するモデル一覧を返す。

    OpenAI 互換の ``GET {base_url}/models`` を叩く。SSRF を避けるため、
    ローカルホスト宛のベース URL のみ許可する。
    """
    base_url = (
        _sanitize(request.args.get("base_url", ""))
        or _read_env().get(ENV_LLM_BASE_URL, "")
        or OLLAMA_DEFAULT_BASE_URL
    )
    if not _is_local_base_url(base_url):
        return {"ok": False, "error": "ローカルのエンドポイントのみ取得できます", "models": []}
    url = f"{base_url.rstrip('/')}/models"
    try:
        with urllib.request.urlopen(url, timeout=3) as response:  # noqa: S310 - ローカル限定
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        logger.info("LLM モデル一覧の取得に失敗しました (%s): %s", url, exc)
        return {"ok": False, "error": "接続できませんでした", "models": []}
    models = sorted(str(item.get("id", "")) for item in payload.get("data", []) if item.get("id"))
    return {"ok": True, "models": models}


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
    if "llm_provider" in request.form:
        provider = _sanitize(request.form.get("llm_provider", "")) or "openai"
        if provider == "ollama":
            updates[ENV_LLM_BASE_URL] = (
                _sanitize(request.form.get("llm_base_url", "")) or OLLAMA_DEFAULT_BASE_URL
            )
            updates[ENV_LLM_MODEL] = (
                _sanitize(request.form.get("llm_model", "")) or OLLAMA_DEFAULT_MODEL
            )
        else:
            # OpenAI に戻す: ベース URL を空にして既定（api.openai.com）へ復帰させる。
            updates[ENV_LLM_BASE_URL] = ""
            updates[ENV_LLM_MODEL] = _read_env().get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    slack_url = _sanitize(request.form.get("slack_webhook_url", ""))
    if "slack_webhook_url" in request.form:
        updates["SLACK_WEBHOOK_URL"] = slack_url
    if updates:
        _write_env(updates)
        record_admin_event(
            INSTANCE_DIR,
            action="settings.updated",
            target_type="workspace",
            target_id="current",
            detail={"changed_fields": sorted(updates)},
        )
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
    result = save_test_design_settings(payload)
    if not isinstance(result, tuple) or result[1] < 400:
        record_admin_event(
            INSTANCE_DIR,
            action="settings.updated",
            target_type="test_design",
            target_id="current",
            detail={"changed_fields": sorted(payload)},
        )
    return result


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
    record_admin_event(
        INSTANCE_DIR,
        action="settings.updated",
        target_type="security",
        target_id="allow_local",
        detail={"changed_fields": ["enabled"]},
    )
    return {"ok": True, "allow_local": allow_local}
