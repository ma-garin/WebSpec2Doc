"""クロール礼儀（politeness）を担うモジュール。

token bucket 方式のリクエスト間隔制御・HTTP 429/503 の exponential backoff・
robots.txt の Crawl-Delay 解釈・監査ログ（audit.jsonl）出力を提供する。
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)

# ツールバージョン（User-Agent 表記に使用）
TOOL_VERSION = "1.0"

# リクエスト間隔の既定値（秒）と環境変数名
DEFAULT_CRAWL_INTERVAL_SEC = 1.0
CRAWL_INTERVAL_ENV = "WEBSPEC2DOC_CRAWL_INTERVAL_SEC"

# 429/503 受信時の exponential backoff 設定
BACKOFF_INITIAL_SEC = 2.0
BACKOFF_MAX_SEC = 60.0
BACKOFF_MAX_RETRIES = 5
RETRYABLE_STATUS_CODES = frozenset({429, 503})

AUDIT_LOG_FILE_NAME = "audit.jsonl"


class RetryableHTTPError(RuntimeError):
    """HTTP 429/503 などリトライ可能なステータスを受信したことを表す例外。"""

    def __init__(self, url: str, status: int) -> None:
        super().__init__(f"リトライ可能な HTTP ステータスを受信しました: {status} ({url})")
        self.url = url
        self.status = status


def build_user_agent() -> str:
    """明示的な User-Agent 文字列を返す。"""
    return f"WebSpec2Doc/{TOOL_VERSION} (+https://github.com/ma-garin/WebSpec2Doc)"


def crawl_interval_from_env() -> float:
    """環境変数からリクエスト間隔（秒）を取得する。不正値は既定値にフォールバックする。"""
    raw = os.environ.get(CRAWL_INTERVAL_ENV, "")
    if not raw:
        return DEFAULT_CRAWL_INTERVAL_SEC
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "%s の値が不正です（%r）。既定値 %s 秒を使用します。",
            CRAWL_INTERVAL_ENV,
            raw,
            DEFAULT_CRAWL_INTERVAL_SEC,
        )
        return DEFAULT_CRAWL_INTERVAL_SEC
    if value < 0:
        logger.warning(
            "%s に負値が指定されました（%s）。既定値 %s 秒を使用します。",
            CRAWL_INTERVAL_ENV,
            value,
            DEFAULT_CRAWL_INTERVAL_SEC,
        )
        return DEFAULT_CRAWL_INTERVAL_SEC
    return value


class TokenBucketLimiter:
    """token bucket 方式のリクエスト間隔制御。

    バケット容量 1 トークン・補充レート 1/interval_sec で、
    ``acquire()`` 呼び出しの間隔が interval_sec 以上になることを保証する。
    clock / sleeper を注入可能にしてテスト容易性を確保する。
    """

    def __init__(
        self,
        interval_sec: float,
        clock: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        if interval_sec < 0:
            raise ValueError("interval_sec は 0 以上を指定してください。")
        self._interval_sec = interval_sec
        # 未指定時は呼び出し時に time モジュールを参照する（テストでのパッチを有効にするため）
        self._clock = clock if clock is not None else (lambda: time.monotonic())
        self._sleeper = sleeper if sleeper is not None else (lambda sec: time.sleep(sec))
        # 並列クロール時も全ワーカー共有で間隔を保証するためロックを持つ
        self._lock = threading.Lock()
        # 初回リクエストは待たせない（トークン 1 個で開始）
        self._tokens = 1.0
        self._last_refill = self._clock()

    @property
    def interval_sec(self) -> float:
        """現在のリクエスト間隔（秒）を返す。"""
        return self._interval_sec

    def apply_crawl_delay(self, crawl_delay: float | None) -> None:
        """robots.txt の Crawl-Delay と比較し、長い方を間隔として採用する。"""
        if crawl_delay is None:
            return
        if crawl_delay > self._interval_sec:
            logger.info(
                "robots.txt の Crawl-Delay (%s 秒) を採用します（設定値 %s 秒より長いため）。",
                crawl_delay,
                self._interval_sec,
            )
            self._interval_sec = float(crawl_delay)

    def _refill(self) -> None:
        """経過時間に応じてトークンを補充する（容量上限 1）。"""
        if self._interval_sec <= 0:
            self._tokens = 1.0
            return
        now = self._clock()
        elapsed = now - self._last_refill
        self._last_refill = now
        self._tokens = min(1.0, self._tokens + elapsed / self._interval_sec)

    def acquire(self) -> float:
        """トークンを 1 個消費する。不足時は補充されるまで待機し、待機秒数を返す。"""
        with self._lock:
            self._refill()
            waited = 0.0
            if self._tokens < 1.0 and self._interval_sec > 0:
                waited = (1.0 - self._tokens) * self._interval_sec
                self._sleeper(waited)
                self._refill()
            self._tokens = max(0.0, self._tokens - 1.0)
            return waited


def backoff_delays(
    initial_sec: float = BACKOFF_INITIAL_SEC,
    max_sec: float = BACKOFF_MAX_SEC,
    max_retries: int = BACKOFF_MAX_RETRIES,
) -> Iterator[float]:
    """exponential backoff の待機秒数列（初期 2 秒・上限 60 秒・最大 5 回）を返す。"""
    delay = initial_sec
    for _ in range(max_retries):
        yield min(delay, max_sec)
        delay *= 2


def robots_crawl_delay(parser: RobotFileParser, user_agent: str) -> float | None:
    """robots.txt の Crawl-Delay ディレクティブを秒数として返す（未指定なら None）。"""
    try:
        raw = parser.crawl_delay(user_agent)
    except AttributeError:
        return None
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        logger.warning("Crawl-Delay の値を解釈できませんでした: %r", raw)
        return None


def append_audit_log(output_dir: Path | None, record: dict[str, object]) -> Path | None:
    """監査レコードを output_dir/audit.jsonl に 1 行の JSON として追記する。

    output_dir が None の場合は何もしない。書き込み失敗はクロールを妨げない。
    """
    if output_dir is None:
        return None
    entry = {"timestamp": datetime.now(UTC).isoformat(timespec="seconds"), **record}
    audit_path = output_dir / AUDIT_LOG_FILE_NAME
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("監査ログの書き込みに失敗しました: %s (%s)", audit_path, exc)
        return None
    return audit_path
