"""レーンD-1: セキュリティ回帰テスト（R3-20）。

docs/0706_plan.md レーンDの受け入れ基準が指す5項目のうち、既に別ファイルで
green だったものは重複実装せず参照コメントのみ残す（テスト対象コードは同一）:
- CSPにCDNを許可していないこと          → tests/test_validation_security.py::test_csp_does_not_allow_mermaid_cdn
- /api/autorun/approve のdeviceホワイトリスト → tests/test_auto_run.py::TestApproveRoute::test_approve_rejects_unknown_device_falls_back_pc
- 実況リストのtitle/error切り詰め        → tests/test_auto_run.py::test_title_and_error_are_truncated
本ファイルでは、まだどこにも無かった「APIレスポンス（404含む）へのセキュリティ
ヘッダー付与」のみを新規に検証する。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod  # noqa: E402
from web.security import _CSP  # noqa: E402


def _client():
    return appmod.app.test_client()


def test_csp_unchanged_no_cdn_allowlisted() -> None:
    """B-1（Mermaid同梱）実装後もCSPが外部CDNをallowlistしていないことの回帰ガード。"""
    for host in ("cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com"):
        assert host not in _CSP


def test_security_headers_on_api_responses() -> None:
    """404を含むAPI/ファイル配信レスポンスにもセキュリティヘッダーが付与されること。"""
    client = _client()
    responses = [
        client.get("/api/autorun/status?job_id=does-not-exist"),  # 404
        client.get("/preview"),  # path未指定 → 404
    ]
    for resp in responses:
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert "Content-Security-Policy" in resp.headers


def test_approve_device_whitelist() -> None:
    """/api/autorun/approve の device ホワイトリスト回帰ガード（A-3・実装は auto_run.py）。

    詳細ケースは tests/test_auto_run.py::TestApproveRoute に既存。ここでは
    セキュリティ観点の最小再確認のみ行う。
    """
    import json as _json
    from unittest.mock import patch

    from web.routes.auto_run import AutoRunJob, _now_iso

    job = AutoRunJob(
        job_id="sec-test-job",
        url="https://example.com",
        domain="example.com",
        started_at=_now_iso(),
        status="awaiting_approval",
    )
    with (
        patch("web.routes.auto_run._JOBS", {job.job_id: job}),
        patch("web.routes.auto_run.threading.Thread"),
    ):
        res = _client().post(
            "/api/autorun/approve",
            data=_json.dumps({"job_id": job.job_id, "device": "__proto__"}),
            content_type="application/json",
        )
    assert res.status_code == 200
    assert job.run_policy["device"] == "pc"


def test_live_tests_error_is_truncated(tmp_path: Path) -> None:
    """実況応答の title/error 切り詰め回帰ガード（A-2・負荷/ログ漏えい対策）。

    詳細ケースは tests/test_auto_run.py::test_title_and_error_are_truncated に既存。
    """
    import json as _json
    from unittest.mock import patch

    from web.routes.auto_run import AutoRunJob, _current_test_progress, _now_iso

    job = AutoRunJob(
        job_id="sec-test-job-2",
        url="https://example.com",
        domain="example.com",
        started_at=_now_iso(),
    )
    qa_dir = tmp_path / "example.com" / "qa_process"
    qa_dir.mkdir(parents=True)
    ndjson_path = qa_dir / "playwright_progress.ndjson"
    lines = [
        _json.dumps({"event": "begin", "total": 1}),
        _json.dumps(
            {
                "event": "test",
                "title": "<img src=x onerror=alert(1)>" * 20,
                "status": "failed",
                "error": "E" * 500,
            }
        ),
    ]
    ndjson_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with patch("web.routes.auto_run.OUTPUT_DIR", tmp_path):
        progress = _current_test_progress(job)

    assert len(progress["tests"][0]["title"]) == 200
    assert len(progress["tests"][0]["error"]) == 300
