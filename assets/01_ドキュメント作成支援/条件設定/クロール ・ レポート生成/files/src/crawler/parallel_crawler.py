from __future__ import annotations

import queue
import threading
import time
from collections import deque
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from crawler.session_guard import SessionExpiredError

if TYPE_CHECKING:
    from urllib.robotparser import RobotFileParser

    from crawler.page_crawler import (
        CheckpointCallback,
        CrawlEventCallback,
        PageData,
        StopRequested,
        UxResultCallback,
    )
    from crawler.politeness import OriginRateLimiter, TokenBucketLimiter

# ワーカーが仕事待ちで cond.wait する際のポーリング間隔（秒）。
# stop_requested は外部ポーリングのため、通知漏れに備えて短い timeout で再確認する。
_WAIT_POLL_SEC = 0.2


def crawl_urls_parallel(
    targets: list[str],
    output_dir: Path | None,
    auth_state: Path | None,
    worker_count: int,
    on_event: CrawlEventCallback | None,
    on_checkpoint: CheckpointCallback | None,
    stop_requested: StopRequested | None,
    limiter: OriginRateLimiter | None = None,
    ux_review: bool = False,
    on_ux_result: UxResultCallback | None = None,
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
                            ux_review=ux_review,
                            on_ux_result=on_ux_result,
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


def crawl_site_parallel(
    base_url: str,
    *,
    depth: int,
    max_pages: int,
    output_dir: Path | None,
    auth_state: Path | None,
    worker_count: int,
    robots: RobotFileParser,
    limiter: TokenBucketLimiter,
    on_event: CrawlEventCallback | None = None,
    on_checkpoint: CheckpointCallback | None = None,
    stop_requested: StopRequested | None = None,
    ux_review: bool = False,
    on_ux_result: UxResultCallback | None = None,
    viewport: Any | None = None,
) -> list[PageData]:
    """BFS リンク追跡クロール（auto モード）をワーカー並列で実行する。

    共有フロンティア（visited + キュー）を複数ワーカーが取り合う並列 BFS。
    limiter は全ワーカー共有の rate limiter（サイト全体のリクエスト間隔を保証）で、
    robots.txt 判定・depth 制限・max_pages 上限は直列版 crawl_site と同一に扱う。
    """
    from crawler.page_crawler import (
        _browser_page,
        _crawl_page_with_id,
        _format_page_id,
        _next_urls,
        _skip_reason,
        known_total,
    )

    state = threading.Condition()
    frontier: deque[tuple[str, int]] = deque([(base_url, 0)])
    visited: set[str] = set()
    results: dict[int, PageData] = {}
    errors: list[BaseException] = []
    checkpoint_lock = threading.Lock()
    internal_stop = threading.Event()
    in_flight = 0
    dispatched = 0

    def should_stop() -> bool:
        return internal_stop.is_set() or bool(stop_requested and stop_requested())

    def _known_total_locked() -> int:
        """判明済みの対象数。`state` を保持した状態で呼ぶこと。"""
        return known_total(
            len(results), in_flight, frontier, visited, max_pages, max_depth=depth, robots=robots
        )

    def reserve_task() -> tuple[int, str, int, int] | None:
        """次のクロール対象を予約する。None は「もう仕事が来ない」を意味する。

        max_pages は「成功数 + 実行中数」で予約制にし、直列版と同様に
        上限超過クロールを発生させない（実行中の失敗時は枠が戻る）。
        """
        nonlocal in_flight, dispatched
        with state:
            while True:
                if should_stop() or len(results) >= max_pages:
                    return None
                if len(results) + in_flight < max_pages:
                    while frontier:
                        url, current_depth = frontier.popleft()
                        reason = _skip_reason(url, current_depth, depth, visited, robots)
                        if reason:
                            if reason not in {"visited", "depth"}:
                                _emit(on_event, "page_skipped", url=url, reason=reason)
                            continue
                        visited.add(url)
                        in_flight += 1
                        dispatched += 1
                        return dispatched, url, current_depth, _known_total_locked()
                    if in_flight == 0:
                        return None
                state.wait(timeout=_WAIT_POLL_SEC)

    def finish_task(
        index: int, url: str, current_depth: int, page_data: PageData | None, started_at: float
    ) -> None:
        nonlocal in_flight
        completed_count = 0
        total_known = max_pages
        with state:
            in_flight -= 1
            if page_data is not None and len(results) < max_pages:
                results[index] = page_data
                completed_count = len(results)
                frontier.extend(_next_urls(page_data.links, current_depth, visited, depth))
            else:
                page_data = None
            total_known = _known_total_locked()
            state.notify_all()
        if page_data is None:
            return
        if on_checkpoint:
            with checkpoint_lock:
                with state:
                    snapshot = [results[key] for key in sorted(results)]
                on_checkpoint(snapshot)
        _emit(
            on_event,
            "page_completed",
            url=url,
            completed=completed_count,
            total=total_known,
            elapsed_sec=round(time.monotonic() - started_at, 3),
        )

    def worker() -> None:
        try:
            with _browser_page(auth_state, viewport) as page:
                while True:
                    task = reserve_task()
                    if task is None:
                        return
                    index, url, current_depth, total_known = task
                    started_at = time.monotonic()
                    _emit(on_event, "page_started", url=url, index=index, total=total_known)
                    limiter.acquire()
                    page_data: PageData | None = None
                    try:
                        page_data = _crawl_page_with_id(
                            page,
                            url,
                            _format_page_id(index),
                            output_dir,
                            auth_state=auth_state,
                            on_event=on_event,
                            ux_review=ux_review,
                            on_ux_result=on_ux_result,
                        )
                    finally:
                        finish_task(index, url, current_depth, page_data, started_at)
        except BaseException as exc:
            with state:
                errors.append(exc)
                state.notify_all()
            internal_stop.set()

    workers = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, worker_count))]
    for thread in workers:
        thread.start()
    for thread in workers:
        thread.join()

    if errors:
        raise errors[0]
    pages = _compact_page_screenshots([results[key] for key in sorted(results)], output_dir)
    event = "crawl_cancelled" if should_stop() else "crawl_completed"
    # 終了時の total に上限値を載せると、収束していた分母が最後だけ跳ね上がる。
    with state:
        final_total = _known_total_locked()
    _emit(on_event, event, completed=len(pages), total=final_total)
    return pages


def _compact_page_screenshots(pages: list[PageData], output_dir: Path | None) -> list[PageData]:
    """並列処理で欠番になったスクリーンショットIDを成功画面順へ詰める。

    表示用（{id}.png）と対になる全体版（{id}_full.png）も一緒に詰め直し、
    レポートのライトボックスが全体版を見失わないようにする。
    """
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
        if source != target:
            if source.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                source.replace(target)
            source_full = source.with_name(f"{source.stem}_full.png")
            if source_full.exists():
                target_full = target.with_name(f"{target.stem}_full.png")
                target.parent.mkdir(parents=True, exist_ok=True)
                source_full.replace(target_full)
        compacted.append(replace(page, screenshot_path=str(target)))
    return compacted


def _emit(callback: CrawlEventCallback | None, event: str, **details: object) -> None:
    if callback is not None:
        callback({"event": event, **details})


def discover_pages_parallel(
    *,
    base_url: str,
    depth: int,
    max_pages: int,
    auth_state: Path | None,
    robots: RobotFileParser | None,
    worker_count: int,
    on_page_found: Any = None,
    on_event: CrawlEventCallback | None = None,
) -> list[dict[str, object]]:
    """画面リスト探索（BFS）を、深さ単位の波で並列に行う。

    直列だと 1 ページあたり実測 0.53 秒がそのまま積み上がっていた。
    同じ深さの URL は互いに依存しないので、まとめて取りに行ける。

    深さはまたがない。次の深さへ進む URL は、いまの深さで見つけたリンクから
    決まるため、先に進むと探索範囲が変わってしまう。

    発見順は「深さ順・同一深さ内は元の順序」で安定させる。並列で終わった順に
    出すと、同じサイトを解析するたびに画面の並びが変わり、前回との比較が
    できなくなる。

    Chromium はワーカーごとに起動する（起動は実測 0.21 秒/個）。1 個を共有して
    コンテキストだけ分ける案は成立しない。Playwright の同期 API は、
    オブジェクトを作ったスレッド以外から触ると
    `greenlet.error: Cannot switch to a different thread` で落ちる。
    既存の crawl_urls_parallel がワーカーごとに独立 Playwright を持つのも同じ理由。
    """
    from crawler.page_crawler import (
        _browser_page,
        _discover_one,
        _emit_event,
        _next_urls,
        _skip_reason,
    )

    visited: set[str] = set()
    found: list[dict[str, object]] = []
    wave: list[tuple[str, int]] = [(base_url, 0)]

    _emit_event(on_event, "browser_starting")
    first_wave = True
    while wave and len(found) < max_pages:
        # この波で実際に取りに行く URL を先に確定させる（除外はここで判定する）
        targets: list[tuple[str, int]] = []
        for url, url_depth in wave:
            if len(targets) + len(found) >= max_pages:
                break
            reason = _skip_reason(url, url_depth, depth, visited, robots)
            if reason:
                if reason not in {"visited", "depth"}:
                    _emit_event(on_event, "page_skipped", url=url, reason=reason)
                continue
            visited.add(url)
            targets.append((url, url_depth))
        if not targets:
            break

        task_queue: queue.Queue[int] = queue.Queue()
        for index in range(len(targets)):
            task_queue.put(index)
        # 添字ごとに結果を置く。並列で終わった順ではなく、元の順序で拾い直すため。
        page_slots: list[list[dict[str, object]]] = [[] for _ in targets]
        link_slots: list[tuple[str, ...]] = [() for _ in targets]
        errors: list[BaseException] = []

        # 波ごとに worker を作り直すため、この波の状態を引数で束縛する。
        # 外側のループ変数を閉じ込めると、波が進んだときに前の波の器へ
        # 書き込む余地が残る（B023）。
        def worker(
            tasks: queue.Queue[int] = task_queue,
            urls: list[tuple[str, int]] = targets,
            pages_out: list[list[dict[str, object]]] = page_slots,
            links_out: list[tuple[str, ...]] = link_slots,
            failures: list[BaseException] = errors,
        ) -> None:
            try:
                with _browser_page(auth_state) as page:
                    while True:
                        try:
                            index = tasks.get_nowait()
                        except queue.Empty:
                            return
                        url, _ = urls[index]
                        local: list[dict[str, object]] = []
                        links_out[index] = _discover_one(page, url, local)
                        pages_out[index] = local
            except BaseException as exc:  # noqa: BLE001  # 収集して呼び出し元へ伝える
                failures.append(exc)

        threads = [
            threading.Thread(target=worker, daemon=True)
            for _ in range(min(worker_count, len(targets)))
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        if errors:
            raise errors[0]
        if first_wave:
            _emit_event(on_event, "browser_ready")
            first_wave = False

        # 元の順序で確定させ、その順で通知する
        next_wave: list[tuple[str, int]] = []
        for index, (_url, url_depth) in enumerate(targets):
            for item in page_slots[index]:
                if len(found) >= max_pages:
                    break
                found.append(item)
                if on_page_found is not None:
                    on_page_found(item)
            next_wave.extend(_next_urls(link_slots[index], url_depth, visited, depth))
        wave = next_wave

    return found
