from __future__ import annotations

import queue
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from crawler.session_guard import SessionExpiredError

if TYPE_CHECKING:
    from crawler.page_crawler import (
        CheckpointCallback,
        CrawlEventCallback,
        PageData,
        StopRequested,
    )
    from crawler.politeness import OriginRateLimiter


def crawl_urls_parallel(
    targets: list[str],
    output_dir: Path | None,
    auth_state: Path | None,
    worker_count: int,
    on_event: CrawlEventCallback | None,
    on_checkpoint: CheckpointCallback | None,
    stop_requested: StopRequested | None,
    limiter: OriginRateLimiter | None = None,
) -> list[PageData]:
    """ワーカーごとに独立Playwrightを持ち、明示URLを安全に並列解析する。

    limiter は全ワーカー共有の rate limiter（サイト全体のリクエスト間隔を保証）。
    """
    from crawler.page_crawler import _browser_page, _crawl_page_with_id, _format_page_id

    task_queue: queue.Queue[tuple[int, str]] = queue.Queue()
    for item in enumerate(targets):
        task_queue.put(item)
    results: dict[int, PageData] = {}
    errors: list[BaseException] = []
    result_lock = threading.Lock()
    checkpoint_lock = threading.Lock()
    internal_stop = threading.Event()

    def should_stop() -> bool:
        return internal_stop.is_set() or bool(stop_requested and stop_requested())

    def worker() -> None:
        try:
            with _browser_page(auth_state) as page:
                while not should_stop():
                    try:
                        index, target = task_queue.get_nowait()
                    except queue.Empty:
                        return
                    started_at = time.monotonic()
                    _emit(
                        on_event,
                        "page_started",
                        url=target,
                        index=index + 1,
                        total=len(targets),
                    )
                    if limiter is not None:
                        limiter.acquire(target)
                    try:
                        page_data = _crawl_page_with_id(
                            page,
                            target,
                            _format_page_id(index + 1),
                            output_dir,
                            auth_state=auth_state,
                            on_event=on_event,
                        )
                    except SessionExpiredError as exc:
                        with result_lock:
                            errors.append(exc)
                        internal_stop.set()
                        return
                    finally:
                        task_queue.task_done()
                    if page_data is None:
                        continue
                    with result_lock:
                        results[index] = page_data
                        completed_count = len(results)
                    if on_checkpoint:
                        with checkpoint_lock:
                            with result_lock:
                                checkpoint_pages = [results[key] for key in sorted(results)]
                            on_checkpoint(checkpoint_pages)
                    _emit(
                        on_event,
                        "page_completed",
                        url=target,
                        completed=completed_count,
                        total=len(targets),
                        elapsed_sec=round(time.monotonic() - started_at, 3),
                    )
        except BaseException as exc:
            with result_lock:
                errors.append(exc)
            internal_stop.set()

    workers = [threading.Thread(target=worker, daemon=True) for _ in range(worker_count)]
    for thread in workers:
        thread.start()
    for thread in workers:
        thread.join()

    if errors:
        raise errors[0]
    pages = _compact_page_screenshots([results[key] for key in sorted(results)], output_dir)
    event = "crawl_cancelled" if should_stop() else "crawl_completed"
    _emit(on_event, event, completed=len(pages), total=len(targets))
    return pages


def _compact_page_screenshots(pages: list[PageData], output_dir: Path | None) -> list[PageData]:
    """並列処理で欠番になったスクリーンショットIDを成功画面順へ詰める。"""
    from crawler.page_crawler import SCREENSHOTS_DIR_NAME, _format_page_id

    if output_dir is None:
        return pages
    compacted: list[PageData] = []
    for index, page in enumerate(pages, 1):
        if not page.screenshot_path:
            compacted.append(page)
            continue
        source = Path(page.screenshot_path)
        target = output_dir / SCREENSHOTS_DIR_NAME / f"{_format_page_id(index)}.png"
        if source != target and source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            source.replace(target)
        compacted.append(replace(page, screenshot_path=str(target)))
    return compacted


def _emit(callback: CrawlEventCallback | None, event: str, **details: object) -> None:
    if callback is not None:
        callback({"event": event, **details})
