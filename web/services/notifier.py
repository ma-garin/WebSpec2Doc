from __future__ import annotations

import dataclasses
import json
import logging
import smtplib
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.mime.text import MIMEText
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.diff.differ import DiffResult

logger = logging.getLogger(__name__)

NOTIFIER_SLACK = "slack"
NOTIFIER_EMAIL = "email"
NOTIFIER_WEBHOOK = "webhook"

_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class DriftNotification:
    site_url: str
    added_pages: int
    removed_pages: int
    field_changes: int
    api_changes: int
    report_url: str  # diff_report.html への相対 or 絶対 URL


@dataclass(frozen=True)
class NotifierConfig:
    notifier_type: str  # NOTIFIER_SLACK / NOTIFIER_EMAIL / NOTIFIER_WEBHOOK
    endpoint: str       # Slack Webhook URL / SMTP host / Webhook URL
    # メール専用（slack/webhook では無視）
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    from_address: str = ""
    to_addresses: tuple[str, ...] = ()


def send_drift_notification(config: NotifierConfig, notification: DriftNotification) -> bool:
    """通知タイプに応じてドリフト通知を送信する。失敗時は False を返す。"""
    dispatch = {
        NOTIFIER_SLACK: _send_slack,
        NOTIFIER_EMAIL: _send_email,
        NOTIFIER_WEBHOOK: _send_webhook,
    }
    handler = dispatch.get(config.notifier_type)
    if handler is None:
        logger.error("Unknown notifier_type: %s", config.notifier_type)
        return False
    try:
        return handler(config, notification)
    except Exception:
        logger.error("Unexpected error sending notification", exc_info=True)
        return False


def _build_text(notification: DriftNotification) -> str:
    return (
        f"⚠️ 仕様ドリフト検知: {notification.site_url}\n"
        f"追加: {notification.added_pages}画面 / "
        f"削除: {notification.removed_pages}画面 / "
        f"フィールド変化: {notification.field_changes}件\n"
        f"レポート: {notification.report_url}"
    )


def _post_json(url: str, payload: dict[str, Any]) -> bool:
    body = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS):
            return True
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        logger.error("HTTP/URL error posting to %s: %s", url, exc)
        return False


def _send_slack(config: NotifierConfig, notification: DriftNotification) -> bool:
    payload = {"text": _build_text(notification)}
    return _post_json(config.endpoint, payload)


def _send_webhook(config: NotifierConfig, notification: DriftNotification) -> bool:
    payload = dataclasses.asdict(notification)
    payload["type"] = "drift_detected"
    return _post_json(config.endpoint, payload)


def _send_email(config: NotifierConfig, notification: DriftNotification) -> bool:
    # to_addresses が空の場合は送信対象なしとみなして正常終了
    if not config.to_addresses:
        return True

    subject = f"[WebSpec2Doc] 仕様ドリフト検知: {notification.site_url}"
    body = _build_text(notification)

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = config.from_address
    msg["To"] = ", ".join(config.to_addresses)

    try:
        with smtplib.SMTP_SSL(config.endpoint, config.smtp_port) as smtp:
            smtp.login(config.smtp_user, config.smtp_password)
            smtp.sendmail(config.from_address, list(config.to_addresses), msg.as_string())
        return True
    except (smtplib.SMTPException, OSError) as exc:
        logger.error("Email send failed: %s", exc)
        return False


def build_notification(
    diff_result: Any,
    site_url: str,
    report_url: str,
) -> DriftNotification:
    """DiffResult から DriftNotification を組み立てる。

    diff_result の型を Any にしているのは、differ.py が別エージェントによる
    並行編集中の場合に静的 import が失敗するリスクを避けるため。
    """
    return DriftNotification(
        site_url=site_url,
        added_pages=len(diff_result.added_pages),
        removed_pages=len(diff_result.removed_pages),
        field_changes=len(diff_result.field_changes),
        api_changes=len(diff_result.api_changes),
        report_url=report_url,
    )
