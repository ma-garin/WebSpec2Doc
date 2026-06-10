from __future__ import annotations

import urllib.error
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from web.services.notifier import (
    NOTIFIER_EMAIL,
    NOTIFIER_SLACK,
    NOTIFIER_WEBHOOK,
    DriftNotification,
    NotifierConfig,
    build_notification,
    send_drift_notification,
)


# ─────────────────────── ダミー DiffResult ───────────────────────


@dataclass(frozen=True)
class _DummyDiffResult:
    """DiffResult の最小ダミー（実物への依存を避けるため）。"""

    added_pages: tuple
    removed_pages: tuple
    field_changes: tuple
    api_changes: tuple


def _make_diff(
    added: int = 2,
    removed: int = 1,
    fields: int = 3,
    apis: int = 0,
) -> _DummyDiffResult:
    return _DummyDiffResult(
        added_pages=tuple(range(added)),
        removed_pages=tuple(range(removed)),
        field_changes=tuple(range(fields)),
        api_changes=tuple(range(apis)),
    )


# ─────────────────────── build_notification ───────────────────────


def test_build_notification_from_diff_result() -> None:
    diff = _make_diff(added=2, removed=1, fields=3, apis=4)
    notif = build_notification(diff, "https://example.com", "output/diff_report.html")

    assert notif.site_url == "https://example.com"
    assert notif.added_pages == 2
    assert notif.removed_pages == 1
    assert notif.field_changes == 3
    assert notif.api_changes == 4
    assert notif.report_url == "output/diff_report.html"


# ─────────────────────── Slack ───────────────────────


def _make_slack_config() -> NotifierConfig:
    return NotifierConfig(
        notifier_type=NOTIFIER_SLACK,
        endpoint="https://hooks.slack.com/services/TXXXXXXXX/BXXXXXXXX/XXXXXXXX",
    )


def _sample_notification() -> DriftNotification:
    return DriftNotification(
        site_url="https://example.com",
        added_pages=1,
        removed_pages=0,
        field_changes=2,
        api_changes=0,
        report_url="output/diff_report.html",
    )


def test_send_drift_notification_slack_success(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_cm)
    mock_cm.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: mock_cm)

    result = send_drift_notification(_make_slack_config(), _sample_notification())

    assert result is True


def test_send_drift_notification_slack_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args: object, **kwargs: object) -> None:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _raise)

    result = send_drift_notification(_make_slack_config(), _sample_notification())

    assert result is False


# ─────────────────────── Webhook ───────────────────────


def test_send_drift_notification_webhook_success(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict] = []

    def _fake_urlopen(req: object, timeout: int = 10) -> MagicMock:
        import json as _json

        body = req.data  # type: ignore[attr-defined]
        captured.append(_json.loads(body))
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        return cm

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)

    config = NotifierConfig(
        notifier_type=NOTIFIER_WEBHOOK,
        endpoint="https://api.example.com/webhook",
    )
    notif = _sample_notification()
    result = send_drift_notification(config, notif)

    assert result is True
    assert len(captured) == 1
    payload = captured[0]
    assert payload["type"] == "drift_detected"
    assert payload["site_url"] == notif.site_url
    assert payload["added_pages"] == notif.added_pages


# ─────────────────────── Email ───────────────────────


def test_send_drift_notification_email_empty_to(monkeypatch: pytest.MonkeyPatch) -> None:
    # to_addresses が空なら smtplib に触れずに True を返す
    smtp_called = []

    def _fake_smtp_ssl(*args: object, **kwargs: object) -> MagicMock:
        smtp_called.append(True)
        return MagicMock()

    monkeypatch.setattr("smtplib.SMTP_SSL", _fake_smtp_ssl)

    config = NotifierConfig(
        notifier_type=NOTIFIER_EMAIL,
        endpoint="smtp.example.com",
        smtp_port=465,
        smtp_user="user@example.com",
        smtp_password="secret",
        from_address="noreply@example.com",
        to_addresses=(),  # 空
    )
    result = send_drift_notification(config, _sample_notification())

    assert result is True
    assert smtp_called == [], "to_addresses が空のとき SMTP 接続は不要"
