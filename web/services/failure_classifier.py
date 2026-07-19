from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from typing import Any

logger = logging.getLogger(__name__)

FAILURE_APP_CHANGE = "app_change"
FAILURE_TEST_ROT = "test_rot"
FAILURE_ENV_ISSUE = "env_issue"
# タイミング起因（非同期待ちの不足・遅延）。Luo et al.(FSE 2014) がフレイキーの
# 最大要因を Async Wait と特定しており、test_rot（ロケータ消失）と分けることで
# 「ロケータを直す」でなく「待ち方を直す/再実行する」という正しい対処に導く。
FAILURE_ASYNC_WAIT = "async_wait"
FAILURE_UNKNOWN = "unknown"

_ALL_FAILURE_TYPES = (
    FAILURE_APP_CHANGE,
    FAILURE_TEST_ROT,
    FAILURE_ENV_ISSUE,
    FAILURE_ASYNC_WAIT,
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

_ENV_SETUP_KEYWORDS = (
    "browserType.launch",
    "Executable doesn't exist",
)

_ACTION_ENV = "環境・認証状態を確認してください"
_ACTION_ENV_SETUP = (
    "Playwrightのブラウザ実行環境が未セットアップまたはバージョン不一致です。"
    "次回のAutoRun実行時に自動修復を試みます。改善しない場合は "
    "`npx playwright install chromium` を手動実行してください。"
)
_ACTION_ROT = "ロケータを更新してください（self-healing ロケータ候補を確認）"
_ACTION_ASYNC = (
    "タイミング起因の可能性が高い失敗です。単発なら再実行で解消するか確認し、"
    "再発するなら該当ステップの待機条件（表示待ち・通信完了待ち）を見直してください"
)
_ACTION_APP = "差分レポートを確認してください（仕様変更の可能性）"
_ACTION_UNKNOWN = "テストログを詳細確認してください"


@dataclass(frozen=True)
class FailureClassification:
    test_id: str
    failure_type: str
    confidence: float
    reason: str
    suggested_action: str
    count: int = 1
    affected_test_ids: tuple[str, ...] = ()


def _is_env_setup_error(error_message: str) -> bool:
    """Playwrightブラウザ未インストール・バージョン不一致による起動失敗かどうかを判定する。"""
    return any(kw in error_message for kw in _ENV_SETUP_KEYWORDS)


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


def _is_async_wait(error_message: str) -> bool:
    """非同期待ちの不足・遅延（タイミング起因）かどうかを判定する。

    「locator が見つからない」(test_rot) と違い、要素や条件の**状態待ちで
    時間切れ**になったものを拾う。
    """
    msg = error_message
    if "Timeout" not in msg and "timeout" not in msg:
        return False
    state_waits = (
        "waiting for element to be visible",
        "waiting for element to be enabled",
        "waiting for element to be stable",
        "waiting for navigation",
        "waiting for load state",
        "waiting for response",
        "waiting for request",
        "waiting for event",
        "waiting for function",
        "networkidle",
    )
    return any(kw in msg for kw in state_waits)


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
    if _is_env_setup_error(error_message):
        return FailureClassification(
            test_id=test_id,
            failure_type=FAILURE_ENV_ISSUE,
            confidence=0.95,
            reason="Playwrightのブラウザ実行環境が未セットアップまたはバージョン不一致です",
            suggested_action=_ACTION_ENV_SETUP,
        )
    if _is_env_issue(error_message):
        return FailureClassification(
            test_id=test_id,
            failure_type=FAILURE_ENV_ISSUE,
            confidence=0.9,
            reason="ネットワーク・サーバーエラーまたは認証切れと判定しました",
            suggested_action=_ACTION_ENV,
        )
    if _is_async_wait(error_message):
        return FailureClassification(
            test_id=test_id,
            failure_type=FAILURE_ASYNC_WAIT,
            confidence=0.8,
            reason="非同期処理の待ち時間切れ（タイミング起因）と判定しました",
            suggested_action=_ACTION_ASYNC,
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


def _normalize_error(error_message: str) -> str:
    """行番号・一時パス等の可変部分を除いた、重複判定用のキー文字列を作る。"""
    return re.sub(r"\d+", "#", error_message).strip()


def _collapse_duplicate_failures(
    items: list[tuple[FailureClassification, str]],
) -> list[FailureClassification]:
    """同一原因（同じ failure_type ＋ 同じエラー文言）で大量発生した失敗を1件に集約する。
    Playwrightのブラウザ未セットアップ等、根本原因が1つなのに数百件のテストが
    同一メッセージで失敗するケースで、UI上に意味のある単位で表示するための集約。"""
    groups: dict[tuple[str, str], list[tuple[FailureClassification, str]]] = {}
    order: list[tuple[str, str]] = []
    for classification, error in items:
        key = (classification.failure_type, _normalize_error(error))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((classification, error))

    collapsed: list[FailureClassification] = []
    for key in order:
        group = groups[key]
        if len(group) == 1:
            collapsed.append(group[0][0])
            continue
        first = group[0][0]
        test_ids = tuple(c.test_id for c, _ in group)
        collapsed.append(
            replace(
                first,
                test_id=f"{first.test_id} ほか{len(group) - 1}件",
                count=len(group),
                affected_test_ids=test_ids,
            )
        )
    return collapsed


def classify_failures(
    results: list[dict],
    diff_result: Any = None,
) -> list[FailureClassification]:
    """複数のテスト結果をまとめて分類する。
    results の各要素: {"test_id": str, "status": "failed"/"passed", "error": str}
    status が "failed" のもののみ処理する。同一原因の大量重複は1件に集約する。"""
    raw: list[tuple[FailureClassification, str]] = []
    for item in results:
        if item.get("status") != "failed":
            continue
        test_id = item.get("test_id", "")
        error = item.get("error", "")
        raw.append((classify_failure(test_id, error, diff_result), error))
    return _collapse_duplicate_failures(raw)


def summarize_classifications(
    classifications: list[FailureClassification],
) -> dict[str, int]:
    """分類結果をカテゴリ別件数でまとめる（集約済みエントリは count 分で加算）。
    戻り値例: {"app_change": 3, "test_rot": 1, "env_issue": 0, "unknown": 0}"""
    summary: dict[str, int] = {ft: 0 for ft in _ALL_FAILURE_TYPES}
    for c in classifications:
        if c.failure_type in summary:
            summary[c.failure_type] += c.count
        else:
            logger.warning("未知の failure_type: %s", c.failure_type)
    return summary
