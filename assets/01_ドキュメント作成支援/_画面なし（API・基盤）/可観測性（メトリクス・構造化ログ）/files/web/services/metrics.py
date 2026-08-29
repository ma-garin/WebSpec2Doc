"""Prometheus 形式のメトリクスと、その計測点。

運用者が知りたいのは「動いているか」ではなく「静かに壊れていないか」。
そのため成功数だけでなく、失敗・遅延・滞留を必ず対で公開する。

主張境界: ここが公開するのは**このプロセスが観測した値**であり、
対象サイトの品質やSLA達成度ではない。
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client.openmetrics.exposition import CONTENT_TYPE_LATEST

REGISTRY = CollectorRegistry()

RESULT_SUCCESS = "success"
RESULT_FAILURE = "failure"

crawl_total = Counter(
    "webspec2doc_crawl_total",
    "クロール実行の累計（成否別）",
    labelnames=("result",),
    registry=REGISTRY,
)
crawl_duration_seconds = Histogram(
    "webspec2doc_crawl_duration_seconds",
    "クロール1回あたりの所要時間",
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800),
    registry=REGISTRY,
)
schedule_delay_seconds = Gauge(
    "webspec2doc_schedule_delay_seconds",
    "予定時刻から実際の開始までの遅延（秒）",
    registry=REGISTRY,
)
job_queue_depth = Gauge(
    "webspec2doc_job_queue_depth",
    "未終了のジョブ数（滞留の検知用）",
    registry=REGISTRY,
)
notification_total = Counter(
    "webspec2doc_notification_total",
    "通知送信の累計（成否・種別）",
    labelnames=("result", "channel"),
    registry=REGISTRY,
)


def render_metrics() -> tuple[bytes, str]:
    """公開用のメトリクス本文と Content-Type を返す。"""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


# ─────────────────── 計測点 ───────────────────


def record_crawl(*, success: bool, duration_sec: float) -> None:
    """クロール1回の結果を記録する。計測失敗で本処理を止めない。"""
    try:
        crawl_total.labels(result=RESULT_SUCCESS if success else RESULT_FAILURE).inc()
        if duration_sec >= 0:
            crawl_duration_seconds.observe(duration_sec)
    except Exception:  # pragma: no cover - 計測は本処理を妨げない
        logging.getLogger(__name__).debug("クロールのメトリクス記録に失敗", exc_info=True)


def record_notification(*, success: bool, channel: str) -> None:
    try:
        notification_total.labels(
            result=RESULT_SUCCESS if success else RESULT_FAILURE,
            channel=channel or "unknown",
        ).inc()
    except Exception:  # pragma: no cover
        logging.getLogger(__name__).debug("通知のメトリクス記録に失敗", exc_info=True)


def set_schedule_delay(delay_sec: float) -> None:
    try:
        schedule_delay_seconds.set(max(0.0, float(delay_sec)))
    except Exception:  # pragma: no cover
        logging.getLogger(__name__).debug("遅延のメトリクス記録に失敗", exc_info=True)


def set_job_queue_depth(depth: int) -> None:
    try:
        job_queue_depth.set(max(0, int(depth)))
    except Exception:  # pragma: no cover
        logging.getLogger(__name__).debug("滞留のメトリクス記録に失敗", exc_info=True)


@contextmanager
def measure_crawl() -> Iterator[dict[str, Any]]:
    """クロールの所要時間と成否を自動で記録する。

    with 内で例外が出た場合は失敗として計上したうえで再送出する
    （握り潰すと「静かに壊れる」ため）。
    """
    started = time.monotonic()
    state: dict[str, Any] = {"success": True}
    try:
        yield state
    except Exception:
        record_crawl(success=False, duration_sec=time.monotonic() - started)
        raise
    record_crawl(success=bool(state.get("success", True)), duration_sec=time.monotonic() - started)


# ─────────────────── 構造化ログ ───────────────────


class JsonLogFormatter(logging.Formatter):
    """1行1JSONのログ。ログ基盤で機械的に集計できる形にする。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in getattr(record, "extra_fields", {}).items():
            payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


def configure_json_logging(level: int = logging.INFO) -> None:
    """ルートロガーをJSON出力へ切り替える（既存ハンドラは置き換える）。"""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
