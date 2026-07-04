from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from crawler.network_interceptor import (
    NetworkCapture,
    _extract_response_fields,
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
