"""フォーム到達クロール（テスト環境限定・明示オプトイン）。

登録・検索フォームの「先にある画面」へ到達し、カバレッジを本質的に上げる。
送信を伴うため、本システムの非送信原則に対する**明示的で監査可能な例外**として
設計する。既定では完全に無効。

安全設計（すべて満たさなければ送信しない）:
  1. 二重オプトイン: 環境変数 WEBSPEC2DOC_ALLOW_FORM_SUBMIT=1 かつ 明示フラグ
  2. 対象ホスト許可リスト必須
  3. 破壊的文言ボタン（削除/購入/決済 等）はスキップ
  4. 全送信を監査ログへ記録（値は記録しない）
  5. 入力値は安全な合成値のみ（実測制約準拠）
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

ENV_FLAG = "WEBSPEC2DOC_ALLOW_FORM_SUBMIT"

# 押してはいけないボタンの文言（部分一致・大文字小文字無視）。
_DESTRUCTIVE_TERMS = (
    "delete",
    "remove",
    "purchase",
    "buy",
    "pay",
    "checkout",
    "order",
    "subscribe",
    "decline",
    "cancel account",
    "unsubscribe",
    "削除",
    "購入",
    "支払",
    "決済",
    "注文",
    "退会",
    "解約",
    "課金",
)

# 安全な合成入力値（type別）。実測制約が使えない場合の既定。
_SAFE_VALUES = {
    "email": "test@example.com",
    "tel": "09012345678",
    "number": "1",
    "date": "2026-01-01",
    "url": "https://example.com",
    "password": "Test1234!",
    "text": "テスト入力",
    "search": "テスト",
}


def form_submit_enabled(explicit_flag: bool) -> bool:
    """二重オプトイン（環境変数＋明示フラグ）が両方成立しているか。"""
    env_ok = os.environ.get(ENV_FLAG, "").strip() in {"1", "true", "yes", "on"}
    return bool(env_ok and explicit_flag)


def host_allowed(url: str, host_allowlist: list[str] | tuple[str, ...]) -> bool:
    """URL のホストが許可リストに含まれるか。許可リストが空なら常に不許可。"""
    if not host_allowlist:
        return False
    host = urlparse(url).hostname or ""
    return host in set(host_allowlist)


def is_destructive_button(text: str) -> bool:
    """破壊的操作の疑いがあるボタン文言か。"""
    lowered = str(text).lower()
    return any(term in lowered for term in _DESTRUCTIVE_TERMS)


def safe_value_for(field: dict[str, Any]) -> str:
    """フォーム項目に入れる安全な合成値を返す（実測 options があれば先頭を使う）。"""
    options = [str(v) for v in field.get("options", []) if str(v)]
    if options:
        return options[0]
    field_type = str(field.get("field_type", "text"))
    return _SAFE_VALUES.get(field_type, _SAFE_VALUES["text"])


def plan_form_submission(form: dict[str, Any], submit_text: str) -> dict[str, Any] | None:
    """フォーム送信計画を作る。送信すべきでない場合は None。

    実際の送信はしない（計画のみ）。呼び出し側が安全確認後に実行する。
    """
    if is_destructive_button(submit_text):
        logger.info("破壊的文言のため送信をスキップ: %r", submit_text)
        return None
    fills = {}
    for field in form.get("fields", []):
        if not isinstance(field, dict):
            continue
        name = str(field.get("name", ""))
        field_type = str(field.get("field_type", ""))
        if not name or field_type in ("hidden", "submit", "button", "file", "image"):
            continue
        fills[name] = safe_value_for(field)
    return {
        "action": str(form.get("action", "")),
        "method": str(form.get("method", "get")),
        "fills": fills,
        "submit_text": submit_text,
    }


def audit_record_for(url: str, plan: dict[str, Any]) -> dict[str, Any]:
    """送信の監査レコードを作る（**値は含めない**・フィールド名のみ）。"""
    return {
        "event": "form_submitted",
        "url": url,
        "method": plan.get("method", ""),
        "action": plan.get("action", ""),
        "field_names": sorted(plan.get("fills", {}).keys()),
    }
