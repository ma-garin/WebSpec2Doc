"""新側リンクの疎通確認（link_checker）の単体テスト。フェイク opener で HTTP をモックする。"""

from __future__ import annotations

from urllib.error import URLError

from diff.link_checker import (
    STATUS_BROKEN,
    STATUS_OK,
    STATUS_UNCONFIRMED,
    check_link,
    check_links,
)


def test_link_checker_records_404() -> None:
    """新側に 404 を返すリンクは broken・HTTP ステータス付きで記録される（AC-5）。"""

    def fake_opener(url: str, timeout_sec: float) -> int:
        return 404

    result = check_link("https://new.example.com/missing", "P002", opener=fake_opener)

    assert result.status == STATUS_BROKEN
    assert result.http_status == 404
    assert result.source_page_id == "P002"
    assert "404" in result.reason


def test_link_checker_records_ok() -> None:
    """200 を返すリンクは ok として記録される。"""

    def fake_opener(url: str, timeout_sec: float) -> int:
        return 200

    result = check_link("https://new.example.com/ok", "P001", opener=fake_opener)

    assert result.status == STATUS_OK
    assert result.http_status == 200


def test_link_timeout_marked_unconfirmed() -> None:
    """タイムアウトするリンクは「切れ」と断定せず未確認として記録される（5-4 節）。

    sleeper をフェイク注入し、backoff の実待機（最大約 62 秒）を発生させない。
    """

    def always_timeout(url: str, timeout_sec: float) -> int:
        raise TimeoutError("simulated timeout")

    sleeps: list[float] = []
    result = check_link(
        "https://new.example.com/slow",
        "P003",
        opener=always_timeout,
        sleeper=sleeps.append,
    )

    assert result.status == STATUS_UNCONFIRMED
    assert result.http_status is None
    assert "未確認" in result.reason
    assert len(sleeps) > 0, "backoff の待機秒数列が呼ばれていない"


def test_link_checker_retries_retryable_status_then_succeeds() -> None:
    """429 を受けても politeness の backoff で再試行し、最終的に成功を記録する。"""
    calls = {"count": 0}

    def flaky_opener(url: str, timeout_sec: float) -> int:
        calls["count"] += 1
        if calls["count"] == 1:
            return 429
        return 200

    result = check_link(
        "https://new.example.com/flaky",
        "P004",
        opener=flaky_opener,
        sleeper=lambda _sec: None,
    )

    assert result.status == STATUS_OK
    assert calls["count"] == 2


def test_check_links_processes_multiple_targets() -> None:
    """複数リンクを一括検査できる。"""

    def opener(url: str, timeout_sec: float) -> int:
        if url.endswith("missing"):
            return 404
        return 200

    results = check_links(
        [("https://new.example.com/ok", "P001"), ("https://new.example.com/missing", "P002")],
        opener=opener,
    )

    assert len(results) == 2
    assert results[0].status == STATUS_OK
    assert results[1].status == STATUS_BROKEN


def test_link_checker_url_error_marked_unconfirmed() -> None:
    """接続失敗（URLError）も「切れ」と断定せず未確認として記録される。"""

    def connection_error(url: str, timeout_sec: float) -> int:
        raise URLError("connection refused")

    result = check_link(
        "https://new.example.com/down", "P005", opener=connection_error, sleeper=lambda _sec: None
    )

    assert result.status == STATUS_UNCONFIRMED
