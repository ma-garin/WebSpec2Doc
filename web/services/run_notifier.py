from __future__ import annotations

import logging

from web.env_store import _read_env
from web.services.notifier import (
    NOTIFIER_SLACK,
    NotifierConfig,
    RunNotification,
    send_run_notification,
)

logger = logging.getLogger(__name__)

#: 既定を run_failed のみにしているのは、成功のたびに鳴る通知は数日で読み飛ばされ、
#: 本当に見てほしい失敗まで一緒に無視されるようになるため。
#: 成功も受け取りたい場合だけ .env の SLACK_NOTIFY_EVENTS で明示的に足す。
DEFAULT_NOTIFY_EVENTS = "run_failed"
#: 通知対象として受け付けるイベント。未知の値は黙って捨てる（誤記で全通知が止まらないように）。
VALID_EVENTS = frozenset({"run_completed", "run_failed", "run_cancelled"})


def _enabled_events(env: dict[str, str]) -> frozenset[str]:
    raw = (env.get("SLACK_NOTIFY_EVENTS") or DEFAULT_NOTIFY_EVENTS).strip()
    requested = {item.strip() for item in raw.split(",") if item.strip()}
    return frozenset(requested & VALID_EVENTS)


def notify_run_finished(
    *,
    site_url: str,
    run_kind: str,
    status: str,
    total: int = 0,
    passed: int = 0,
    failed: int = 0,
    skipped: int = 0,
    elapsed_sec: int = 0,
    report_url: str = "",
    error: str = "",
) -> None:
    """AutoRun / テスト実行の終了を Slack へ通知する。

    発火点（実行パイプライン）から 1 行で呼べることを優先し、例外は一切外へ出さない。
    通知の失敗で実行そのものが失敗扱いになってはならない。
    """
    try:
        env = _read_env()
        webhook_url = (env.get("SLACK_WEBHOOK_URL") or "").strip()
        if not webhook_url:
            return
        if f"run_{status}" not in _enabled_events(env):
            return
        send_run_notification(
            NotifierConfig(notifier_type=NOTIFIER_SLACK, endpoint=webhook_url),
            RunNotification(
                site_url=site_url,
                run_kind=run_kind,
                status=status,
                total=int(total or 0),
                passed=int(passed or 0),
                failed=int(failed or 0),
                skipped=int(skipped or 0),
                elapsed_sec=int(elapsed_sec or 0),
                report_url=report_url,
                error=error,
            ),
        )
    except Exception:
        logger.warning("実行完了通知の送信に失敗しました: kind=%s", run_kind, exc_info=True)
