"""新側リンクの疎通確認（現新比較の三層比較の 1 つ）。

politeness.py の ``OriginRateLimiter``・``backoff_delays`` に準拠して HTTP 検査する。
タイムアウト・接続失敗は「切れ」と断定せず「未確認」として記録する（5-4 節）。
標準ライブラリ（urllib）のみで実装し、新規外部依存（requests 等）は追加しない。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from crawler.politeness import (
    RETRYABLE_STATUS_CODES,
    OriginRateLimiter,
    append_audit_log,
    backoff_delays,
    build_user_agent,
)

logger = logging.getLogger(__name__)

STATUS_OK = "ok"
STATUS_BROKEN = "broken"
STATUS_UNCONFIRMED = "unconfirmed"

DEFAULT_TIMEOUT_SEC = 10.0

# url, timeout_sec -> HTTP ステータスコード（接続失敗時は例外を送出する）
LinkOpener = Callable[[str, float], int]


@dataclass(frozen=True)
class LinkCheckResult:
    """1 件のリンク検査結果。"""

    url: str
    source_page_id: str
    status: str  # STATUS_OK / STATUS_BROKEN / STATUS_UNCONFIRMED
    http_status: int | None = None
    reason: str = ""


def _default_opener(url: str, timeout_sec: float) -> int:
    """urllib で HEAD リクエストを送り HTTP ステータスコードを返す。"""
    request = Request(url, method="HEAD", headers={"User-Agent": build_user_agent()})
    try:
        # 検査対象は呼び出し側（新側クロール結果）が指定した URL のみ。file:// 等の
        # 任意スキームは想定しないが、bandit/ruff の抑制コメントは別物のため両方併記する。
        with urlopen(request, timeout=timeout_sec) as response:  # nosec B310  # noqa: S310
            return int(response.status)
    except HTTPError as exc:
        # 404 等は例外だが「切れ」判定に必要な正規のステータスコードなのでそのまま返す
        return int(exc.code)


def check_link(
    url: str,
    source_page_id: str,
    limiter: OriginRateLimiter | None = None,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    opener: LinkOpener | None = None,
    output_dir: Path | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> LinkCheckResult:
    """1 件のリンクを検査する。429/503 は politeness の backoff で再試行する。

    sleeper はテスト容易性のための注入ポイント（既定は time.sleep。
    ``crawler.politeness.TokenBucketLimiter`` と同じ注入パターン）。
    """
    active_opener = opener or _default_opener
    active_sleeper = sleeper or time.sleep
    if limiter is not None:
        limiter.acquire(url)

    last_error: Exception | None = None
    delays: tuple[float, ...] = (0.0, *backoff_delays())
    for delay in delays:
        if delay:
            active_sleeper(delay)
        try:
            status_code = active_opener(url, timeout_sec)
        except (URLError, TimeoutError, OSError) as exc:
            last_error = exc
            continue
        if status_code in RETRYABLE_STATUS_CODES:
            last_error = None
            continue
        result = _classify(url, source_page_id, status_code)
        _record_audit(output_dir, result)
        return result

    result = LinkCheckResult(
        url=url,
        source_page_id=source_page_id,
        status=STATUS_UNCONFIRMED,
        http_status=None,
        reason=(
            f"タイムアウト/接続失敗のため未確認（切れとは断定しない）: {last_error}"
            if last_error is not None
            else "リトライ上限に達したため未確認"
        ),
    )
    _record_audit(output_dir, result)
    return result


def check_links(
    links: Iterable[tuple[str, str]],
    limiter: OriginRateLimiter | None = None,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    opener: LinkOpener | None = None,
    output_dir: Path | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> tuple[LinkCheckResult, ...]:
    """(url, source_page_id) の列を検査し、結果を返す。"""
    return tuple(
        check_link(url, source_page_id, limiter, timeout_sec, opener, output_dir, sleeper)
        for url, source_page_id in links
    )


def _classify(url: str, source_page_id: str, status_code: int) -> LinkCheckResult:
    if status_code >= 400:
        return LinkCheckResult(
            url=url,
            source_page_id=source_page_id,
            status=STATUS_BROKEN,
            http_status=status_code,
            reason=f"HTTP {status_code}",
        )
    return LinkCheckResult(
        url=url, source_page_id=source_page_id, status=STATUS_OK, http_status=status_code, reason=""
    )


def _record_audit(output_dir: Path | None, result: LinkCheckResult) -> None:
    """検査対象と結果を audit.jsonl に記録する（比較の網羅性証明）。"""
    append_audit_log(
        output_dir,
        {
            "event": "comparison_link_checked",
            "url": result.url,
            "source_page_id": result.source_page_id,
            "status": result.status,
            "http_status": result.http_status,
            "reason": result.reason,
        },
    )
