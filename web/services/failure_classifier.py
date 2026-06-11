from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

FAILURE_APP_CHANGE = "app_change"
FAILURE_TEST_ROT = "test_rot"
FAILURE_ENV_ISSUE = "env_issue"
FAILURE_UNKNOWN = "unknown"

_ALL_FAILURE_TYPES = (
    FAILURE_APP_CHANGE,
    FAILURE_TEST_ROT,
    FAILURE_ENV_ISSUE,
    FAILURE_UNKNOWN,
)

_ENV_KEYWORDS = (
    "net::ERR_",
    "ERR_CONNECTION",
    "ECONNREFUSED",
    "502",
    "503",
    "504",
)

_AUTH_KEYWORDS = (
    "401",
    "403",
    "session",
    "login",
    "認証",
)

_ACTION_ENV = "環境・認証状態を確認してください"
_ACTION_ROT = "ロケータを更新してください（self-healing ロケータ候補を確認）"
_ACTION_APP = "差分レポートを確認してください（仕様変更の可能性）"
_ACTION_UNKNOWN = "テストログを詳細確認してください"


@dataclass(frozen=True)
class FailureClassification:
    test_id: str
    failure_type: str
    confidence: float
    reason: str
    suggested_action: str


def _is_env_issue(error_message: str) -> bool:
    """ネットワーク・サーバーエラー・認証切れかどうかを判定する。"""
    msg = error_message
    for kw in _ENV_KEYWORDS:
        if kw in msg:
            return True
    is_timeout = "Timeout" in msg and "waiting for" not in msg
    if is_timeout:
        return True
    return any(kw in msg for kw in _AUTH_KEYWORDS)


def _is_test_rot(error_message: str) -> bool:
    """ロケータ変化・タイミング問題かどうかを判定する。"""
    msg = error_message
    if "locator" in msg and "not found" in msg:
        return True
    if "resolved to" in msg and "elements" in msg:
        return True
    if "waiting for" in msg and "locator" in msg:
        return True
    if "strict mode violation" in msg:
        return True
    if "Element is outside of the viewport" in msg:
        return True
    return False


def _is_app_change(error_message: str, diff_result: Any) -> bool:
    """アプリの仕様変更が原因かどうかを判定する。"""
    msg = error_message
    has_diff = diff_result is not None and getattr(diff_result, "has_changes", False)
    if has_diff and "expect" in msg and ("received" in msg or "expected" in msg):
        return True
    if "toHaveURL" in msg and "expected" in msg:
        return True
    if "toBeVisible" in msg and "expected to be visible" in msg:
        return True
    return False


def classify_failure(
    test_id: str,
    error_message: str,
    diff_result: Any = None,
) -> FailureClassification:
    """Playwright テスト失敗のエラーメッセージとドリフト情報から失敗を分類する。"""
    if _is_env_issue(error_message):
        return FailureClassification(
            test_id=test_id,
            failure_type=FAILURE_ENV_ISSUE,
            confidence=0.9,
            reason="ネットワーク・サーバーエラーまたは認証切れと判定しました",
            suggested_action=_ACTION_ENV,
        )
    if _is_test_rot(error_message):
        return FailureClassification(
            test_id=test_id,
            failure_type=FAILURE_TEST_ROT,
            confidence=0.85,
            reason="ロケータの変化またはタイミング問題と判定しました",
            suggested_action=_ACTION_ROT,
        )
    if _is_app_change(error_message, diff_result):
        return FailureClassification(
            test_id=test_id,
            failure_type=FAILURE_APP_CHANGE,
            confidence=0.8,
            reason="アプリの仕様変更（ドリフト）が原因と判定しました",
            suggested_action=_ACTION_APP,
        )
    logger.debug("test_id=%s は分類不能（unknown）", test_id)
    return FailureClassification(
        test_id=test_id,
        failure_type=FAILURE_UNKNOWN,
        confidence=0.5,
        reason="既知パターンに該当しないため分類できませんでした",
        suggested_action=_ACTION_UNKNOWN,
    )


def classify_failures(
    results: list[dict],
    diff_result: Any = None,
) -> list[FailureClassification]:
    """複数のテスト結果をまとめて分類する。
    results の各要素: {"test_id": str, "status": "failed"/"passed", "error": str}
    status が "failed" のもののみ処理する。"""
    classifications: list[FailureClassification] = []
    for item in results:
        if item.get("status") != "failed":
            continue
        test_id = item.get("test_id", "")
        error = item.get("error", "")
        classifications.append(classify_failure(test_id, error, diff_result))
    return classifications


def summarize_classifications(
    classifications: list[FailureClassification],
) -> dict[str, int]:
    """分類結果をカテゴリ別件数でまとめる。
    戻り値例: {"app_change": 3, "test_rot": 1, "env_issue": 0, "unknown": 0}"""
    summary: dict[str, int] = {ft: 0 for ft in _ALL_FAILURE_TYPES}
    for c in classifications:
        if c.failure_type in summary:
            summary[c.failure_type] += 1
        else:
            logger.warning("未知の failure_type: %s", c.failure_type)
    return summary
