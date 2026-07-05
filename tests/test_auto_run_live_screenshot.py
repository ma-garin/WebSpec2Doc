from __future__ import annotations

from pathlib import Path

import app as appmod
import pytest
import web.routes.auto_run as auto_run_routes


def _client():
    return appmod.app.test_client()


@pytest.fixture
def output_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(auto_run_routes, "OUTPUT_DIR", tmp_path)
    return tmp_path


def test_returns_404_for_invalid_domain(output_dir: Path) -> None:
    response = _client().get("/api/autorun/live-screenshot?domain=../etc")
    assert response.status_code == 404


def test_returns_404_when_test_results_dir_missing(output_dir: Path) -> None:
    response = _client().get("/api/autorun/live-screenshot?domain=example.com")
    assert response.status_code == 404


def test_returns_404_when_no_png_present(output_dir: Path) -> None:
    results_dir = output_dir / "example.com" / "qa_process" / "test-results"
    results_dir.mkdir(parents=True)
    (results_dir / "notes.txt").write_text("no screenshots here", encoding="utf-8")

    response = _client().get("/api/autorun/live-screenshot?domain=example.com")
    assert response.status_code == 404


def test_returns_newest_png_from_nested_test_result_dirs(output_dir: Path) -> None:
    results_dir = output_dir / "example.com" / "qa_process" / "test-results"
    old_dir = results_dir / "login-test"
    new_dir = results_dir / "checkout-test"
    old_dir.mkdir(parents=True)
    new_dir.mkdir(parents=True)

    old_png = old_dir / "test-finished-1.png"
    new_png = new_dir / "test-finished-1.png"
    old_png.write_bytes(b"old-fake-png")
    new_png.write_bytes(b"new-fake-png")
    # 明示的に mtime をずらし、順序を確実にする
    import os
    import time

    now = time.time()
    os.utime(old_png, (now - 100, now - 100))
    os.utime(new_png, (now, now))

    response = _client().get("/api/autorun/live-screenshot?domain=example.com")
    assert response.status_code == 200
    assert response.data == b"new-fake-png"
    assert response.headers.get("Cache-Control") == "no-store"


def test_missing_domain_param_returns_404(output_dir: Path) -> None:
    response = _client().get("/api/autorun/live-screenshot")
    assert response.status_code == 404
