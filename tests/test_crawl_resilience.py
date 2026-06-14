from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.robotparser import RobotFileParser

import pytest

import crawler.page_crawler as crawler
from crawler.page_crawler import LoginWallDetected, PageData
from diff.snapshot import latest_snapshot, save_partial_snapshot, save_snapshot


def _page(url: str) -> PageData:
    return PageData(url, "title", (), (), (), None)


@contextmanager
def _browser(_auth: Path | None):
    yield MagicMock()


def test_crawl_urls_reports_robots_skip() -> None:
    robots = RobotFileParser()
    robots.parse(["User-agent: *", "Disallow: /private"])
    events: list[dict[str, object]] = []
    with (
        patch.object(crawler, "_load_robots_parser", return_value=robots),
        patch.object(crawler, "_browser_page", _browser),
        patch.object(
            crawler,
            "_crawl_page_with_id",
            side_effect=lambda _page_obj, url, *_args, **_kwargs: _page(url),
        ),
    ):
        pages = crawler.crawl_urls(
            ["https://example.com/public", "https://example.com/private/data"],
            respect_robots=True,
            on_event=events.append,
        )

    assert [page.url for page in pages] == ["https://example.com/public"]
    assert any(
        event.get("event") == "page_skipped" and event.get("reason") == "robots" for event in events
    )


def test_parallel_crawl_preserves_input_order_and_checkpoints() -> None:
    events: list[dict[str, object]] = []
    checkpoints: list[list[str]] = []
    urls = ["https://example.com/a", "https://example.com/b", "https://example.com/c"]
    with (
        patch.object(crawler, "_browser_page", _browser),
        patch.object(
            crawler,
            "_crawl_page_with_id",
            side_effect=lambda _page_obj, url, *_args, **_kwargs: _page(url),
        ),
    ):
        pages = crawler.crawl_urls(
            urls,
            parallelism=2,
            on_event=events.append,
            on_checkpoint=lambda done: checkpoints.append([page.url for page in done]),
        )

    assert [page.url for page in pages] == urls
    assert checkpoints
    assert checkpoints[-1] == urls
    started = next(event for event in events if event.get("event") == "crawl_started")
    assert started["parallelism"] == 2


def test_login_wall_is_reported_and_not_recorded() -> None:
    events: list[dict[str, object]] = []
    with patch.object(
        crawler,
        "crawl_page",
        side_effect=LoginWallDetected(
            "https://example.com/private", "https://example.com/login", ("password_field",)
        ),
    ):
        result = crawler._crawl_page_with_id(
            MagicMock(),
            "https://example.com/private",
            "P001",
            None,
            on_event=events.append,
        )

    assert result is None
    assert events[0]["event"] == "login_wall_detected"
    assert events[0]["login_url"] == "https://example.com/login"


def test_stop_before_next_page_emits_cancelled() -> None:
    events: list[dict[str, object]] = []
    with patch.object(crawler, "_browser_page", _browser):
        pages = crawler.crawl_urls(
            ["https://example.com/a"],
            on_event=events.append,
            stop_requested=lambda: True,
        )
    assert pages == []
    assert events[-1]["event"] == "crawl_cancelled"


def test_partial_snapshot_is_atomic_and_not_latest_complete(tmp_path: Path) -> None:
    pages = [_page("https://example.com/")]
    complete = save_snapshot(pages, tmp_path)
    checkpoint = save_partial_snapshot(pages, tmp_path)
    partial = save_partial_snapshot(pages, tmp_path, finalized=True)

    assert checkpoint.name == "current-checkpoint.json"
    assert checkpoint.exists()
    assert partial.name.endswith("-partial.json")
    assert latest_snapshot(tmp_path) == complete


def test_crawl_page_detects_login_wall_before_capture() -> None:
    page = MagicMock()
    page.goto.return_value = MagicMock(status=200, headers={})
    page.url = "https://example.com/login"
    page.query_selector.return_value = MagicMock()
    with pytest.raises(LoginWallDetected):
        crawler.crawl_page(page, "https://example.com/private", None)
