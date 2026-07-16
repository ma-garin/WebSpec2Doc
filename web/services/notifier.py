from __future__ import annotations

import dataclasses
import json
import logging
import os
import smtplib
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.mime.text import MIMEText
from typing import TYPE_CHECKING, Any

from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

NOTIFIER_SLACK = "slack"
NOTIFIER_TEAMS = "teams"
NOTIFIER_EMAIL = "email"
NOTIFIER_WEBHOOK = "webhook"

_TIMEOUT_SECONDS = 10
_MAX_TEMPLATE_LENGTH = 10_000
_MAX_RENDERED_LENGTH = 20_000


@dataclass(frozen=True)
class DriftNotification:
    site_url: str
    added_pages: int
    removed_pages: int
    field_changes: int
    api_changes: int
    report_url: str  # diff_report.html への相対 or 絶対 URL
    added_page_names: tuple[str, ...] = ()
    removed_page_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class CrawlFailureNotification:
    site_url: str
    attempts: int
    error: str
    started_at: str = ""


@dataclass(frozen=True)
class NotifierConfig:
    notifier_type: str  # NOTIFIER_SLACK / NOTIFIER_EMAIL / NOTIFIER_WEBHOOK
    endpoint: str  # Slack Webhook URL / SMTP host / Webhook URL
    # メール専用（slack/webhook では無視）
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    from_address: str = ""
    to_addresses: tuple[str, ...] = ()
    template: str = ""


def send_drift_notification(config: NotifierConfig, notification: DriftNotification) -> bool:
    """通知タイプに応じてドリフト通知を送信する。失敗時は False を返す。"""
    return _send_notification(config, notification, "drift_detected")


def send_crawl_failure_notification(
    config: NotifierConfig, notification: CrawlFailureNotification
) -> bool:
    """最終リトライ後のクロール失敗を通知する。"""
    return _send_notification(config, notification, "crawl_failed")


def notifier_config_from_mapping(values: dict[str, Any]) -> NotifierConfig | None:
    """schedule.json 等の設定値から、秘密値をログへ出さず通知設定を組み立てる。"""
    notifier_type = str(values.get("notify_type", "none")).strip()
    if notifier_type not in {NOTIFIER_SLACK, NOTIFIER_TEAMS, NOTIFIER_EMAIL, NOTIFIER_WEBHOOK}:
        return None
    endpoint = str(values.get("notify_endpoint", "")).strip()
    if notifier_type == NOTIFIER_EMAIL:
        endpoint = endpoint or os.environ.get("SMTP_HOST", "")
    if not endpoint:
        return None
    raw_addresses = values.get("to_addresses") or os.environ.get("SMTP_TO", "")
    if isinstance(raw_addresses, str):
        to_addresses = tuple(item.strip() for item in raw_addresses.split(",") if item.strip())
    elif isinstance(raw_addresses, list | tuple | set):
        to_addresses = tuple(str(item).strip() for item in raw_addresses if str(item).strip())
    else:
        to_addresses = ()
    raw_port = values.get("smtp_port") or os.environ.get("SMTP_PORT", "465")
    try:
        smtp_port = int(raw_port) if isinstance(raw_port, str | int | float | bytes) else 465
    except (TypeError, ValueError):
        smtp_port = 465
    return NotifierConfig(
        notifier_type=notifier_type,
        endpoint=endpoint,
        smtp_port=smtp_port,
        smtp_user=str(values.get("smtp_user") or os.environ.get("SMTP_USER", "")),
        smtp_password=str(values.get("smtp_password") or os.environ.get("SMTP_PASSWORD", "")),
        from_address=str(values.get("from_address") or os.environ.get("SMTP_FROM", "")),
        to_addresses=to_addresses,
        template=str(values.get("notify_template", "")),
    )


def _send_notification(
    config: NotifierConfig,
    notification: DriftNotification | CrawlFailureNotification,
    event_type: str,
) -> bool:
    dispatch = {
        NOTIFIER_SLACK: _send_text_webhook,
        NOTIFIER_TEAMS: _send_text_webhook,
        NOTIFIER_EMAIL: _send_email,
        NOTIFIER_WEBHOOK: _send_webhook,
    }
    handler = dispatch.get(config.notifier_type)
    if handler is None:
        logger.error("Unknown notifier_type: %s", config.notifier_type)
        return False
    try:
        return handler(config, notification, event_type)
    except Exception:
        logger.error("Unexpected error sending notification", exc_info=True)
        return False


def render_notification_text(
    config: NotifierConfig,
    notification: DriftNotification | CrawlFailureNotification,
) -> str:
    """通知文面を安全な Jinja2 sandbox で描画する。"""
    if not config.template:
        return _default_text(notification)
    if len(config.template) > _MAX_TEMPLATE_LENGTH:
        logger.error("Notification template is too long")
        return _default_text(notification)
    environment = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False)
    try:
        rendered = environment.from_string(config.template).render(
            **dataclasses.asdict(notification)
        )
    except TemplateError:
        logger.error("Notification template rendering failed", exc_info=True)
        return _default_text(notification)
    if len(rendered) > _MAX_RENDERED_LENGTH:
        logger.error("Rendered notification is too long")
        return _default_text(notification)
    return rendered


def validate_notification_template(template: str) -> str | None:
    """保存前の構文検査。None は正常、文字列はエラー理由。"""
    if len(template) > _MAX_TEMPLATE_LENGTH:
        return "template is too long"
    try:
        SandboxedEnvironment(undefined=StrictUndefined, autoescape=False).parse(template)
    except TemplateError as exc:
        return f"invalid template: {exc}"
    return None


def _default_text(notification: DriftNotification | CrawlFailureNotification) -> str:
    if isinstance(notification, CrawlFailureNotification):
        return (
            f"❌ クロール失敗: {notification.site_url}\n"
            f"試行回数: {notification.attempts}回\n"
            f"エラー: {notification.error}"
        )
    details: list[str] = []
    if notification.added_page_names:
        details.append("追加画面: " + ", ".join(notification.added_page_names))
    if notification.removed_page_names:
        details.append("削除画面: " + ", ".join(notification.removed_page_names))
    suffix = ("\n" + "\n".join(details)) if details else ""
    return (
        f"⚠️ 仕様ドリフト検知: {notification.site_url}\n"
        f"追加: {notification.added_pages}画面 / "
        f"削除: {notification.removed_pages}画面 / "
        f"フィールド変化: {notification.field_changes}件\n"
        f"レポート: {notification.report_url}{suffix}"
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
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS):  # nosec B310
            return True
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        logger.error("HTTP/URL error posting to %s: %s", url, exc)
        return False


def _send_text_webhook(
    config: NotifierConfig,
    notification: DriftNotification | CrawlFailureNotification,
    _event_type: str,
) -> bool:
    # Teams Workflows と Slack Incoming Webhook は text payload を共通で受け取る。
    payload = {"text": render_notification_text(config, notification)}
    return _post_json(config.endpoint, payload)


def _send_webhook(
    config: NotifierConfig,
    notification: DriftNotification | CrawlFailureNotification,
    event_type: str,
) -> bool:
    payload = dataclasses.asdict(notification)
    payload["type"] = event_type
    return _post_json(config.endpoint, payload)


def _send_email(
    config: NotifierConfig,
    notification: DriftNotification | CrawlFailureNotification,
    event_type: str,
) -> bool:
    # 送信対象なしを成功扱いするとテスト通知が偽陽性になる。
    if not config.to_addresses:
        logger.error("Email recipient is not configured")
        return False

    subject_label = "クロール失敗" if event_type == "crawl_failed" else "仕様ドリフト検知"
    subject = f"[WebSpec2Doc] {subject_label}: {notification.site_url}"
    body = render_notification_text(config, notification)

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
    summary_limit: int = 5,
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
        added_page_names=_page_names(diff_result.added_pages, summary_limit),
        removed_page_names=_page_names(diff_result.removed_pages, summary_limit),
    )


def _page_names(changes: Any, limit: int) -> tuple[str, ...]:
    labels: list[str] = []
    for change in changes:
        label = str(getattr(change, "title", "") or getattr(change, "url", "")).strip()
        if label:
            labels.append(label)
        if len(labels) >= max(0, limit):
            break
    return tuple(labels)
