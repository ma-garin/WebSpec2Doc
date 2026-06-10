"""web/validation.py と web/security.py のテスト。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.routes.schedule as schedule_mod
from web.validation import _valid_url, error_json

# ─────────────── _valid_url ───────────────


def test_valid_url_accepts_https() -> None:
    assert _valid_url("https://example.com") is True


def test_valid_url_accepts_http() -> None:
    assert _valid_url("http://example.com/path") is True


def test_valid_url_accepts_with_port() -> None:
    assert _valid_url("http://localhost:3000") is True


def test_valid_url_rejects_empty() -> None:
    assert _valid_url("") is False


def test_valid_url_rejects_ftp() -> None:
    assert _valid_url("ftp://example.com") is False


def test_valid_url_rejects_file_scheme() -> None:
    assert _valid_url("file:///etc/passwd") is False


def test_valid_url_rejects_plain_string() -> None:
    assert _valid_url("example.com") is False


def test_valid_url_rejects_javascript_scheme() -> None:
    assert _valid_url("javascript:alert(1)") is False


# ─────────────── error_json ───────────────


def test_error_json_default_code() -> None:
    body, code = error_json("bad request")
    assert code == 400
    assert body == {"error": "bad request"}


def test_error_json_custom_code() -> None:
    body, code = error_json("not found", 404)
    assert code == 404
    assert body["error"] == "not found"


# ─────────────── セキュリティヘッダー ───────────────


def _client():
    return appmod.app.test_client()


def test_security_headers_present_on_get() -> None:
    """全レスポンスにセキュリティヘッダーが付与される。"""
    resp = _client().get("/")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert resp.headers.get("Referrer-Policy") == "same-origin"
    assert "Content-Security-Policy" in resp.headers


def test_csp_blocks_object_src() -> None:
    """CSP に object-src 'none' が含まれる。"""
    resp = _client().get("/")
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "object-src 'none'" in csp


def test_csp_allows_self_scripts() -> None:
    """CSP に script-src 'self' が含まれる。"""
    resp = _client().get("/")
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "'self'" in csp
    assert "script-src" in csp


# ─────────────── site_url バリデーション (schedule API) ───────────────


def test_schedule_rejects_invalid_site_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().post(
        "/schedule/config",
        data=json.dumps(
            {
                "domain": "example.com",
                "site_url": "ftp://badscheme.com",
                "interval": "daily",
                "notify_type": "none",
                "notify_endpoint": "",
                "severity_filter": "all",
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "site_url" in resp.get_json()["error"]


def test_schedule_accepts_valid_site_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().post(
        "/schedule/config",
        data=json.dumps(
            {
                "domain": "example.com",
                "site_url": "https://example.com",
                "interval": "daily",
                "notify_type": "none",
                "notify_endpoint": "",
                "severity_filter": "all",
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200


def test_schedule_accepts_empty_site_url(tmp_path: Path, monkeypatch) -> None:
    """site_url が空の場合はバリデーションをスキップ（後から設定できる）。"""
    monkeypatch.setattr(schedule_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().post(
        "/schedule/config",
        data=json.dumps(
            {
                "domain": "example.com",
                "site_url": "",
                "interval": "daily",
                "notify_type": "none",
                "notify_endpoint": "",
                "severity_filter": "all",
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
