"""web/routes/api_v1.py のテスト"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.routes.api_v1 as api_v1_mod

from registry.site_registry import SiteConfig, save_site


def _client():
    return appmod.app.test_client()


def _register_blueprint_once() -> None:
    """api_v1 Blueprint をアプリに登録する（未登録の場合のみ）。"""
    registered = {bp.name for bp in appmod.app.blueprints.values()}
    if "api_v1" not in registered:
        appmod.app.register_blueprint(api_v1_mod.bp)


_register_blueprint_once()


# ─────────────────────────── GET /api/v1/sites ───────────────────────────


def test_api_sites_returns_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().get("/api/v1/sites")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "sites" in data


def test_api_sites_includes_saved_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    save_site(
        SiteConfig(
            domain="example.com",
            urls=("https://example.com/",),
            crawl_mode="crawl",
            depth=2,
            max_pages=20,
            formats=("html", "md"),
        ),
        tmp_path,
    )
    resp = _client().get("/api/v1/sites")
    assert resp.status_code == 200
    data = resp.get_json()
    assert any(s["domain"] == "example.com" for s in data["sites"])


# ─────────────────────────── GET /api/v1/sites/<domain>/report ───────────────────────────


def test_api_report_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().get("/api/v1/sites/nonexistent.com/report")
    assert resp.status_code == 404


def test_api_report_returns_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    domain_dir = tmp_path / "example.com"
    domain_dir.mkdir()
    (domain_dir / "report.json").write_text(json.dumps({"screens": []}), encoding="utf-8")
    resp = _client().get("/api/v1/sites/example.com/report")
    assert resp.status_code == 200
    assert resp.get_json()["screens"] == []


def test_api_report_invalid_domain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().get("/api/v1/sites/..invalid../report")
    assert resp.status_code in (400, 404)


# ─────────────────────────── GET /api/v1/sites/<domain>/snapshots ───────────────────────────


def test_api_snapshots_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().get("/api/v1/sites/nonexistent.com/snapshots")
    assert resp.status_code == 200
    assert resp.get_json()["snapshots"] == []


def test_api_snapshots_lists_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    snap_dir = tmp_path / "example.com" / "snapshots"
    snap_dir.mkdir(parents=True)
    (snap_dir / "20240101-120000.json").write_text("[]", encoding="utf-8")
    (snap_dir / "20240102-130000.json").write_text("[]", encoding="utf-8")
    resp = _client().get("/api/v1/sites/example.com/snapshots")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["domain"] == "example.com"
    assert len(data["snapshots"]) == 2


def test_api_snapshots_created_at_iso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    snap_dir = tmp_path / "example.com" / "snapshots"
    snap_dir.mkdir(parents=True)
    (snap_dir / "20240315-093045.json").write_text("[]", encoding="utf-8")
    resp = _client().get("/api/v1/sites/example.com/snapshots")
    snaps = resp.get_json()["snapshots"]
    assert snaps[0]["created_at"] == "2024-03-15T09:30:45"


# ─────────────────────────── GET /api/v1/sites/<domain>/diff ───────────────────────────


def test_api_diff_no_snapshots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().get("/api/v1/sites/nonexistent.com/diff")
    assert resp.status_code == 404
    assert "need at least 2" in resp.get_json()["error"]


def test_api_diff_one_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    snap_dir = tmp_path / "example.com" / "snapshots"
    snap_dir.mkdir(parents=True)
    (snap_dir / "20240101-120000.json").write_text("[]", encoding="utf-8")
    resp = _client().get("/api/v1/sites/example.com/diff")
    assert resp.status_code == 404


def test_api_diff_two_snapshots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    snap_dir = tmp_path / "example.com" / "snapshots"
    snap_dir.mkdir(parents=True)
    (snap_dir / "20240101-120000.json").write_text("[]", encoding="utf-8")
    (snap_dir / "20240102-130000.json").write_text("[]", encoding="utf-8")
    resp = _client().get("/api/v1/sites/example.com/diff")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "has_changes" in data
    assert data["has_changes"] is False


# ─────────────────────────── POST /api/v1/sites/<domain>/crawl ───────────────────────────


def test_api_crawl_requires_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """URL なしのリクエストは 400 を返す。"""
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().post(
        "/api/v1/sites/example.com/crawl",
        data=json.dumps({"depth": 2, "max_pages": 10}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_api_crawl_queues_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """URL 付きのリクエストは 202 とジョブIDを返す。"""
    from unittest.mock import patch

    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    with patch("web.services.job_queue._run_job"):
        resp = _client().post(
            "/api/v1/sites/example.com/crawl",
            data=json.dumps({"url": "https://example.com", "depth": 2, "max_pages": 10}),
            content_type="application/json",
        )
    assert resp.status_code == 202
    data = resp.get_json()
    assert "job_id" in data
    assert data["status"] == "queued"
    assert data["domain"] == "example.com"


def test_api_crawl_rejects_invalid_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """http/https 以外のスキームは 400 を返す。"""
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().post(
        "/api/v1/sites/example.com/crawl",
        data=json.dumps({"url": "ftp://badscheme.com"}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_api_crawl_invalid_domain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().post("/api/v1/sites/..bad../crawl", content_type="application/json")
    assert resp.status_code in (400, 404)


def test_api_job_status_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """存在しないジョブIDは 404 を返す。"""
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().get("/api/v1/jobs/nonexistent-job-id")
    assert resp.status_code == 404


def test_api_domain_jobs_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ジョブを作っていないドメインは空リストを返す。"""
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().get("/api/v1/sites/no-jobs-here.com/jobs")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["jobs"] == []
    assert data["domain"] == "no-jobs-here.com"


def test_api_healthz_returns_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """/api/v1/healthz は status=ok を返す。"""
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().get("/api/v1/healthz")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert "scheduler" in data


# ─────────────────────────── GET /api/v1/sites/<domain>/test-cases ───────────────────────────


def test_api_test_cases_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().get("/api/v1/sites/nonexistent.com/test-cases")
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 0


def test_api_test_cases_returns_candidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    domain_dir = tmp_path / "example.com"
    domain_dir.mkdir()
    candidates = [{"title": "ログインテスト", "automation_status": "automatable"}]
    (domain_dir / "playwright_candidates.json").write_text(
        json.dumps({"candidates": candidates}), encoding="utf-8"
    )
    resp = _client().get("/api/v1/sites/example.com/test-cases")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["domain"] == "example.com"
    assert data["total"] == 1
    assert data["candidates"][0]["title"] == "ログインテスト"


def test_api_test_cases_invalid_domain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().get("/api/v1/sites/..bad../test-cases")
    assert resp.status_code in (400, 404)


# ─────────────────────────── パストラバーサル防止 ───────────────────────────


def test_api_domain_traversal_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    resp = _client().get("/api/v1/sites/../etc/report")
    # 400 または 404 を返すこと（パストラバーサル拒否）
    assert resp.status_code in (400, 404)


# ─────────────────────────── _valid_domain ユニットテスト（web.validation に統一済み）───────────────────────────


def test_validate_domain_valid() -> None:
    from web.validation import _valid_domain

    assert _valid_domain("example.com") is True
    assert _valid_domain("localhost:8765") is True
    assert _valid_domain("sub.domain.co.jp") is True


def test_validate_domain_rejects_traversal() -> None:
    from web.validation import _valid_domain

    assert _valid_domain("../etc") is False
    assert _valid_domain("foo/../bar") is False


def test_validate_domain_rejects_slash() -> None:
    from web.validation import _valid_domain

    assert _valid_domain("foo/bar") is False


def test_validate_domain_rejects_empty() -> None:
    from web.validation import _valid_domain

    assert _valid_domain("") is False


# ─────────────────────────── _snapshot_ts_to_iso ユニットテスト ───────────────────────────


def test_snapshot_ts_to_iso_parses_correctly() -> None:
    assert api_v1_mod._snapshot_ts_to_iso("20240315-093045") == "2024-03-15T09:30:45"


def test_snapshot_ts_to_iso_fallback_on_invalid() -> None:
    result = api_v1_mod._snapshot_ts_to_iso("no-timestamp-here")
    assert result == "no-timestamp-here"
