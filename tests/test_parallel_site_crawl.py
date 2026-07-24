"""オートクローリング（BFS）並列化と高速化ノブのテスト。

crawl_site(parallelism>1) → crawl_site_parallel の委譲・BFS 意味論の維持
（visited 重複排除・depth 制限・max_pages 上限）・キャンセル・セッション失効の
伝播・スクリーンショット詰め直し（_full.png 同伴）・環境変数ノブを検証する。
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from urllib.robotparser import RobotFileParser

import pytest

import crawler.page_crawler as pc
import crawler.parallel_crawler as pcp
from crawler.page_crawler import PageData
from crawler.politeness import TokenBucketLimiter
from crawler.session_guard import SessionExpiredError


def _allow_all_robots() -> RobotFileParser:
    parser = RobotFileParser()
    parser.allow_all = True
    return parser


@contextmanager
def _fake_browser(_auth, _viewport=None):
    yield MagicMock()


def _page(url: str, links: tuple[str, ...] = ()) -> PageData:
    return PageData(
        url=url, title="t", headings=(), links=links, forms=(), screenshot_path=None
    )


def _no_wait_limiter() -> TokenBucketLimiter:
    return TokenBucketLimiter(0)


class TestCrawlSiteParallel:
    """crawl_site_parallel の BFS 意味論。"""

    def _run(
        self,
        site_links: dict[str, tuple[str, ...]],
        *,
        depth: int = 3,
        max_pages: int = 50,
        worker_count: int = 3,
        on_event=None,
        on_checkpoint=None,
        stop_requested=None,
    ) -> list[PageData]:
        def fake_crawl(page, url, page_id, output_dir, **kwargs):
            return _page(url, site_links.get(url, ()))

        with (
            patch.object(pc, "_browser_page", _fake_browser),
            patch.object(pc, "_crawl_page_with_id", side_effect=fake_crawl),
        ):
            return pcp.crawl_site_parallel(
                "https://example.com/",
                depth=depth,
                max_pages=max_pages,
                output_dir=None,
                auth_state=None,
                worker_count=worker_count,
                robots=_allow_all_robots(),
                limiter=_no_wait_limiter(),
                on_event=on_event,
                on_checkpoint=on_checkpoint,
                stop_requested=stop_requested,
            )

    def test_follows_links_and_dedupes(self) -> None:
        links = {
            "https://example.com/": ("https://example.com/a", "https://example.com/b"),
            "https://example.com/a": ("https://example.com/b", "https://example.com/"),
            "https://example.com/b": ("https://example.com/c",),
        }
        pages = self._run(links)
        assert sorted(p.url for p in pages) == [
            "https://example.com/",
            "https://example.com/a",
            "https://example.com/b",
            "https://example.com/c",
        ]

    def test_respects_max_pages(self) -> None:
        links = {
            f"https://example.com/{i}": (f"https://example.com/{i + 1}",) for i in range(20)
        }
        links["https://example.com/"] = ("https://example.com/0",)
        pages = self._run(links, max_pages=5, depth=30)
        assert len(pages) == 5

    def test_respects_depth_limit(self) -> None:
        links = {
            "https://example.com/": ("https://example.com/d1",),
            "https://example.com/d1": ("https://example.com/d2",),
            "https://example.com/d2": ("https://example.com/d3",),
        }
        pages = self._run(links, depth=1)
        assert sorted(p.url for p in pages) == [
            "https://example.com/",
            "https://example.com/d1",
        ]

    def test_emits_events_and_checkpoints(self) -> None:
        events: list[dict[str, object]] = []
        checkpoints: list[list[PageData]] = []
        event_lock = threading.Lock()

        def on_event(event: dict[str, object]) -> None:
            with event_lock:
                events.append(event)

        pages = self._run(
            {"https://example.com/": ("https://example.com/a",)},
            on_event=on_event,
            on_checkpoint=checkpoints.append,
        )
        assert len(pages) == 2
        names = [e["event"] for e in events]
        assert names.count("page_started") == 2
        assert names.count("page_completed") == 2
        assert names[-1] == "crawl_completed"
        assert len(checkpoints) == 2
        assert len(checkpoints[-1]) == 2

    def test_stop_requested_cancels(self) -> None:
        pages = self._run(
            {"https://example.com/": ("https://example.com/a",)},
            stop_requested=lambda: True,
        )
        assert pages == []

    def test_session_expired_propagates(self) -> None:
        def fake_crawl(page, url, page_id, output_dir, **kwargs):
            raise SessionExpiredError("expired")

        with (
            patch.object(pc, "_browser_page", _fake_browser),
            patch.object(pc, "_crawl_page_with_id", side_effect=fake_crawl),
        ):
            with pytest.raises(SessionExpiredError):
                pcp.crawl_site_parallel(
                    "https://example.com/",
                    depth=1,
                    max_pages=5,
                    output_dir=None,
                    auth_state=None,
                    worker_count=2,
                    robots=_allow_all_robots(),
                    limiter=_no_wait_limiter(),
                )

    def test_failed_page_frees_budget(self) -> None:
        """クロール失敗（None）は max_pages の枠を消費しない。"""
        failed = {"https://example.com/a"}

        def fake_crawl(page, url, page_id, output_dir, **kwargs):
            if url in failed:
                return None
            return _page(
                url,
                (
                    "https://example.com/a",
                    "https://example.com/b",
                    "https://example.com/c",
                ),
            )

        with (
            patch.object(pc, "_browser_page", _fake_browser),
            patch.object(pc, "_crawl_page_with_id", side_effect=fake_crawl),
        ):
            pages = pcp.crawl_site_parallel(
                "https://example.com/",
                depth=2,
                max_pages=3,
                output_dir=None,
                auth_state=None,
                worker_count=2,
                robots=_allow_all_robots(),
                limiter=_no_wait_limiter(),
            )
        assert len(pages) == 3
        assert "https://example.com/a" not in {p.url for p in pages}


class TestCrawlSiteDelegation:
    """crawl_site は parallelism>1 のとき並列 BFS へ委譲する。"""

    def test_delegates_when_parallelism_above_one(self) -> None:
        sentinel = [_page("https://example.com/")]
        with (
            patch.object(pcp, "crawl_site_parallel", return_value=sentinel) as spy,
            patch.object(pc, "_load_robots_parser", return_value=_allow_all_robots()),
        ):
            pages = pc.crawl_site("https://example.com/", parallelism=3)
        assert pages == sentinel
        assert spy.call_args.kwargs["worker_count"] == 3

    def test_sequential_when_parallelism_one(self) -> None:
        with (
            patch.object(pcp, "crawl_site_parallel") as spy,
            patch.object(pc, "_browser_page", _fake_browser),
            patch.object(pc, "_crawl_page_with_id", return_value=_page("https://example.com/")),
            patch.object(pc, "_load_robots_parser", return_value=_allow_all_robots()),
            patch.object(pc.time, "sleep"),
        ):
            pages = pc.crawl_site("https://example.com/", parallelism=1, max_pages=1)
        assert len(pages) == 1
        spy.assert_not_called()

    def test_worker_count_capped_by_max_pages(self) -> None:
        with (
            patch.object(pcp, "crawl_site_parallel", return_value=[]) as spy,
            patch.object(pc, "_load_robots_parser", return_value=_allow_all_robots()),
        ):
            pc.crawl_site("https://example.com/", parallelism=4, max_pages=2)
        assert spy.call_args.kwargs["worker_count"] == 2


class TestScreenshotCompaction:
    def test_moves_full_screenshot_alongside_viewport(self, tmp_path) -> None:
        shots = tmp_path / "screenshots"
        shots.mkdir()
        (shots / "P003.png").write_bytes(b"viewport")
        (shots / "P003_full.png").write_bytes(b"full")
        pages = [_page("https://example.com/")]
        pages[0] = PageData(
            url="https://example.com/",
            title="t",
            headings=(),
            links=(),
            forms=(),
            screenshot_path=str(shots / "P003.png"),
        )
        compacted = pcp._compact_page_screenshots(pages, tmp_path)
        assert compacted[0].screenshot_path == str(shots / "P001.png")
        assert (shots / "P001.png").read_bytes() == b"viewport"
        assert (shots / "P001_full.png").read_bytes() == b"full"
        assert not (shots / "P003.png").exists()
        assert not (shots / "P003_full.png").exists()


class TestSpeedKnobs:
    def test_stability_timeout_default(self, monkeypatch) -> None:
        monkeypatch.delenv(pc.STABILITY_TIMEOUT_ENV, raising=False)
        assert pc._stability_timeout_ms() == pc.STABILITY_TIMEOUT_MS

    def test_stability_timeout_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv(pc.STABILITY_TIMEOUT_ENV, "800")
        assert pc._stability_timeout_ms() == 800

    def test_stability_timeout_invalid_falls_back(self, monkeypatch) -> None:
        monkeypatch.setenv(pc.STABILITY_TIMEOUT_ENV, "abc")
        assert pc._stability_timeout_ms() == pc.STABILITY_TIMEOUT_MS
        monkeypatch.setenv(pc.STABILITY_TIMEOUT_ENV, "-1")
        assert pc._stability_timeout_ms() == pc.STABILITY_TIMEOUT_MS

    def test_stability_timeout_zero_skips_wait(self, monkeypatch) -> None:
        monkeypatch.setenv(pc.STABILITY_TIMEOUT_ENV, "0")
        page = MagicMock()
        pc._goto_stable(page, "https://example.com/")
        page.wait_for_load_state.assert_not_called()

    def test_full_screenshot_enabled_by_default(self, monkeypatch) -> None:
        monkeypatch.delenv(pc.FULL_SCREENSHOT_ENV, raising=False)
        assert pc._full_screenshot_enabled() is True

    def test_full_screenshot_disabled_by_env(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv(pc.FULL_SCREENSHOT_ENV, "0")
        page = MagicMock()
        result = pc._save_screenshot(page, tmp_path, "P001")
        assert result == str(tmp_path / "screenshots" / "P001.png")
        assert page.screenshot.call_count == 1
        assert page.screenshot.call_args.kwargs.get("full_page") is False
