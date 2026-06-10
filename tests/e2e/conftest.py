"""E2E テスト共通設定。

使用方法:
    make verify-ui          # Flask サーバーを自動起動して E2E 実行
    pytest tests/e2e/ -v    # サーバーが起動済みの場合に単独実行

必要条件:
    - venv が有効化されていること
    - playwright install chromium が完了していること
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Generator
from pathlib import Path

import pytest
import requests

try:
    from playwright.sync_api import sync_playwright  # noqa: F401
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

try:
    from playwright.sync_api import Page
except ImportError:
    Page = object  # type: ignore[assignment,misc]

# プロジェクトルートを sys.path に追加
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _server_is_up(url: str, timeout: float = 0.5) -> bool:
    try:
        requests.get(url, timeout=timeout)
        return True
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def require_playwright() -> None:
    """Playwright が未インストールの場合は E2E テストをスキップする。"""
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("playwright not installed — skipping E2E tests", allow_module_level=True)


@pytest.fixture(scope="session", autouse=True)
def flask_server() -> Generator[None, None, None]:
    """Flask サーバーを session スコープで起動・終了する。

    環境変数 WEBSPEC2DOC_E2E_EXTERNAL=1 が設定されている場合は
    外部サーバーを使用し、自動起動をスキップする。
    """
    if os.environ.get("WEBSPEC2DOC_E2E_EXTERNAL") == "1" or _server_is_up(BASE_URL):
        yield
        return

    env = {**os.environ, "FLASK_TESTING": "1", "PYTHONPATH": str(ROOT)}
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 最大10秒待機
    for _ in range(20):
        if _server_is_up(BASE_URL):
            break
        time.sleep(0.5)
    else:
        proc.terminate()
        pytest.skip(f"Flask サーバーが {BASE_URL} で起動しませんでした — E2E テストをスキップします。")

    yield

    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="session")
def browser_context_args() -> dict:
    return {
        "viewport": {"width": 1280, "height": 800},
        "locale": "ja-JP",
    }


# playwright タイムアウトを明示設定（デフォルト 30 秒では CI 環境で不安定になることがある）
@pytest.fixture(scope="session")
def playwright_timeout() -> int:
    return 45_000  # 45 秒


@pytest.fixture()
def page_with_screenshot(page: Page, request: pytest.FixtureRequest) -> Generator[Page, None, None]:
    """テスト失敗時に自動スクリーンショットを保存するページフィクスチャ。"""
    yield page
    if request.node.rep_call.failed if hasattr(request.node, "rep_call") else False:
        name = request.node.name.replace("/", "_").replace(":", "_")
        page.screenshot(path=str(SCREENSHOT_DIR / f"FAIL_{name}.png"), full_page=True)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Generator:
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)
