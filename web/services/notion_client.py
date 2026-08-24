"""Notion API（2022-06-28）への一方向連携クライアント。

WebSpec2Doc から Notion データベースへ「ページを作る」だけの片方向に限定する。
取り込み（Notion → WebSpec2Doc）を実装すると不具合の状態の正本がどちらか曖昧になり、
運用者がどちらを信じるべきか判断できなくなるため。

外向き HTTP は jira_client.py と同じ方式（urllib + timeout=10 + 例外を握って失敗を返す）
に揃える。requests を足すと依存が増えるうえ、「秘密値をログへ出さない」という
既存の失敗時の作法とずれるため。
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from web.env_store import _read_env
from web.services.defect_store import SEVERITY_LABELS, STATE_LABELS

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10
_API_BASE_URL = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"
_TITLE_MAX_LENGTH = 80
# Notion の rich_text 1 要素は 2000 文字、children は 100 ブロックが上限。
# 超過すると 400 になるため送信前に自分で丸める。
_TEXT_MAX_LENGTH = 2000
_BLOCK_MAX_COUNT = 100

ENV_API_TOKEN = "NOTION_API_TOKEN"
ENV_DATABASE_ID = "NOTION_DATABASE_ID"
ENV_TITLE_PROPERTY = "NOTION_TITLE_PROPERTY"

# Notion のデータベースは「タイトル型の列」が必ず 1 つあり、そこを埋めないと
# ページを作れない。その列名はワークスペースごとに任意（既定の英語 UI では "Name"）で
# API からは事前に確定できないため、既定を "Name" とし、
# 合わない場合は .env の NOTION_TITLE_PROPERTY で上書きできるようにする。
DEFAULT_TITLE_PROPERTY = "Name"

# database_id はパスへ埋め込むため、UUID の文字種だけを許可する（パス注入防止）。
_DATABASE_ID_RE = re.compile(r"^[0-9a-fA-F-]{32,36}$")

# 失敗理由は必ず定型文へ丸める。Notion の応答本文をそのまま返すと
# 内部の識別子やワークスペース情報が画面へ漏れるため。
ERROR_DATABASE_ID = "データベース ID の形式が不正です"
ERROR_AUTH = "トークンが無効です"
ERROR_NOT_FOUND = (
    "データベースが見つかりません（連携にデータベースを共有していない可能性があります）"
)
ERROR_RATE_LIMIT = "リクエストが多すぎます"
ERROR_UNREACHABLE = "接続できませんでした"
ERROR_UNEXPECTED_BODY = "Notion の応答を解釈できませんでした"
ERROR_EMPTY_TITLE = "タイトルが空のためページを作成できません"

# 本文に載せるフィールドと日本語見出し。
# defect の実体はドメインごとに増減するため、存在するキーだけを拾う。
_BODY_FIELDS: tuple[tuple[str, str], ...] = (
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
class NotionConfig:
    """Notion 接続設定。生成後は書き換えない（秘密値の取り違えを防ぐため）。"""

    api_token: str
    database_id: str


def notion_config_from_env(env: Mapping[str, str]) -> NotionConfig | None:
    """.env の値から設定を組む。必須項目が 1 つでも欠けたら None。

    「部分的に設定済み」を有効扱いにすると、ページ作成時に初めて失敗して
    原因が分からなくなる。未設定は入口で None に倒す。
    """
    api_token = _clean(env.get(ENV_API_TOKEN, ""))
    database_id = _clean(env.get(ENV_DATABASE_ID, ""))
    if not (api_token and database_id):
        return None
    return NotionConfig(api_token=api_token, database_id=database_id)


def verify_connection(config: NotionConfig) -> tuple[bool, str]:
    """データベースを 1 件取得して接続確認する。成功時はデータベース名を返す。

    保存前に確かめられないと、連携が必要になった時点で初めて誤設定
    （トークン失効・データベース未共有）に気づくことになる。
    """
    if not _is_valid_database_id(config.database_id):
        return False, ERROR_DATABASE_ID
    status, data = _send(config, "GET", f"/databases/{config.database_id}")
    if not _is_success(status):
        return False, _message_for_status(status)
    return True, _database_title(data)


def create_page(
    config: NotionConfig,
    *,
    title: str,
    properties: Mapping[str, Any],
    blocks: Sequence[Mapping[str, Any]] = (),
) -> tuple[bool, dict[str, Any]]:
    """データベース配下にページを 1 件作る。成功時は page_id / page_url を返す。

    失敗は例外ではなく (False, {"error": 理由}) で返す。jira_client と同じ作法に揃え、
    呼び出し側が握りつぶしを書かなくて済むようにするため。
    """
    if not _is_valid_database_id(config.database_id):
        return False, {"error": ERROR_DATABASE_ID}
    if not _trim(_clean(title), _TITLE_MAX_LENGTH):
        return False, {"error": ERROR_EMPTY_TITLE}

    payload = {
        "parent": {"database_id": config.database_id},
        "properties": dict(properties),
        "children": [dict(block) for block in blocks][:_BLOCK_MAX_COUNT],
    }
    status, data = _send(config, "POST", "/pages", payload)
    if not _is_success(status):
        return False, {"error": _message_for_status(status)}
    page_id = str(data.get("id") or "")
    if not page_id:
        return False, {"error": ERROR_UNEXPECTED_BODY}
    return True, {"page_id": page_id, "page_url": str(data.get("url") or "")}


def build_page_from_defect(
    defect: Mapping[str, Any], domain: str
) -> tuple[str, dict[str, Any], tuple[dict[str, Any], ...]]:
    """defect 1 件から (title, properties, blocks) を組む。引数は書き換えない。

    Notion 側で読む人は WebSpec2Doc を開いていない前提なので、重要度・状態・
    再現手順など「存在する情報だけ」を本文へ展開する。空欄の見出しは載せない。
    """
    title = _trim(_clean(defect.get("summary", "")), _TITLE_MAX_LENGTH)
    properties = {
        _title_property_name(): {"title": [{"text": {"content": title}}]},
    }

    lines: list[str] = [f"WebSpec2Doc で検出された不具合です（対象ドメイン: {_clean(domain)}）"]
    for key, label in _BODY_FIELDS:
        value = _clean(defect.get(key, ""))
        if not value:
            continue
        if key == "severity":
            value = SEVERITY_LABELS.get(value, value)
        elif key == "state":
            value = STATE_LABELS.get(value, value)
        lines.append(f"{label}: {value}")
    blocks = tuple(_paragraph_block(line) for line in lines[:_BLOCK_MAX_COUNT])
    return title, properties, blocks


# =========================================================================
# 内部ヘルパ
# =========================================================================
def _is_valid_database_id(database_id: str) -> bool:
    """UUID の文字種だけを許可する。宛先は api.notion.com 固定だが、
    設定値がそのままパスへ入るため `../` 等でパスを差し替えられないようにする。
    """
    return bool(_DATABASE_ID_RE.match(_clean(database_id)))


def _title_property_name() -> str:
    """タイトル列の名前を解決する。.env の読み出しに失敗しても既定値で動かす。"""
    try:
        return _clean(_read_env().get(ENV_TITLE_PROPERTY, "")) or DEFAULT_TITLE_PROPERTY
    except (OSError, ValueError):
        logger.warning("Failed to read the Notion title property name; using the default.")
        return DEFAULT_TITLE_PROPERTY


def _send(
    config: NotionConfig, method: str, path: str, payload: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any]]:
    """Notion を 1 回叩き (HTTP ステータス, JSON) を返す。通信不能は status=0。

    ログにはメソッドとステータスだけ出す。URL 全体やトークンを出すと
    監査ログ・アプリログの双方に秘密値が残るため。
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {
        "Authorization": f"Bearer {config.api_token}",
        "Notion-Version": _NOTION_VERSION,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(
        f"{_API_BASE_URL}{path}", data=body, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as response:  # nosec B310
            return int(getattr(response, "status", 0) or 0), _parse_json(response.read())
    except urllib.error.HTTPError as exc:
        logger.error("Notion API responded with an error: method=%s status=%s", method, exc.code)
        return int(exc.code), {}
    except (urllib.error.URLError, OSError, ValueError):
        logger.error("Notion API request failed: method=%s kind=network_error", method)
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
    if status == 429:
        return ERROR_RATE_LIMIT
    return ERROR_UNREACHABLE


def _database_title(data: Mapping[str, Any]) -> str:
    """データベース名を title[0].plain_text から取る。無題のデータベースもあるため空文字を許す。"""
    title = data.get("title")
    if not isinstance(title, list) or not title:
        return ""
    head = title[0]
    return _clean(head.get("plain_text", "")) if isinstance(head, Mapping) else ""


def _paragraph_block(text: str) -> dict[str, Any]:
    """1 行を paragraph ブロックへ変換する。改行はブロック側で表現する。"""
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": _trim(text, _TEXT_MAX_LENGTH)}}]
        },
    }


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _trim(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit]
