from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from web.env_store import _read_env
from web.services.notifier import (
    NOTIFIER_SLACK,
    NotifierConfig,
    RunNotification,
    notifier_config_from_mapping,
    send_run_notification,
)

logger = logging.getLogger(__name__)

#: 既定を run_failed のみにしているのは、成功のたびに鳴る通知は数日で読み飛ばされ、
#: 本当に見てほしい失敗まで一緒に無視されるようになるため。
#: 成功も受け取りたい場合だけ .env の SLACK_NOTIFY_EVENTS で明示的に足す。
DEFAULT_NOTIFY_EVENTS = "run_failed"
#: 通知対象として受け付けるイベント。未知の値は黙って捨てる（誤記で全通知が止まらないように）。
VALID_EVENTS = frozenset({"run_completed", "run_failed", "run_cancelled"})


def _normalize_events(raw: Any) -> frozenset[str]:
    """設定値（カンマ区切り文字列 / 配列）をイベント集合へ正規化する。

    未知の値は VALID_EVENTS で落とす。誤記 1 個で通知が全部止まるより、
    誤記だけを捨てて正しい指定を生かすほうが運用事故が小さいため。
    """
    if isinstance(raw, str):
        requested = {item.strip() for item in raw.split(",") if item.strip()}
    elif isinstance(raw, list | tuple | set | frozenset):
        requested = {str(item).strip() for item in raw if str(item).strip()}
    else:
        return frozenset()
    return frozenset(requested & VALID_EVENTS)


def _enabled_events(env: dict[str, str]) -> frozenset[str]:
    """.env の SLACK_NOTIFY_EVENTS（無ければ既定）から許可イベントを求める。"""
    return _normalize_events((env.get("SLACK_NOTIFY_EVENTS") or DEFAULT_NOTIFY_EVENTS).strip())


def _load_schedule_config(domain: str, output_root: Path | None) -> dict[str, Any]:
    """`output/<domain>/schedule.json` を読む。読めなければ空 dict を返す。

    通知設定はスケジュール設定 UI・テスト送信 API・秘匿値（Webhook URL 等）の
    取り扱いが既にこのファイルへ集約されているため、実行完了通知でも同じ保存場所を
    再利用する。ここで新しい設定ストアを作ると、同じ通知先を 2 か所で二重管理する
    ことになり、片方だけ更新されて「テスト送信は届くのに実行通知は旧アドレスへ飛ぶ」
    という食い違いが必ず起きる。

    ファイルが無い・壊れている場合でも例外は投げない（呼び出し元は実行の終端であり、
    通知設定の不備で実行そのものを失敗扱いにしてはならない）。
    """
    if not domain or output_root is None:
        return {}
    try:
        path = Path(output_root) / domain / "schedule.json"
        if not path.is_file():
            return {}
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        logger.warning("schedule.json を読めないため env 設定へフォールバックします: domain=%s", domain)
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _resolve_config(
    schedule_config: dict[str, Any], env: dict[str, str]
) -> NotifierConfig | None:
    """通知先を決める。schedule.json（全チャネル）→ .env（Slack のみ）の順。

    schedule.json 側は notifier_config_from_mapping() を通すため
    slack / teams / email / webhook のいずれにも対応する。
    設定が無い場合に .env SLACK_WEBHOOK_URL へ落とすのは、この関数が
    追加される前から .env だけで運用している環境の後方互換のため。
    """
    config = notifier_config_from_mapping(schedule_config) if schedule_config else None
    if config is not None:
        return config
    webhook_url = (env.get("SLACK_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        return None
    return NotifierConfig(notifier_type=NOTIFIER_SLACK, endpoint=webhook_url)


def _resolve_events(schedule_config: dict[str, Any], env: dict[str, str]) -> frozenset[str]:
    """許可イベントを決める。schedule.json の notify_run_events → .env → 既定の順。"""
    if schedule_config:
        events = _normalize_events(schedule_config.get("notify_run_events"))
        if events:
            return events
    return _enabled_events(env)


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
    domain: str = "",
    output_root: Path | None = None,
) -> None:
    """AutoRun / テスト実行の終了を、設定された通知チャネルへ通知する。

    発火点（実行パイプライン）から 1 行で呼べることを優先し、例外は一切外へ出さない。
    通知の失敗で実行そのものが失敗扱いになってはならない。

    `domain` / `output_root` を受け取るのは、通知先が「サイト（ドメイン）ごと」に
    決まる設定だからである。実行の終端はドメインを必ず持っているため、その 2 つを
    渡すだけで `output/<domain>/schedule.json` に保存済みの通知設定
    （notify_type / notify_endpoint / notify_template …）をそのまま使え、
    slack / teams / email / webhook の全チャネルへ飛ばせる。既存のスケジュール通知と
    同じ保存場所を再利用することで、設定 UI・テスト送信 API・秘匿値の扱いを
    そのまま流用でき、通知先の二重管理を避けられる。

    解決順序:
      通知先  : schedule.json の設定 → .env SLACK_WEBHOOK_URL → 何もしない
      イベント: schedule.json の notify_run_events → .env SLACK_NOTIFY_EVENTS
                → DEFAULT_NOTIFY_EVENTS
    """
    try:
        env = _read_env()
        schedule_config = _load_schedule_config(domain, output_root)
        config = _resolve_config(schedule_config, env)
        if config is None:
            return
        if f"run_{status}" not in _resolve_events(schedule_config, env):
            return
        send_run_notification(
            config,
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
