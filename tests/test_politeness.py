"""crawler.politeness（レート制御・backoff・robots・監査ログ）のユニットテスト。"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.robotparser import RobotFileParser

import pytest

import crawler.page_crawler as pc
from crawler.page_crawler import _crawl_page_with_id, _make_rate_limiter
from crawler.politeness import (
    BACKOFF_MAX_RETRIES,
    CRAWL_INTERVAL_ENV,
    DEFAULT_CRAWL_INTERVAL_SEC,
    RetryableHTTPError,
    TokenBucketLimiter,
    append_audit_log,
    backoff_delays,
    build_user_agent,
    crawl_interval_from_env,
    robots_crawl_delay,
)


class _FakeClock:
    """sleep すると時刻が進む決定的なクロック（テスト用）。"""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, sec: float) -> None:
        self.sleeps.append(sec)
        self.now += sec

    def advance(self, sec: float) -> None:
        self.now += sec


# ---------- TokenBucketLimiter ----------


class TestTokenBucketLimiter:
    def test_first_acquire_does_not_wait(self) -> None:
        fake = _FakeClock()
        limiter = TokenBucketLimiter(1.0, clock=fake.clock, sleeper=fake.sleep)
        assert limiter.acquire() == 0.0
        assert fake.sleeps == []

    def test_consecutive_acquires_keep_min_interval(self) -> None:
        """連続クロール時のリクエスト間隔が設定値以上であることを確認する（受け入れ条件）。"""
        fake = _FakeClock()
        limiter = TokenBucketLimiter(1.0, clock=fake.clock, sleeper=fake.sleep)
        timestamps: list[float] = []
        for _ in range(3):
            limiter.acquire()
            timestamps.append(fake.now)
        intervals = [b - a for a, b in zip(timestamps, timestamps[1:], strict=False)]
        assert all(interval >= 1.0 - 1e-9 for interval in intervals)

    def test_no_wait_after_enough_elapsed(self) -> None:
        fake = _FakeClock()
        limiter = TokenBucketLimiter(1.0, clock=fake.clock, sleeper=fake.sleep)
        limiter.acquire()
        fake.advance(2.0)
        assert limiter.acquire() == 0.0

    def test_zero_interval_never_waits(self) -> None:
        fake = _FakeClock()
        limiter = TokenBucketLimiter(0.0, clock=fake.clock, sleeper=fake.sleep)
        for _ in range(5):
            assert limiter.acquire() == 0.0

    def test_negative_interval_raises(self) -> None:
        with pytest.raises(ValueError):
            TokenBucketLimiter(-1.0)

    def test_apply_crawl_delay_takes_longer_value(self) -> None:
        limiter = TokenBucketLimiter(1.0)
        limiter.apply_crawl_delay(5.0)
        assert limiter.interval_sec == 5.0

    def test_apply_crawl_delay_keeps_longer_configured_interval(self) -> None:
        limiter = TokenBucketLimiter(10.0)
        limiter.apply_crawl_delay(5.0)
        assert limiter.interval_sec == 10.0

    def test_apply_crawl_delay_none_is_noop(self) -> None:
        limiter = TokenBucketLimiter(1.0)
        limiter.apply_crawl_delay(None)
        assert limiter.interval_sec == 1.0


# ---------- 環境変数からの間隔取得 ----------


class TestCrawlIntervalFromEnv:
    def test_default_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(CRAWL_INTERVAL_ENV, raising=False)
        assert crawl_interval_from_env() == DEFAULT_CRAWL_INTERVAL_SEC

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(CRAWL_INTERVAL_ENV, "2.5")
        assert crawl_interval_from_env() == 2.5

    def test_invalid_value_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(CRAWL_INTERVAL_ENV, "abc")
        assert crawl_interval_from_env() == DEFAULT_CRAWL_INTERVAL_SEC

    def test_negative_value_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(CRAWL_INTERVAL_ENV, "-3")
        assert crawl_interval_from_env() == DEFAULT_CRAWL_INTERVAL_SEC


# ---------- robots Crawl-Delay ----------


class TestRobotsCrawlDelay:
    def _parser(self, lines: list[str]) -> RobotFileParser:
        parser = RobotFileParser()
        parser.parse(lines)
        return parser

    def test_crawl_delay_5_makes_interval_5(self) -> None:
        """Crawl-Delay: 5 のとき間隔が 5 秒になることを確認する（受け入れ条件）。"""
        parser = self._parser(["User-agent: *", "Crawl-delay: 5"])
        with patch.object(pc, "crawl_interval_from_env", return_value=1.0):
            limiter = _make_rate_limiter(parser)
        assert limiter.interval_sec == 5.0

    def test_no_crawl_delay_returns_none(self) -> None:
        parser = self._parser(["User-agent: *", "Disallow: /private"])
        assert robots_crawl_delay(parser, build_user_agent()) is None

    def test_crawl_delay_matches_user_agent(self) -> None:
        parser = self._parser(["User-agent: WebSpec2Doc", "Crawl-delay: 7"])
        assert robots_crawl_delay(parser, build_user_agent()) == 7.0


# ---------- backoff ----------


class TestBackoffDelays:
    def test_exponential_sequence(self) -> None:
        assert list(backoff_delays()) == [2.0, 4.0, 8.0, 16.0, 32.0]

    def test_capped_at_max(self) -> None:
        delays = list(backoff_delays(initial_sec=30.0, max_sec=60.0, max_retries=4))
        assert delays == [30.0, 60.0, 60.0, 60.0]

    def test_max_retries_respected(self) -> None:
        assert len(list(backoff_delays())) == BACKOFF_MAX_RETRIES


class TestRetryOn429:
    def _run(self, statuses: list[int]) -> tuple[object, list[float]]:
        """statuses の順に crawl_page が応答した場合の _crawl_page_with_id 結果を返す。"""
        sleeps: list[float] = []
        results = iter(statuses)

        def fake_crawl_page(page: object, url: str, output_dir: object, auth: object) -> str:
            status = next(results)
            if status in (429, 503):
                raise RetryableHTTPError(url, status)
            return "page-data"

        with (
            patch.object(pc, "crawl_page", side_effect=fake_crawl_page),
            patch.object(pc.time, "sleep", side_effect=sleeps.append),
        ):
            result = _crawl_page_with_id(MagicMock(), "https://example.com/", "P001", None)
        return result, sleeps

    def test_retries_then_succeeds(self) -> None:
        result, sleeps = self._run([429, 503, 200])
        assert result == "page-data"
        assert sleeps == [2.0, 4.0]

    def test_gives_up_after_max_retries(self) -> None:
        result, sleeps = self._run([429] * (BACKOFF_MAX_RETRIES + 1))
        assert result is None
        assert sleeps == [2.0, 4.0, 8.0, 16.0, 32.0]

    def test_retry_exhausted_emits_page_failed(self) -> None:
        events: list[dict[str, object]] = []
        with (
            patch.object(
                pc, "crawl_page", side_effect=RetryableHTTPError("https://example.com/", 429)
            ),
            patch.object(pc.time, "sleep"),
        ):
            result = _crawl_page_with_id(
                MagicMock(), "https://example.com/", "P001", None, on_event=events.append
            )
        assert result is None
        failed = [e for e in events if e.get("event") == "page_failed"]
        assert failed and failed[0]["reason"] == "retry_exhausted"


# ---------- robots Disallow スキップ（受け入れ条件） ----------


@contextmanager
def _fake_browser(_auth: Path | None):
    yield MagicMock()


class TestRobotsDisallowSkip:
    def test_disallowed_url_skipped_and_event_emitted(self) -> None:
        """robots.txt で Disallow された URL がスキップされ、イベント通知されることを確認する。"""
        robots = RobotFileParser()
        robots.parse(["User-agent: *", "Disallow: /admin"])
        events: list[dict[str, object]] = []
        with (
            patch.object(pc, "_browser_page", _fake_browser),
            patch.object(pc, "_load_robots_parser", return_value=robots),
            patch.object(
                pc,
                "_crawl_page_with_id",
                side_effect=lambda _p, url, *_a, **_k: MagicMock(url=url),
            ),
            patch.object(pc.time, "sleep"),
        ):
            pages = pc.crawl_urls(
                ["https://example.com/admin/panel", "https://example.com/public"],
                on_event=events.append,
            )
        assert [p.url for p in pages] == ["https://example.com/public"]
        skipped = [e for e in events if e.get("event") == "page_skipped"]
        assert skipped
        assert skipped[0]["url"] == "https://example.com/admin/panel"
        assert skipped[0]["reason"] == "robots"


# ---------- User-Agent ----------


class TestUserAgent:
    def test_format_includes_version_and_repo_url(self) -> None:
        ua = build_user_agent()
        assert ua.startswith("WebSpec2Doc/")
        assert "+https://github.com/ma-garin/WebSpec2Doc" in ua

    def test_page_crawler_uses_explicit_user_agent(self) -> None:
        assert pc.USER_AGENT == build_user_agent()


# ---------- 監査ログ ----------


class TestAuditLog:
    def test_appends_jsonl_record(self, tmp_path: Path) -> None:
        path = append_audit_log(tmp_path, {"event": "crawl_started", "target_urls": ["u1"]})
        assert path is not None
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        record = json.loads(lines[0])
        assert record["event"] == "crawl_started"
        assert record["target_urls"] == ["u1"]
        assert "timestamp" in record

    def test_none_output_dir_is_noop(self) -> None:
        assert append_audit_log(None, {"event": "x"}) is None

    def test_crawl_urls_writes_audit_log(self, tmp_path: Path) -> None:
        """クロール開始時に対象URL・robots判定・間隔設定が audit.jsonl に記録されることを確認する。"""
        robots = RobotFileParser()
        robots.parse(["User-agent: *", "Disallow: /admin", "Crawl-delay: 5"])
        with (
            patch.object(pc, "_browser_page", _fake_browser),
            patch.object(pc, "_load_robots_parser", return_value=robots),
            patch.object(pc, "_crawl_page_with_id", return_value=None),
            patch.object(pc.time, "sleep"),
        ):
            pc.crawl_urls(
                ["https://example.com/admin/x", "https://example.com/public"],
                output_dir=tmp_path,
            )
        audit_path = tmp_path / "audit.jsonl"
        assert audit_path.exists()
        record = json.loads(audit_path.read_text(encoding="utf-8").strip().splitlines()[0])
        assert record["event"] == "crawl_started"
        assert record["target_urls"] == ["https://example.com/public"]
        assert record["robots_skipped_urls"] == ["https://example.com/admin/x"]
        assert record["robots_crawl_delay_sec"] == 5.0
        assert record["interval_sec"] == 5.0
        assert record["user_agent"] == build_user_agent()
