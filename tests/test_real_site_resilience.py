"""実サイト耐性強化（page_id 状態対応・per-origin レート・待ち戦略）のユニットテスト。"""

from __future__ import annotations

from analyzer.html_analyzer import analyze_pages, assign_page_ids
from crawler.action_explorer import _wait_for_validation_feedback
from crawler.page_crawler import PageData
from crawler.politeness import OriginRateLimiter


def _page(url: str, state_id: str = "default") -> PageData:
    return PageData(
        url=url,
        title="T",
        headings=(),
        links=(),
        forms=(),
        screenshot_path=None,
        state_id=state_id,
    )


# ---------- page_id の状態対応（同一 URL 別状態の ID 衝突解消） ----------


class TestPageIdStateSeparation:
    def test_same_url_different_states_get_distinct_ids(self) -> None:
        """同一 URL の別状態レコードが別 page_id になる。"""
        pages = analyze_pages(
            [
                _page("https://example.com/app", "default"),
                _page("https://example.com/app", "modal123"),
            ]
        )
        assert pages[0].page_id == "P001"
        assert pages[1].page_id == "P002"

    def test_ids_are_sequential_by_occurrence(self) -> None:
        pages = analyze_pages(
            [
                _page("https://example.com/a"),
                _page("https://example.com/b"),
                _page("https://example.com/a"),
            ]
        )
        assert [p.page_id for p in pages] == ["P001", "P002", "P003"]

    def test_assign_page_ids_keeps_first_occurrence(self) -> None:
        """URL マップは初出（正規ページ）の ID を保持する。"""
        ids = assign_page_ids(
            [
                _page("https://example.com/a"),
                _page("https://example.com/a"),
                _page("https://example.com/b"),
            ]
        )
        assert ids["https://example.com/a"] == "P001"
        assert ids["https://example.com/b"] == "P003"

    def test_canonicalizer_groups_states_with_distinct_ids(self) -> None:
        """analyze_pages 経由でも状態別 fingerprint が別グループになる。"""
        from analyzer.canonicalizer import group_canonical_screens

        pages = analyze_pages(
            [
                _page("https://example.com/app", "default"),
                _page("https://example.com/app", "modal123"),
            ]
        )
        grouped = group_canonical_screens(pages)
        assert grouped["P001"].canonical_key != grouped["P002"].canonical_key


# ---------- オリジン単位レート制御 ----------


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, sec: float) -> None:
        self.sleeps.append(sec)
        self.now += sec


class TestOriginRateLimiter:
    def test_different_origins_do_not_block_each_other(self) -> None:
        """別オリジンへの連続リクエストは互いに待たない。"""
        fake = _FakeClock()
        limiter = OriginRateLimiter(10.0, clock=fake.clock, sleeper=fake.sleep)
        assert limiter.acquire("https://a.example.com/page1") == 0.0
        assert limiter.acquire("https://b.example.com/page1") == 0.0
        assert fake.sleeps == []

    def test_same_origin_keeps_interval(self) -> None:
        """同一オリジンへの連続リクエストは間隔を守る。"""
        fake = _FakeClock()
        limiter = OriginRateLimiter(2.0, clock=fake.clock, sleeper=fake.sleep)
        limiter.acquire("https://a.example.com/page1")
        waited = limiter.acquire("https://a.example.com/page2")
        assert waited >= 2.0 - 1e-9

    def test_crawl_delay_applies_only_to_its_origin(self) -> None:
        """Crawl-Delay は対象オリジンだけを遅くする。"""
        fake = _FakeClock()
        limiter = OriginRateLimiter(1.0, clock=fake.clock, sleeper=fake.sleep)
        limiter.set_crawl_delay("https://slow.example.com", 5.0)

        limiter.acquire("https://slow.example.com/a")
        slow_wait = limiter.acquire("https://slow.example.com/b")
        assert slow_wait >= 5.0 - 1e-9

        limiter.acquire("https://fast.example.com/a")
        fast_wait = limiter.acquire("https://fast.example.com/b")
        assert fast_wait <= 1.0 + 1e-9

    def test_crawl_delay_after_first_acquire_still_applies(self) -> None:
        fake = _FakeClock()
        limiter = OriginRateLimiter(1.0, clock=fake.clock, sleeper=fake.sleep)
        limiter.acquire("https://a.example.com/1")
        limiter.set_crawl_delay("https://a.example.com", 4.0)
        waited = limiter.acquire("https://a.example.com/2")
        assert waited >= 1.0 - 1e-9  # 少なくとも既存トークン分は待つ

    def test_default_interval_property(self) -> None:
        limiter = OriginRateLimiter(3.0)
        assert limiter.interval_sec == 3.0


# ---------- バリデーション実測の明示的待ち戦略 ----------


class _WaitProbePage:
    """wait_for_selector / wait_for_timeout の呼び出しを記録するフェイク。"""

    def __init__(self, selector_appears: bool) -> None:
        self._selector_appears = selector_appears
        self.waited_selector = False
        self.waited_timeout = False

    def wait_for_selector(self, selector: str, timeout: int, state: str) -> None:
        self.waited_selector = True
        if not self._selector_appears:
            raise TimeoutError("フィードバックが出現しない")

    def wait_for_timeout(self, ms: int) -> None:
        self.waited_timeout = True


class TestValidationFeedbackWait:
    def test_waits_for_feedback_selector_first(self) -> None:
        """エラー表示要素の出現を明示的に待ち、出現すれば固定待ちしない。"""
        page = _WaitProbePage(selector_appears=True)
        _wait_for_validation_feedback(page)  # type: ignore[arg-type]
        assert page.waited_selector is True
        assert page.waited_timeout is False

    def test_falls_back_to_settle_wait_on_timeout(self) -> None:
        """出現しない場合は settle 待ちにフォールバックする。"""
        page = _WaitProbePage(selector_appears=False)
        _wait_for_validation_feedback(page)  # type: ignore[arg-type]
        assert page.waited_selector is True
        assert page.waited_timeout is True
