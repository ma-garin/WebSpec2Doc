"""外部サービス連携（Jira 起票・Webhook・Teams・Notion・Confluence・QualityForward）の設定と実行 API。

保存先は他の設定と同じく `.env`。連携ごとに保存先を分けると、
どこを見れば設定済みか分からなくなるため揃える。

秘密値（API トークン・Webhook URL）はレスポンスでもログでも生のまま出さない。
画面へ返すのはマスク済み文字列と真偽値だけ。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Blueprint, request
from werkzeug.wrappers import Response as BaseResponse

from web.audit_context import record_admin_event
from web.config import OUTPUT_DIR
from web.env_store import _mask_key, _read_env, _write_env
from web.services import defect_store
from web.services.jira_client import (
    DEFAULT_ISSUE_TYPE,
    ENV_API_TOKEN,
    ENV_BASE_URL,
    ENV_EMAIL,
    ENV_ISSUE_TYPE,
    ENV_PROJECT_KEY,
    ERROR_BASE_URL,
    _is_allowed_base_url,
    build_issue_from_defect,
    create_issue,
    jira_config_from_env,
    verify_connection,
)
from web.tenancy import scoped_output_dir
from web.validation import _valid_domain

logger = logging.getLogger(__name__)

bp = Blueprint("integrations", __name__)
INSTANCE_DIR = Path("instance")

ENV_SLACK_WEBHOOK = "SLACK_WEBHOOK_URL"
ENV_GENERIC_WEBHOOK = "GENERIC_WEBHOOK_URL"
ENV_TEAMS_WEBHOOK = "TEAMS_WEBHOOK_URL"
ENV_NOTION_API_TOKEN = "NOTION_API_TOKEN"
ENV_NOTION_DATABASE_ID = "NOTION_DATABASE_ID"
ENV_CONFLUENCE_BASE_URL = "CONFLUENCE_BASE_URL"
ENV_CONFLUENCE_EMAIL = "CONFLUENCE_EMAIL"
ENV_CONFLUENCE_API_TOKEN = "CONFLUENCE_API_TOKEN"
ENV_CONFLUENCE_SPACE_KEY = "CONFLUENCE_SPACE_KEY"
ENV_QUALITYFORWARD_API_KEY = "QUALITYFORWARD_API_KEY"

_MAX_VALUE_LENGTH = 500

# (.env のキー, フォーム項目名, 秘密値か)
_JIRA_FIELDS: tuple[tuple[str, str, bool], ...] = (
    (ENV_BASE_URL, "jira_base_url", False),
    (ENV_EMAIL, "jira_email", False),
    (ENV_API_TOKEN, "jira_api_token", True),
    (ENV_PROJECT_KEY, "jira_project_key", False),
    (ENV_ISSUE_TYPE, "jira_issue_type", False),
)

_TEAMS_FIELDS: tuple[tuple[str, str, bool], ...] = ((ENV_TEAMS_WEBHOOK, "teams_webhook_url", True),)

_NOTION_FIELDS: tuple[tuple[str, str, bool], ...] = (
    (ENV_NOTION_API_TOKEN, "notion_api_token", True),
    (ENV_NOTION_DATABASE_ID, "notion_database_id", False),
)

_CONFLUENCE_FIELDS: tuple[tuple[str, str, bool], ...] = (
    (ENV_CONFLUENCE_BASE_URL, "confluence_base_url", False),
    (ENV_CONFLUENCE_EMAIL, "confluence_email", False),
    (ENV_CONFLUENCE_API_TOKEN, "confluence_api_token", True),
    (ENV_CONFLUENCE_SPACE_KEY, "confluence_space_key", False),
)

_QUALITYFORWARD_FIELDS: tuple[tuple[str, str, bool], ...] = (
    (ENV_QUALITYFORWARD_API_KEY, "qualityforward_api_key", True),
)

_ERROR_GENERIC = "処理に失敗しました"
_ERROR_NOT_CONFIGURED = "Jira 連携が未設定です（ベース URL・メール・トークン・プロジェクトキー）"
_ERROR_TEAMS_NOT_CONFIGURED = "Teams の Webhook URL が未設定です。先に保存してください。"
_ERROR_NOTION_NOT_CONFIGURED = "Notion 連携が未設定です（API トークン・データベース ID）"
_ERROR_CONFLUENCE_NOT_CONFIGURED = (
    "Confluence 連携が未設定です（ベース URL・メール・API トークン・スペースキー）"
)
_ERROR_QUALITYFORWARD_NOT_CONFIGURED = "QualityForward 連携が未設定です（プロジェクト API キー）"
_ERROR_BAD_DOMAIN = "ドメイン指定が不正です"
_ERROR_DEFECT_NOT_FOUND = "指定された不具合が見つかりません"


@bp.before_request
def _integrations_admin_guard() -> BaseResponse | None:
    """連携設定の変更と起票は管理者のみ。参照（GET）は制限しない。

    settings.py と同じ書き方に揃える。認証が無効な開発環境では
    require_admin が None を返すため制限されない。
    """
    from web.auth import require_admin

    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        return require_admin()
    return None


def _guarded(handler: Callable[..., Any]) -> Callable[..., Any]:
    """未捕捉例外で 500 を返さないための境界。

    連携先は外部サービスで、こちらの制御外の理由でいつでも落ちる。
    500 だと画面側が理由を出せないため、必ず ok/error の形へ寄せる。
    """

    @wraps(handler)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return handler(*args, **kwargs)
        except Exception:
            logger.error(
                "連携 API の処理に失敗しました: endpoint=%s", handler.__name__, exc_info=True
            )
            return {"ok": False, "error": _ERROR_GENERIC}

    return wrapper


@bp.get("/api/integrations")
@_guarded
def get_integrations() -> dict[str, Any]:
    """連携の設定状況を返す。秘密値はマスク済みの文字列のみ。"""
    from web.services.confluence_client import confluence_config_from_env
    from web.services.notion_client import notion_config_from_env
    from web.services.qualityforward_client import qualityforward_config_from_env

    env = _read_env()
    token = env.get(ENV_API_TOKEN, "")
    webhook_url = env.get(ENV_GENERIC_WEBHOOK, "")
    teams_url = env.get(ENV_TEAMS_WEBHOOK, "")
    notion_token = env.get(ENV_NOTION_API_TOKEN, "")
    confluence_token = env.get(ENV_CONFLUENCE_API_TOKEN, "")
    qualityforward_key = env.get(ENV_QUALITYFORWARD_API_KEY, "")
    return {
        "jira": {
            "configured": jira_config_from_env(env) is not None,
            "base_url": env.get(ENV_BASE_URL, ""),
            "project_key": env.get(ENV_PROJECT_KEY, ""),
            "issue_type": env.get(ENV_ISSUE_TYPE, "") or DEFAULT_ISSUE_TYPE,
            "email": env.get(ENV_EMAIL, ""),
            "token_masked": _mask_key(token) if token else "",
        },
        "slack": {"configured": bool(env.get(ENV_SLACK_WEBHOOK, ""))},
        "webhook": {
            "configured": bool(webhook_url),
            "url_masked": _mask_key(webhook_url) if webhook_url else "",
        },
        "teams": {
            "configured": bool(teams_url),
            "url_masked": _mask_key(teams_url) if teams_url else "",
        },
        "notion": {
            "configured": notion_config_from_env(env) is not None,
            "database_id": env.get(ENV_NOTION_DATABASE_ID, ""),
            "token_masked": _mask_key(notion_token) if notion_token else "",
        },
        "confluence": {
            "configured": confluence_config_from_env(env) is not None,
            "base_url": env.get(ENV_CONFLUENCE_BASE_URL, ""),
            "space_key": env.get(ENV_CONFLUENCE_SPACE_KEY, ""),
            "email": env.get(ENV_CONFLUENCE_EMAIL, ""),
            "token_masked": _mask_key(confluence_token) if confluence_token else "",
        },
        "qualityforward": {
            "configured": qualityforward_config_from_env(env) is not None,
            "key_masked": _mask_key(qualityforward_key) if qualityforward_key else "",
        },
    }


@bp.post("/api/integrations/jira")
@_guarded
def save_jira_settings() -> dict[str, Any]:
    """Jira 接続設定を保存する。トークンは空送信で「変更なし」とみなす。

    画面はマスク済みの値しか持っていないため、空欄＝既存維持にしないと
    別項目を直すたびにトークンが消える。
    """
    return _save_integration_settings(
        "jira",
        _JIRA_FIELDS,
        lambda merged: jira_config_from_env(merged) is not None,
        url_env_keys=(ENV_BASE_URL,),
    )


@bp.post("/api/integrations/jira/test")
@_guarded
def test_jira_connection() -> dict[str, Any]:
    """保存済み設定で接続確認する。失敗理由は定型文（Jira の応答本文は返さない）。"""
    config = jira_config_from_env(_read_env())
    if config is None:
        return {"ok": False, "message": _ERROR_NOT_CONFIGURED}
    ok, message = verify_connection(config)
    return {
        "ok": ok,
        "message": f"接続に成功しました（プロジェクト: {message}）" if ok else message,
    }


@bp.post("/api/integrations/jira/issues")
@_guarded
def create_jira_issue() -> dict[str, Any]:
    """不具合 1 件を Jira へ起票する。

    起票結果（jira_issue_key / jira_issue_url）は **未保存**。
    defect_store には任意フィールドを更新する公開関数が無く（update_state は
    状態遷移専用）、ここで defects.json を直接書くと保存経路が二重になるため、
    レスポンスで返すだけに留める。永続化は defect_store 側に更新関数が
    用意された時点で行う。
    """
    domain = _form_value("domain")
    defect_id = _form_value("defect_id")
    if not _valid_domain(domain):
        return _issue_error(_ERROR_BAD_DOMAIN)

    config = jira_config_from_env(_read_env())
    if config is None:
        return _issue_error(_ERROR_NOT_CONFIGURED)

    defects = defect_store.list_defects(scoped_output_dir(OUTPUT_DIR), domain)
    defect = next((d for d in defects if d.get("id") == defect_id), None)
    if defect is None:
        return _issue_error(_ERROR_DEFECT_NOT_FOUND)

    summary, description, labels = build_issue_from_defect(defect, domain)
    ok, result = create_issue(
        config,
        summary=summary,
        description=description,
        labels=labels,
        severity=str(defect.get("severity", "")),
    )
    record_admin_event(
        INSTANCE_DIR,
        action="integrations.jira.issue_created",
        target_type="defect",
        target_id=defect_id,
        outcome="success" if ok else "failure",
        detail={"domain": domain, "issue_key": result.get("issue_key", "")},
    )
    if not ok:
        return _issue_error(str(result.get("error", "")) or _ERROR_GENERIC)
    return {
        "ok": True,
        "issue_key": str(result.get("issue_key", "")),
        "issue_url": str(result.get("issue_url", "")),
        "error": "",
    }


@bp.post("/api/integrations/slack/test")
@_guarded
def test_slack_notification() -> dict[str, Any]:
    """保存済みの Slack Webhook へテストメッセージを送る。

    「保存できた」ことと「実際に届く」ことは別物で、URL の打ち間違いや
    チャンネル削除は送ってみるまで分からない。本文に送信時刻を入れ、
    受信側で今回の送信かどうかを判別できるようにする。
    """
    webhook = (_read_env().get(ENV_SLACK_WEBHOOK) or "").strip()
    if not webhook:
        return {"ok": False, "message": "Slack Webhook URL が未設定です。先に保存してください。"}

    from web.services.notifier import (
        NOTIFIER_SLACK,
        NotifierConfig,
        TestNotification,
        send_test_notification,
    )

    sent_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    sent = send_test_notification(
        NotifierConfig(notifier_type=NOTIFIER_SLACK, endpoint=webhook),
        TestNotification(sent_at=sent_at, source="設定 > 通知"),
    )
    record_admin_event(
        INSTANCE_DIR,
        action="integrations.slack.tested",
        target_type="integration",
        target_id="slack",
        detail={"sent": sent},
    )
    if sent:
        return {"ok": True, "message": f"テストメッセージを送信しました（{sent_at}）。"}
    return {
        "ok": False,
        "message": "送信できませんでした。Webhook URL とチャンネルの有効性を確認してください。",
    }


@bp.post("/api/integrations/webhook")
@_guarded
def save_webhook_settings() -> dict[str, Any]:
    """汎用 Webhook の送信先を保存する。空文字なら設定を解除する。

    内部ホスト宛は拒否する（SSRF 防止）。設定値経由でサーバから
    社内ネットワークへ任意リクエストを飛ばせてしまうため。
    """
    url = _form_value("webhook_url")
    if url and not _is_allowed_base_url(url):
        return {"ok": False, "error": ERROR_BASE_URL}
    _write_env({ENV_GENERIC_WEBHOOK: url})
    record_admin_event(
        INSTANCE_DIR,
        action="integrations.webhook.updated",
        target_type="integration",
        target_id="webhook",
        detail={"changed_fields": ["webhook_url"], "cleared": not url},
    )
    return {"ok": True}


def _form_value(name: str) -> str:
    """フォーム値を trim して長さ上限で切る（.env へ巨大な値を書かせない）。"""
    return str(request.form.get(name, "") or "").strip()[:_MAX_VALUE_LENGTH]


def _issue_error(message: str) -> dict[str, Any]:
    """起票 API の失敗レスポンス（キー構成は成功時と同じに保つ）。"""
    return {"ok": False, "issue_key": "", "issue_url": "", "error": message}


@bp.post("/api/integrations/teams")
@_guarded
def save_teams_settings() -> dict[str, Any]:
    """Teams の Incoming Webhook URL を保存する。

    URL 自体が送信権限そのものなので秘密値として扱い、空送信は既存維持。
    内部ホスト宛は拒否する（SSRF 防止）。
    """
    return _save_integration_settings(
        "teams",
        _TEAMS_FIELDS,
        lambda merged: bool(merged.get(ENV_TEAMS_WEBHOOK, "")),
        url_env_keys=(ENV_TEAMS_WEBHOOK,),
    )


@bp.post("/api/integrations/teams/test")
@_guarded
def test_teams_notification() -> dict[str, Any]:
    """保存済みの Teams Webhook へテストメッセージを送る。

    Slack と同じく「保存できた」と「実際に届く」は別物のため、
    送信時刻入りの本文を投げて受信側で今回の送信を判別できるようにする。
    """
    webhook = (_read_env().get(ENV_TEAMS_WEBHOOK) or "").strip()
    if not webhook:
        return {"ok": False, "message": _ERROR_TEAMS_NOT_CONFIGURED}

    from web.services.notifier import (
        NOTIFIER_TEAMS,
        NotifierConfig,
        TestNotification,
        send_test_notification,
    )

    sent_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    sent = send_test_notification(
        NotifierConfig(notifier_type=NOTIFIER_TEAMS, endpoint=webhook),
        TestNotification(sent_at=sent_at, source="設定 > 外部サービス連携"),
    )
    record_admin_event(
        INSTANCE_DIR,
        action="integrations.teams.tested",
        target_type="integration",
        target_id="teams",
        outcome="success" if sent else "failure",
        detail={"sent": sent},
    )
    if sent:
        return {"ok": True, "message": f"テストメッセージを送信しました（{sent_at}）。"}
    return {
        "ok": False,
        "message": "送信できませんでした。Webhook URL とチャネルの有効性を確認してください。",
    }


@bp.post("/api/integrations/notion")
@_guarded
def save_notion_settings() -> dict[str, Any]:
    """Notion 連携設定を保存する。API トークンは空送信で「変更なし」。"""
    from web.services.notion_client import notion_config_from_env

    return _save_integration_settings(
        "notion",
        _NOTION_FIELDS,
        lambda merged: notion_config_from_env(merged) is not None,
    )


@bp.post("/api/integrations/notion/test")
@_guarded
def test_notion_connection() -> dict[str, Any]:
    """保存済み設定で Notion への接続を確認する。"""
    from web.services.notion_client import notion_config_from_env
    from web.services.notion_client import verify_connection as verify_notion

    env = _read_env()
    return _report_connection_test(
        "notion",
        notion_config_from_env(env),
        verify_notion,
        _ERROR_NOTION_NOT_CONFIGURED,
        "接続に成功しました（データベース: {detail}）",
    )


@bp.post("/api/integrations/confluence")
@_guarded
def save_confluence_settings() -> dict[str, Any]:
    """Confluence 連携設定を保存する。API トークンは空送信で「変更なし」。"""
    from web.services.confluence_client import confluence_config_from_env

    return _save_integration_settings(
        "confluence",
        _CONFLUENCE_FIELDS,
        lambda merged: confluence_config_from_env(merged) is not None,
        url_env_keys=(ENV_CONFLUENCE_BASE_URL,),
    )


@bp.post("/api/integrations/confluence/test")
@_guarded
def test_confluence_connection() -> dict[str, Any]:
    """保存済み設定で Confluence への接続を確認する。"""
    from web.services.confluence_client import confluence_config_from_env
    from web.services.confluence_client import verify_connection as verify_confluence

    env = _read_env()
    return _report_connection_test(
        "confluence",
        confluence_config_from_env(env),
        verify_confluence,
        _ERROR_CONFLUENCE_NOT_CONFIGURED,
        "接続に成功しました（スペース: {detail}）",
    )


@bp.post("/api/integrations/qualityforward")
@_guarded
def save_qualityforward_settings() -> dict[str, Any]:
    """QualityForward 連携設定を保存する。API キーは空送信で「変更なし」。"""
    from web.services.qualityforward_client import qualityforward_config_from_env

    return _save_integration_settings(
        "qualityforward",
        _QUALITYFORWARD_FIELDS,
        lambda merged: qualityforward_config_from_env(merged) is not None,
    )


@bp.post("/api/integrations/qualityforward/test")
@_guarded
def test_qualityforward_connection() -> dict[str, Any]:
    """保存済み設定で QualityForward への接続を確認する。

    確認できるのは接続だけ。テスト結果の登録（POST /test_results）は
    必須パラメータが公開仕様に無く未実装のため、この画面からは行えない。
    """
    from web.services.qualityforward_client import qualityforward_config_from_env
    from web.services.qualityforward_client import verify_connection as verify_qf

    env = _read_env()
    return _report_connection_test(
        "qualityforward",
        qualityforward_config_from_env(env),
        verify_qf,
        _ERROR_QUALITYFORWARD_NOT_CONFIGURED,
        "接続に成功しました（{detail}）",
    )


def _collect_env_updates(
    env: dict[str, str], fields: tuple[tuple[str, str, bool], ...]
) -> tuple[dict[str, str], list[str]]:
    """フォーム値を .env の更新差分へ畳む。

    画面はマスク済みの値しか持っていないため、秘密値の空送信は
    「変更なし」とみなす。そうしないと別項目を直すたびに秘密値が消える。
    """
    updates: dict[str, str] = {}
    changed_fields: list[str] = []
    for env_key, form_key, is_secret in fields:
        value = _form_value(form_key)
        if is_secret and not value:
            continue  # 空送信は既存の秘密値の維持
        if value == env.get(env_key, ""):
            continue
        updates[env_key] = value
        changed_fields.append(form_key)
    return updates, changed_fields


def _save_integration_settings(
    service: str,
    fields: tuple[tuple[str, str, bool], ...],
    is_configured: Callable[[dict[str, str]], bool],
    url_env_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    """連携設定の保存手順（差分抽出 → URL 検証 → 保存 → 監査記録）を 1 か所に置く。

    サービスごとに書き写すと、監査記録の抜けや秘密値の扱いの食い違いが
    必ず生まれるため、違いは項目表（fields）だけに閉じ込める。
    監査ログには値を残さず、変更された項目名だけを記録する。
    """
    env = _read_env()
    updates, changed_fields = _collect_env_updates(env, fields)

    for env_key in url_env_keys:
        url = updates.get(env_key, env.get(env_key, ""))
        if url and not _is_allowed_base_url(url):
            return {"ok": False, "error": ERROR_BASE_URL}

    if updates:
        _write_env(updates)
    merged = {**env, **updates}
    record_admin_event(
        INSTANCE_DIR,
        action=f"integrations.{service}.updated",
        target_type="integration",
        target_id=service,
        detail={"changed_fields": changed_fields},
    )
    return {"ok": True, "configured": is_configured(merged)}


def _report_connection_test(
    service: str,
    config: Any,
    verify: Callable[[Any], tuple[bool, str]],
    not_configured_message: str,
    success_template: str,
) -> dict[str, Any]:
    """接続確認の共通処理。未設定なら通信せず定型文を返す。

    失敗理由は連携先クライアントが整形した定型文をそのまま使い、
    外部サービスの応答本文を画面へ素通ししない。
    """
    if config is None:
        return {"ok": False, "message": not_configured_message}
    ok, message = verify(config)
    record_admin_event(
        INSTANCE_DIR,
        action=f"integrations.{service}.tested",
        target_type="integration",
        target_id=service,
        outcome="success" if ok else "failure",
        detail={"succeeded": ok},
    )
    return {"ok": ok, "message": success_template.format(detail=message) if ok else message}
