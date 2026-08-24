"""Jira Cloud（REST API v3）への一方向連携クライアント。

WebSpec2Doc から Jira へ「起票する」だけの片方向に限定する。双方向同期にすると
不具合の状態（defect_store の new/fixing/retest/closed）の正本がどちらか曖昧になり、
どちらを信じるかを運用者が判断できなくなるため、取り込みは実装しない。

外向き HTTP は notifier.py と同じ方式（urllib + timeout=10 + 例外を握って失敗を返す）
に揃える。requests を足すと依存が増えるうえ、「秘密値をログへ出さない」という
既存の失敗時の作法とずれるため。
"""

from __future__ import annotations

import base64
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from web.services.defect_store import SEVERITY_LABELS, STATE_LABELS

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10
_SUMMARY_MAX_LENGTH = 80
_DESCRIPTION_MAX_LENGTH = 20_000
_LABEL_MAX_LENGTH = 60
_NON_LABEL_RE = re.compile(r"[^A-Za-z0-9_-]+")

DEFAULT_ISSUE_TYPE = "Bug"

ENV_BASE_URL = "JIRA_BASE_URL"
ENV_EMAIL = "JIRA_EMAIL"
ENV_API_TOKEN = "JIRA_API_TOKEN"
ENV_PROJECT_KEY = "JIRA_PROJECT_KEY"
ENV_ISSUE_TYPE = "JIRA_ISSUE_TYPE"

# 内部ネットワーク宛の base_url は拒否する（SSRF 防止）。
# 設定値は管理者が自由に入れられるため、ここで塞がないとサーバから
# 社内ホストへ任意リクエストを飛ばす踏み台になる。
_BLOCKED_HOSTS = frozenset({"localhost", "::1"})
_BLOCKED_HOST_PREFIXES = ("127.", "10.", "192.168.", "169.254.")
_BLOCKED_HOST_SUFFIXES = (".internal", ".local")

# 失敗理由は必ず定型文へ丸める。Jira の応答本文をそのまま返すと
# 内部エンドポイントやアカウント情報が画面へ漏れるため。
ERROR_BASE_URL = "ベース URL が不正です（https:// の外部ホストのみ指定できます）"
ERROR_AUTH = "認証に失敗しました（メールアドレスと API トークンを確認してください）"
ERROR_NOT_FOUND = "プロジェクトが見つかりません（プロジェクトキーを確認してください）"
ERROR_UNREACHABLE = "接続できませんでした（ベース URL とネットワークを確認してください）"
ERROR_UNEXPECTED_BODY = "Jira の応答を解釈できませんでした"
ERROR_EMPTY_SUMMARY = "概要が空のため起票できません"

# description に載せるフィールドと日本語見出し。
# defect の実体はドメインごとに増減するため、存在するキーだけを拾う。
_DESCRIPTION_FIELDS: tuple[tuple[str, str], ...] = (
    ("id", "不具合ID"),
    ("severity", "重要度"),
    ("state", "状態"),
    ("case_id", "関連テストケース"),
    ("screen", "発生画面"),
    ("url", "発生URL"),
    ("steps", "再現手順"),
    ("expected", "期待結果"),
    ("actual", "実際の結果"),
    ("detected_phase", "検出フェーズ"),
    ("injected_phase", "混入フェーズ"),
    ("odc_type", "ODC分類"),
    ("created_at", "検出日時"),
)


@dataclass(frozen=True)
class JiraConfig:
    """Jira 接続設定。生成後は書き換えない（秘密値の取り違えを防ぐため）。"""

    base_url: str
    email: str
    api_token: str
    project_key: str
    issue_type: str = DEFAULT_ISSUE_TYPE


def jira_config_from_env(env: Mapping[str, str]) -> JiraConfig | None:
    """.env の値から設定を組む。必須項目が 1 つでも欠けたら None。

    「部分的に設定済み」を有効扱いにすると、起票時に初めて失敗して
    原因が分からなくなる。未設定は入口で None に倒す。
    """
    base_url = _clean(env.get(ENV_BASE_URL, "")).rstrip("/")
    email = _clean(env.get(ENV_EMAIL, ""))
    api_token = _clean(env.get(ENV_API_TOKEN, ""))
    project_key = _clean(env.get(ENV_PROJECT_KEY, ""))
    if not (base_url and email and api_token and project_key):
        return None
    return JiraConfig(
        base_url=base_url,
        email=email,
        api_token=api_token,
        project_key=project_key,
        issue_type=_clean(env.get(ENV_ISSUE_TYPE, "")) or DEFAULT_ISSUE_TYPE,
    )


def verify_connection(config: JiraConfig) -> tuple[bool, str]:
    """プロジェクトを 1 件取得して接続確認する。成功時はプロジェクト名を返す。

    保存前に確かめられないと、起票が必要になった時点で初めて誤設定に気づく。
    """
    if not _is_allowed_base_url(config.base_url):
        return False, ERROR_BASE_URL
    path = f"/rest/api/3/project/{urllib.parse.quote(config.project_key, safe='')}"
    status, data = _send(config, "GET", path)
    if not _is_success(status):
        return False, _message_for_status(status)
    return True, str(data.get("name") or config.project_key)


def create_issue(
    config: JiraConfig,
    *,
    summary: str,
    description: str,
    labels: Iterable[str] = (),
    severity: str = "",
) -> tuple[bool, dict[str, Any]]:
    """Issue を 1 件起票する。成功時は issue_key / issue_url を返す。

    失敗は例外ではなく (False, {"error": 理由}) で返す。通知系（notifier.py）と
    同じ作法に揃え、呼び出し側が握りつぶしを書かなくて済むようにするため。
    """
    if not _is_allowed_base_url(config.base_url):
        return False, {"error": ERROR_BASE_URL}
    title = _trim(_clean(summary), _SUMMARY_MAX_LENGTH)
    if not title:
        return False, {"error": ERROR_EMPTY_SUMMARY}

    payload = {
        "fields": {
            "project": {"key": config.project_key},
            "issuetype": {"name": config.issue_type or DEFAULT_ISSUE_TYPE},
            "summary": title,
            "description": _adf_document(description),
            "labels": list(_merge_labels(labels, severity)),
        }
    }
    status, data = _send(config, "POST", "/rest/api/3/issue", payload)
    if not _is_success(status):
        return False, {"error": _message_for_status(status)}
    issue_key = str(data.get("key") or "")
    if not issue_key:
        return False, {"error": ERROR_UNEXPECTED_BODY}
    return True, {
        "issue_key": issue_key,
        "issue_url": f"{config.base_url.rstrip('/')}/browse/{issue_key}",
    }


def build_issue_from_defect(
    defect: Mapping[str, Any], domain: str
) -> tuple[str, str, tuple[str, ...]]:
    """defect 1 件から (summary, description, labels) を組む。引数は書き換えない。

    Jira 側で読む人は WebSpec2Doc を開いていない前提なので、重要度・状態・
    再現手順など「存在する情報だけ」を本文へ展開する。空欄の見出しは載せない。
    """
    summary = _trim(_clean(defect.get("summary", "")), _SUMMARY_MAX_LENGTH)
    lines: list[str] = [f"WebSpec2Doc で検出された不具合です（対象ドメイン: {_clean(domain)}）", ""]
    for key, label in _DESCRIPTION_FIELDS:
        value = _clean(defect.get(key, ""))
        if not value:
            continue
        if key == "severity":
            value = SEVERITY_LABELS.get(value, value)
        elif key == "state":
            value = STATE_LABELS.get(value, value)
        lines.append(f"{label}: {value}")
    description = _trim("\n".join(lines), _DESCRIPTION_MAX_LENGTH)
    labels = _merge_labels(("webspec2doc", _slug(domain)), _clean(defect.get("severity", "")))
    return summary, description, labels


# =========================================================================
# 内部ヘルパ
# =========================================================================
def _is_allowed_base_url(url: str) -> bool:
    """https の外部ホストのみ許可する（SSRF 防止）。"""
    try:
        parsed = urllib.parse.urlparse(_clean(url))
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    if not host or host in _BLOCKED_HOSTS:
        return False
    if host.startswith(_BLOCKED_HOST_PREFIXES):
        return False
    return not host.endswith(_BLOCKED_HOST_SUFFIXES)


def _auth_header(config: JiraConfig) -> str:
    """Jira Cloud は email:api_token の Basic 認証。"""
    raw = f"{config.email}:{config.api_token}".encode()
    return f"Basic {base64.b64encode(raw).decode('ascii')}"


def _send(
    config: JiraConfig, method: str, path: str, payload: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any]]:
    """Jira を 1 回叩き (HTTP ステータス, JSON) を返す。通信不能は status=0。

    ログにはメソッドとステータスだけ出す。URL 全体やトークンを出すと
    監査ログ・アプリログの双方に秘密値が残るため。
    """
    url = f"{config.base_url.rstrip('/')}{path}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Authorization": _auth_header(config), "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as response:  # nosec B310
            return int(getattr(response, "status", 0) or 0), _parse_json(response.read())
    except urllib.error.HTTPError as exc:
        logger.error("Jira API responded with an error: method=%s status=%s", method, exc.code)
        return int(exc.code), {}
    except (urllib.error.URLError, OSError, ValueError):
        logger.error("Jira API request failed: method=%s kind=network_error", method)
        return 0, {}


def _parse_json(raw: bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8", errors="replace") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _is_success(status: int) -> bool:
    return 200 <= status < 300


def _message_for_status(status: int) -> str:
    if status in (401, 403):
        return ERROR_AUTH
    if status == 404:
        return ERROR_NOT_FOUND
    return ERROR_UNREACHABLE


def _adf_document(text: str) -> dict[str, Any]:
    """本文を ADF（Atlassian Document Format）へ変換する。

    text ノードは改行を持てないため、行ごとに paragraph へ分ける。
    1 ノードに詰めると Jira 側で 400 になる。
    """
    lines = [
        line
        for line in _trim(str(text or ""), _DESCRIPTION_MAX_LENGTH).splitlines()
        if line.strip()
    ]
    if not lines:
        lines = ["（詳細なし）"]
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": line}]} for line in lines
        ],
    }


def _merge_labels(labels: Iterable[str], severity: str) -> tuple[str, ...]:
    """空・重複を除いた Jira ラベルを順序を保って返す。"""
    merged: list[str] = []
    for candidate in (*labels, _slug(severity)):
        value = _slug(candidate)
        if value and value not in merged:
            merged.append(value)
    return tuple(merged)


def _slug(value: str) -> str:
    """Jira のラベルは空白を含められないため英数字・ハイフンへ寄せる。"""
    return _trim(_NON_LABEL_RE.sub("-", _clean(value)).strip("-").lower(), _LABEL_MAX_LENGTH)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _trim(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit]
