from __future__ import annotations

import pytest
from web.services.failure_classifier import (
    FAILURE_APP_CHANGE,
    FAILURE_ENV_ISSUE,
    FAILURE_TEST_ROT,
    FAILURE_UNKNOWN,
    FailureClassification,
    classify_failure,
    classify_failures,
    summarize_classifications,
)

# ─────────────────────── classify_failure ───────────────────────


def test_classify_failure_env_issue_network_error() -> None:
    result = classify_failure("TC001", "net::ERR_CONNECTION_REFUSED")
    assert result.failure_type == FAILURE_ENV_ISSUE
    assert result.confidence >= 0.8


def test_classify_failure_env_issue_err_connection() -> None:
    result = classify_failure("TC001", "ERR_CONNECTION timeout")
    assert result.failure_type == FAILURE_ENV_ISSUE


def test_classify_failure_env_issue_econnrefused() -> None:
    result = classify_failure("TC001", "ECONNREFUSED 127.0.0.1:8765")
    assert result.failure_type == FAILURE_ENV_ISSUE


def test_classify_failure_env_issue_502() -> None:
    result = classify_failure("TC001", "502 Bad Gateway")
    assert result.failure_type == FAILURE_ENV_ISSUE


def test_classify_failure_env_issue_503() -> None:
    result = classify_failure("TC001", "503 Service Unavailable")
    assert result.failure_type == FAILURE_ENV_ISSUE


def test_classify_failure_env_issue_504() -> None:
    result = classify_failure("TC001", "504 Gateway Timeout")
    assert result.failure_type == FAILURE_ENV_ISSUE


def test_classify_failure_env_issue_timeout_without_waiting_for() -> None:
    result = classify_failure("TC001", "Timeout exceeded for page load")
    assert result.failure_type == FAILURE_ENV_ISSUE


def test_classify_failure_env_issue_401() -> None:
    result = classify_failure("TC001", "Request failed with status 401")
    assert result.failure_type == FAILURE_ENV_ISSUE


def test_classify_failure_env_issue_403() -> None:
    result = classify_failure("TC001", "403 Forbidden")
    assert result.failure_type == FAILURE_ENV_ISSUE


def test_classify_failure_env_issue_session() -> None:
    result = classify_failure("TC001", "session expired")
    assert result.failure_type == FAILURE_ENV_ISSUE


def test_classify_failure_env_issue_login() -> None:
    result = classify_failure("TC001", "login required")
    assert result.failure_type == FAILURE_ENV_ISSUE


def test_classify_failure_env_issue_auth_japanese() -> None:
    result = classify_failure("TC001", "認証エラーが発生しました")
    assert result.failure_type == FAILURE_ENV_ISSUE


def test_classify_failure_test_rot_locator_not_found() -> None:
    result = classify_failure("TC002", "locator not found: '#submit-btn'")
    assert result.failure_type == FAILURE_TEST_ROT


def test_classify_failure_test_rot_resolved_to_elements() -> None:
    result = classify_failure("TC002", "resolved to 3 elements in strict mode")
    assert result.failure_type == FAILURE_TEST_ROT


def test_classify_failure_test_rot_waiting_for_locator() -> None:
    result = classify_failure("TC002", "waiting for locator('.submit') to be visible")
    assert result.failure_type == FAILURE_TEST_ROT


def test_classify_failure_test_rot_strict_mode_violation() -> None:
    result = classify_failure("TC002", "strict mode violation: locator('.btn') resolved to 2 elements")
    assert result.failure_type == FAILURE_TEST_ROT


def test_classify_failure_test_rot_outside_viewport() -> None:
    result = classify_failure("TC002", "Element is outside of the viewport")
    assert result.failure_type == FAILURE_TEST_ROT


def test_classify_failure_test_rot_confidence() -> None:
    result = classify_failure("TC002", "locator not found: '#btn'")
    assert result.confidence == 0.85


def test_classify_failure_timeout_with_waiting_for_is_not_env_issue() -> None:
    """ロケータ待機タイムアウトは env_issue ではなく test_rot になる。"""
    result = classify_failure("TC002", "Timeout waiting for locator('#submit')")
    assert result.failure_type == FAILURE_TEST_ROT


def test_classify_failure_app_change_with_diff() -> None:
    class _FakeDiff:
        has_changes = True

    result = classify_failure(
        "TC003",
        "expect(page).toHaveURL expected https://a.com received https://b.com",
        _FakeDiff(),
    )
    assert result.failure_type == FAILURE_APP_CHANGE


def test_classify_failure_app_change_to_have_url() -> None:
    result = classify_failure("TC003", "toHaveURL expected https://old.com")
    assert result.failure_type == FAILURE_APP_CHANGE


def test_classify_failure_app_change_to_be_visible() -> None:
    result = classify_failure("TC003", "toBeVisible expected to be visible but was not")
    assert result.failure_type == FAILURE_APP_CHANGE


def test_classify_failure_app_change_diff_no_changes_not_classified() -> None:
    """diff_result.has_changes が False のとき、expect/received だけでは app_change にならない。"""
    class _FakeDiffNoChange:
        has_changes = False

    result = classify_failure(
        "TC003",
        "expect(value) received something expected something else",
        _FakeDiffNoChange(),
    )
    # toHaveURL / toBeVisible を含まず diff なし → unknown
    assert result.failure_type == FAILURE_UNKNOWN


def test_classify_failure_app_change_confidence() -> None:
    result = classify_failure("TC003", "toHaveURL expected https://example.com")
    assert result.confidence == 0.8


def test_classify_failure_unknown_when_no_match() -> None:
    result = classify_failure("TC004", "some weird error XYZ")
    assert result.failure_type == FAILURE_UNKNOWN


def test_classify_failure_unknown_confidence() -> None:
    result = classify_failure("TC004", "some weird error XYZ")
    assert result.confidence == 0.5


def test_classify_failure_unknown_has_suggested_action() -> None:
    result = classify_failure("TC004", "some weird error XYZ")
    assert result.suggested_action != ""


def test_classify_failure_returns_frozen_dataclass() -> None:
    result = classify_failure("TC001", "net::ERR_CONNECTION_REFUSED")
    assert isinstance(result, FailureClassification)
    with pytest.raises((AttributeError, TypeError)):
        result.failure_type = "modified"  # type: ignore[misc]


def test_classify_failure_test_id_preserved() -> None:
    result = classify_failure("MY_TEST_42", "net::ERR_CONNECTION_REFUSED")
    assert result.test_id == "MY_TEST_42"


# ─────────────────────── classify_failures ───────────────────────


def test_classify_failures_only_processes_failed() -> None:
    results = [
        {"test_id": "TC001", "status": "passed", "error": ""},
        {"test_id": "TC002", "status": "failed", "error": "net::ERR_CONNECTION_REFUSED"},
    ]
    classifications = classify_failures(results)
    assert len(classifications) == 1
    assert classifications[0].test_id == "TC002"


def test_classify_failures_empty_results() -> None:
    assert classify_failures([]) == []


def test_classify_failures_all_passed() -> None:
    results = [
        {"test_id": "TC001", "status": "passed", "error": ""},
        {"test_id": "TC002", "status": "passed", "error": ""},
    ]
    assert classify_failures(results) == []


def test_classify_failures_multiple_failures() -> None:
    results = [
        {"test_id": "TC001", "status": "failed", "error": "net::ERR_CONNECTION_REFUSED"},
        {"test_id": "TC002", "status": "failed", "error": "locator not found: '#btn'"},
        {"test_id": "TC003", "status": "failed", "error": "some weird error XYZ"},
    ]
    classifications = classify_failures(results)
    assert len(classifications) == 3
    types = [c.failure_type for c in classifications]
    assert types[0] == FAILURE_ENV_ISSUE
    assert types[1] == FAILURE_TEST_ROT
    assert types[2] == FAILURE_UNKNOWN


def test_classify_failures_passes_diff_result() -> None:
    class _FakeDiff:
        has_changes = True

    results = [
        {
            "test_id": "TC001",
            "status": "failed",
            "error": "toHaveURL expected https://example.com",
        }
    ]
    classifications = classify_failures(results, _FakeDiff())
    assert classifications[0].failure_type == FAILURE_APP_CHANGE


# ─────────────────────── summarize_classifications ───────────────────────


def test_summarize_classifications() -> None:
    base = FailureClassification("x", FAILURE_APP_CHANGE, 0.8, "test", "action")
    summary = summarize_classifications([
        base,
        FailureClassification("y", FAILURE_TEST_ROT, 0.85, "test", "action"),
        FailureClassification("z", FAILURE_APP_CHANGE, 0.8, "test", "action"),
    ])
    assert summary[FAILURE_APP_CHANGE] == 2
    assert summary[FAILURE_TEST_ROT] == 1


def test_summarize_classifications_empty() -> None:
    summary = summarize_classifications([])
    assert summary == {
        FAILURE_APP_CHANGE: 0,
        FAILURE_TEST_ROT: 0,
        FAILURE_ENV_ISSUE: 0,
        FAILURE_UNKNOWN: 0,
    }


def test_summarize_classifications_all_types() -> None:
    classifications = [
        FailureClassification("a", FAILURE_APP_CHANGE, 0.8, "r", "act"),
        FailureClassification("b", FAILURE_TEST_ROT, 0.85, "r", "act"),
        FailureClassification("c", FAILURE_ENV_ISSUE, 0.9, "r", "act"),
        FailureClassification("d", FAILURE_UNKNOWN, 0.5, "r", "act"),
        FailureClassification("e", FAILURE_APP_CHANGE, 0.8, "r", "act"),
    ]
    summary = summarize_classifications(classifications)
    assert summary[FAILURE_APP_CHANGE] == 2
    assert summary[FAILURE_TEST_ROT] == 1
    assert summary[FAILURE_ENV_ISSUE] == 1
    assert summary[FAILURE_UNKNOWN] == 1


def test_summarize_classifications_returns_all_keys_even_if_zero() -> None:
    summary = summarize_classifications([
        FailureClassification("a", FAILURE_UNKNOWN, 0.5, "r", "act"),
    ])
    assert FAILURE_APP_CHANGE in summary
    assert FAILURE_TEST_ROT in summary
    assert FAILURE_ENV_ISSUE in summary
    assert FAILURE_UNKNOWN in summary
    assert summary[FAILURE_UNKNOWN] == 1
    assert summary[FAILURE_APP_CHANGE] == 0
