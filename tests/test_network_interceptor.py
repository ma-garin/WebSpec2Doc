from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from crawler.network_interceptor import (
    MutationBlocker,
    NetworkCapture,
    _extract_response_fields,
    log_mutation_block_summary,
    reset_mutation_log_state,
)
from crawler.page_crawler import _audit_mutation_blocked, _strip_query_for_audit


def _make_response(
    url: str = "https://example.com/api/users",
    method: str = "GET",
    status: int = 200,
    ct: str = "application/json",
    body: bytes = b'{"id":1,"name":"Alice"}',
) -> MagicMock:
    resp = MagicMock()
    resp.url = url
    resp.status = status
    resp.headers = {"content-type": ct}
    resp.body.return_value = body
    req = MagicMock()
    req.method = method
    resp.request = req
    return resp


def test_finalize_deduplicates() -> None:
    capture = NetworkCapture()
    for _ in range(3):
        capture._record(_make_response())
    result = capture.finalize()
    assert len(result) == 1
    assert result[0].method == "GET"
    assert result[0].path == "/api/users"


def test_static_extension_skipped() -> None:
    capture = NetworkCapture()
    capture._record(_make_response(url="https://example.com/style.css", ct="text/css"))
    assert capture.finalize() == ()


def test_html_navigation_skipped() -> None:
    capture = NetworkCapture()
    capture._record(_make_response(url="https://example.com/page", ct="text/html", status=200))
    assert capture.finalize() == ()


def test_json_api_recorded() -> None:
    capture = NetworkCapture()
    capture._record(_make_response(ct="application/json; charset=utf-8"))
    result = capture.finalize()
    assert len(result) == 1
    assert result[0].content_type == "application/json"


def test_sample_fields_extracted() -> None:
    body = json.dumps({"token": "abc", "user": {"id": 1}}).encode()
    capture = NetworkCapture()
    capture._record(_make_response(body=body))
    result = capture.finalize()
    assert "token" in result[0].sample_fields
    assert "user" in result[0].sample_fields


def test_extract_response_fields_dict() -> None:
    resp = _make_response(body=b'{"a":1,"b":2,"c":3}')
    fields = _extract_response_fields(resp)
    assert set(fields) == {"a", "b", "c"}


def test_extract_response_fields_list() -> None:
    resp = _make_response(body=b'[{"x":1,"y":2}]')
    fields = _extract_response_fields(resp)
    assert "x" in fields and "y" in fields


def test_extract_response_fields_too_large() -> None:
    big_body = b"x" * 40_000
    resp = _make_response(body=big_body)
    assert _extract_response_fields(resp) == ()


def test_404_response_recorded() -> None:
    capture = NetworkCapture()
    capture._record(
        _make_response(url="https://example.com/api/missing", status=404, ct="application/json")
    )
    result = capture.finalize()
    assert len(result) == 1
    assert result[0].status_code == 404


def test_attach_detach_no_error() -> None:
    page = MagicMock()
    capture = NetworkCapture()
    capture.attach(page)
    capture.detach()
    page.on.assert_called_once()
    page.remove_listener.assert_called_once()


# ---------- AC-4: MutationBlocker 遮断の監査ログ化 ----------


def test_strip_query_for_audit_removes_query_but_keeps_path() -> None:
    """遮断 URL のクエリ（トークン等の秘匿情報を含み得る）を落として記録する（§8）。"""
    url = "https://example.com/reset-password?token=secret123&uid=42"
    assert _strip_query_for_audit(url) == "https://example.com/reset-password"


def test_strip_query_for_audit_no_query_is_unchanged() -> None:
    url = "https://example.com/checkout"
    assert _strip_query_for_audit(url) == url


def test_blocked_mutation_written_to_audit(tmp_path: Path) -> None:
    """test_blocked_mutation_written_to_audit: blocked=[("POST", url?token=x)] のフェイク
    → audit に event=mutation_blocked・クエリ除去済み URL（AC-4）。"""
    blocked = [("POST", "https://example.com/api/submit?token=secret")]
    path = _audit_mutation_blocked(tmp_path, "https://example.com/form", blocked)
    assert path is not None
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "mutation_blocked"
    assert record["page_url"] == "https://example.com/form"
    assert record["blocked"] == [{"method": "POST", "url": "https://example.com/api/submit"}]


def test_no_audit_record_when_nothing_blocked(tmp_path: Path) -> None:
    """test_no_audit_record_when_nothing_blocked: blocked=[] → mutation_blocked
    行なし（AC-4）。"""
    result = _audit_mutation_blocked(tmp_path, "https://example.com/form", [])
    assert result is None
    assert not (tmp_path / "audit.jsonl").exists()


def test_multiple_blocked_requests_recorded_in_one_entry(tmp_path: Path) -> None:
    blocked = [
        ("POST", "https://example.com/api/a?x=1"),
        ("DELETE", "https://example.com/api/b"),
    ]
    _audit_mutation_blocked(tmp_path, "https://example.com/page", blocked)
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert len(record["blocked"]) == 2


# ---------- 画面ログの抑制（遮断ログでログが埋まる問題への対応） ----------


@pytest.fixture(autouse=True)
def _clean_mutation_log_state():
    """抑制状態はクロール単位のプロセス共有。テスト間で漏れないよう毎回初期化する。"""
    reset_mutation_log_state()
    yield
    reset_mutation_log_state()


def _fake_route(method: str, url: str) -> MagicMock:
    route = MagicMock()
    route.request.method = method
    route.request.url = url
    return route


def _block(urls: list[str], blocker: MutationBlocker | None = None) -> MutationBlocker:
    blocker = blocker or MutationBlocker(allow=False)
    for url in urls:
        blocker.handle_route(_fake_route("POST", url))
    return blocker


def _blocked_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if "遮断しました" in r.getMessage()]


def test_first_block_per_origin_is_logged_with_query_stripped(caplog) -> None:
    """オリジンごとの1件目は出す。URL はクエリを落とす（1件が複数行を占めないため）。"""
    with caplog.at_level("WARNING"):
        _block(["https://www.google.com/ccm/collect?rcb=13&frm=0&auid=365234435"])
    assert "https://www.google.com/ccm/collect" in caplog.text
    assert "rcb=13" not in caplog.text


def test_repeated_blocks_to_same_origin_are_not_logged_each_time(caplog) -> None:
    """同一オリジンの2件目以降は行を増やさない。1ページで何本も飛ぶビーコン対策。"""
    with caplog.at_level("WARNING"):
        _block([f"https://www.google.com/ccm/collect?n={i}" for i in range(10)])
    assert len(_blocked_lines(caplog)) == 1


def test_different_origins_are_each_logged_once(caplog) -> None:
    with caplog.at_level("WARNING"):
        _block(
            [
                "https://www.google.com/ccm/collect",
                "https://analytics.google.com/g/collect",
                "https://www.google.com/ccm/collect?again=1",
            ]
        )
    assert len(_blocked_lines(caplog)) == 2


def test_suppression_spans_pages(caplog) -> None:
    """ページをまたいでも 1 オリジン 1 行に保つ。

    MutationBlocker はページごとに作り直されるため、インスタンス変数に抑制状態を
    持たせると 300 ページで同じ行が 300 回出る。ここが今回の主眼。
    """
    with caplog.at_level("WARNING"):
        for _ in range(300):  # 300 ページぶんのクロールを模す
            _block(["https://www.google.com/ccm/collect", "https://analytics.google.com/g/collect"])
    assert len(_blocked_lines(caplog)) == 2


def test_summary_reports_suppressed_count(caplog) -> None:
    """まとめた件数はクロール終了時に 1 行で出す。伏せると遮断の有無が分からなくなる。"""
    _block([f"https://www.google.com/ccm/collect?n={i}" for i in range(5)])
    with caplog.at_level("WARNING"):
        log_mutation_block_summary()
    assert "https://www.google.com ×4件" in caplog.text


def test_no_summary_when_nothing_suppressed(caplog) -> None:
    _block(["https://www.google.com/ccm/collect"])
    with caplog.at_level("WARNING"):
        log_mutation_block_summary()
    assert "まとめました" not in caplog.text


def test_reset_allows_next_crawl_to_log_again(caplog) -> None:
    """抑制はクロール単位。次のクロールでは同じオリジンでも改めて 1 行出す。"""
    _block(["https://www.google.com/ccm/collect"])
    reset_mutation_log_state()
    caplog.clear()  # 1 回目のクロールぶんを数えないようにする
    with caplog.at_level("WARNING"):
        _block(["https://www.google.com/ccm/collect"])
    assert len(_blocked_lines(caplog)) == 1


def test_all_blocks_remain_in_blocked_list() -> None:
    """画面ログを間引いても、遮断そのものは全件残す（監査を落とさない）。"""
    blocker = _block([f"https://www.google.com/ccm/collect?n={i}" for i in range(10)])
    assert len(blocker.blocked) == 10
    assert blocker.blocked[0] == ("POST", "https://www.google.com/ccm/collect?n=0")
