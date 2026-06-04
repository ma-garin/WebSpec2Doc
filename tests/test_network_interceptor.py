from __future__ import annotations

import json
from unittest.mock import MagicMock

from crawler.network_interceptor import (
    NetworkCapture,
    _extract_response_fields,
)


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
    capture._record(_make_response(url="https://example.com/api/missing", status=404, ct="application/json"))
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
