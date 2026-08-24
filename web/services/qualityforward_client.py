"""QualityForward（ベリサーブのテスト管理ツール）API v2 のクライアント。

現時点で行うのは「プロジェクト API キーの疎通確認」だけ。
テスト結果登録（POST /test_results）は必須パラメータが公開仕様に記載されておらず未実装。
推測でパラメータを組んで送ると相手のテスト管理データを壊しうるため、仕様が確認できるまで作らない。

外向き HTTP は notion_client.py と同じ方式（urllib + timeout=10 + 例外を握って失敗を返す）
に揃える。requests を足すと依存が増えるうえ、「秘密値をログへ出さない」という
既存の失敗時の作法とずれるため。
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10
_API_BASE_URL = "https://cloud.veriserve.co.jp/api/v2"

ENV_API_KEY = "QUALITYFORWARD_API_KEY"

# QualityForward のレート制限は同一 API キーで 1 秒あたり 1 リクエスト（超過で 429）。
# 連打を time.sleep で待たせるとワーカーがふさがり画面全体が固まるため、待たずに断る。
_MIN_REQUEST_INTERVAL_SECONDS = 1.0
_last_request_at = 0.0

# 失敗理由は必ず定型文へ丸める。API の応答本文をそのまま返すと
# 内部の識別子やテナント情報が画面へ漏れるため。
ERROR_AUTH = "API キーが無効です"
ERROR_NOT_FOUND = "プロジェクトが見つかりません"
ERROR_RATE_LIMIT = "リクエスト数の上限に達しました（1 秒あたり 1 回まで）"
ERROR_UNREACHABLE = "接続できませんでした"
ERROR_TOO_SOON = "前回の確認から 1 秒以上あけてください"


@dataclass(frozen=True)
class QualityForwardConfig:
    """QualityForward 接続設定。生成後は書き換えない（秘密値の取り違えを防ぐため）。"""

    api_key: str


def qualityforward_config_from_env(env: Mapping[str, str]) -> QualityForwardConfig | None:
    """.env の値から設定を組む。API キーが無ければ None。

    「部分的に設定済み」を有効扱いにすると、使う段になって初めて失敗して
    原因が分からなくなる。未設定は入口で None に倒す。
    """
    api_key = _clean(env.get(ENV_API_KEY, ""))
    if not api_key:
        return None
    return QualityForwardConfig(api_key=api_key)


def verify_connection(config: QualityForwardConfig) -> tuple[bool, str]:
    """プロジェクト情報を 1 件取得して接続確認する。成功時はプロジェクト名とテナント名を返す。

    保存前に確かめられないと、連携が必要になった時点で初めて誤設定
    （キーの打ち間違い・失効）に気づくことになる。
    """
    if not _may_request_now():
        return False, ERROR_TOO_SOON
    status, data = _send(config, "GET", "/current_project")
    if not _is_success(status):
        return False, _message_for_status(status)
    return True, _project_label(data)


# =========================================================================
# 内部ヘルパ
# =========================================================================
def _may_request_now() -> bool:
    """直前の送信から 1 秒経っていれば True。経っていなければ送らずに断る。

    レート制限（1 req/秒）を自分の側で守るための間引き。待機（time.sleep）はしない
    （リクエストを詰まらせないため）。
    """
    global _last_request_at
    now = time.monotonic()
    if now - _last_request_at < _MIN_REQUEST_INTERVAL_SECONDS:
        return False
    _last_request_at = now
    return True


def _send(config: QualityForwardConfig, method: str, path: str) -> tuple[int, dict[str, Any]]:
    """QualityForward を 1 回叩き (HTTP ステータス, JSON) を返す。通信不能は status=0。

    認証はヘッダの Bearer で行う（クエリパラメータでも渡せるが、URL に載せると
    アクセスログへ API キーが残るため使わない）。
    ログにはメソッドとステータスだけ出す。URL 全体や API キーは出さない。
    """
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Accept": "application/json",
    }
    req = urllib.request.Request(f"{_API_BASE_URL}{path}", headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as response:  # nosec B310
            return int(getattr(response, "status", 0) or 0), _parse_json(response.read())
    except urllib.error.HTTPError as exc:
        logger.error("QualityForward error: method=%s status=%s", method, exc.code)
        return int(exc.code), {}
    except (urllib.error.URLError, OSError, ValueError):
        logger.error("QualityForward API request failed: method=%s kind=network_error", method)
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


def _project_label(data: Mapping[str, Any]) -> str:
    """プロジェクト名（取れればテナント名も）を組む。無名のプロジェクトもあるため空文字を許す。"""
    name = _clean(data.get("name", ""))
    tenant = data.get("tenant")
    tenant_name = _clean(tenant.get("name", "")) if isinstance(tenant, Mapping) else ""
    if name and tenant_name:
        return f"{name}（テナント: {tenant_name}）"
    return name


def _clean(value: Any) -> str:
    return str(value or "").strip()
