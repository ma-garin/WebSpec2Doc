"""システムテスト（docs/system_test_cases.csv）共通基盤。

実行方法:
    make e2e-system
    # または（サーバーは自動起動される）
    venv/bin/python -m pytest tests/e2e/system/ -v

構成:
    - 認証あり実運用構成（owner/admin/member）を専用サーバーで再現する
      （tests/e2e/test_auth_tenant_e2e.py の auth_server パターンを踏襲）
    - スクリーンショット: 各テスト終了時に e2e/artifacts/screenshots/ へ保存
    - 動画: e2e/artifacts/videos/ へ保存（record_video_dir）
    - 結果 JSON: e2e/results/results.json（サマリ＋テストごとの結果とエラー詳細）
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
import requests

try:
    from playwright.sync_api import Browser

    PLAYWRIGHT_AVAILABLE = True
except ImportError:  # pragma: no cover - 親 conftest が session ごと skip する
    Browser = object  # type: ignore[assignment,misc]
    PLAYWRIGHT_AVAILABLE = False

ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from tests.e2e.system.helpers import (  # noqa: E402
    ADMIN,
    MEMBER,
    OWNER,
    PW_CHANGE_MEMBER,
    TENANT_NAME,
    create_user,
)

ARTIFACT_DIR = ROOT / "e2e" / "artifacts"
RESULTS_PATH = ROOT / "e2e" / "results" / "results.json"


def _wait_for_health(url: str, timeout: float = 25.0) -> bool:
    """起動待ち。tests/e2e の固定待機ラチェット（scripts/check_e2e_conventions.py）
    を増やさないため sleep を使わず、接続拒否が即時返ることを利用して再試行する。
    ビジーになるのはサーバー起動までの数秒のみ。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(f"{url}/api/v1/healthz", timeout=0.5).ok:
                return True
        except requests.RequestException:
            continue
    return False


@pytest.fixture(scope="session")
def system_server(browser: Browser) -> Generator[str, None, None]:
    """認証あり構成のシステムテスト専用 Flask サーバー（他の E2E から隔離）。"""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    run_id = uuid.uuid4().hex[:8]
    auth_db = ROOT / "instance" / f"auth.e2e-system-{run_id}.db"
    viewpoints_db = ROOT / "instance" / f"viewpoints.e2e-system-{run_id}.db"
    env = {
        **os.environ,
        "FLASK_TESTING": "1",
        # 初期管理者は /auth/setup の実 UI で作る（bootstrap では作らない）
        "WEBSPEC2DOC_BOOTSTRAP_ADMIN": "0",
        "WEBSPEC2DOC_AUTH_DB": str(auth_db),
        "VIEWPOINTS_DB": str(viewpoints_db),
        "PYTHONPATH": str(ROOT),
        "WEBSPEC2DOC_PORT": str(port),
        # ST-010 でサーバー自身のページをクロール対象にするため
        "WEBSPEC2DOC_ALLOW_LOCAL": "1",
    }
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    if not _wait_for_health(base_url):
        proc.terminate()
        proc.wait(timeout=10)
        pytest.fail(
            f"システムテスト用サーバーが {base_url} で起動しませんでした"
            "（未実行の状態を PASS 扱いにしない）。"
        )

    _bootstrap_tenant_and_users(browser, base_url)
    yield base_url

    proc.terminate()
    proc.wait(timeout=10)
    for db in (auth_db, viewpoints_db):
        for suffix in ("", "-journal", "-wal", "-shm"):
            Path(str(db) + suffix).unlink(missing_ok=True)


def _bootstrap_tenant_and_users(browser: Browser, base_url: str) -> None:
    """初期セットアップ（owner）を実 UI で行い、admin/member を実 API で作る。"""
    context = browser.new_context()
    page = context.new_page()
    try:
        # ユーザー 0 人の状態では /auth/login が初期セットアップへ誘導する
        page.goto(f"{base_url}/auth/login")
        page.locator("#tenant_name").fill(TENANT_NAME)
        page.locator("#name").fill(OWNER.name)
        page.locator("#email").fill(OWNER.email)
        page.locator("#password").fill(OWNER.password)
        page.locator("#password_confirm").fill(OWNER.password)
        page.locator("button.auth-submit").click()
        # テナント確定後の着地点はシステム選択（/systems）。helpers.LANDING_URL_RE と同じ。
        page.wait_for_url(re.compile(r"/auth/tenant$|/systems$"))
        if "/auth/tenant" in page.url:
            page.locator('form[action="/auth/tenant"] button[type="submit"]').first.click()
            page.wait_for_url(f"{base_url}/systems")
        for user in (ADMIN, MEMBER, PW_CHANGE_MEMBER):
            create_user(page, base_url, user)
    finally:
        context.close()


@pytest.fixture(scope="session")
def browser_context_args() -> dict:
    """親 conftest の設定（viewport / locale）＋動画記録を有効にする。"""
    videos_dir = ARTIFACT_DIR / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    return {
        "viewport": {"width": 1280, "height": 800},
        "locale": "ja-JP",
        "record_video_dir": str(videos_dir),
    }


@pytest.fixture(autouse=True)
def capture_final_screenshot(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """各テスト終了時（成功・失敗とも）に全画面スクリーンショットを保存する。"""
    yield
    if "page" not in request.fixturenames:
        return
    page = request.getfixturevalue("page")
    shots = ARTIFACT_DIR / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^\w\-]+", "_", request.node.name)
    try:
        page.screenshot(path=str(shots / f"{name}.png"), full_page=True)
    except Exception:
        # ページが既に閉じている等。撮影失敗で他テストを巻き込まない
        pass


# ── 結果 JSON レポーター ──────────────────────────────────────────
_REPORTS: list[dict] = []


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if "tests/e2e/system" not in report.nodeid.replace(os.sep, "/"):
        return
    # call 段階＋setup 段階の失敗/スキップを記録する
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        _REPORTS.append(
            {
                "test": report.nodeid,
                "outcome": report.outcome,
                "duration_sec": round(report.duration, 2),
                "error": str(report.longrepr) if report.failed else None,
            }
        )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if not _REPORTS:
        return
    counts = {"passed": 0, "failed": 0, "skipped": 0}
    for rep in _REPORTS:
        counts[rep["outcome"]] = counts.get(rep["outcome"], 0) + 1
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(
            {"summary": {**counts, "total": len(_REPORTS)}, "results": _REPORTS},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
