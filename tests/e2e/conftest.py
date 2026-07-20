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
from urllib.parse import urlparse

import pytest
import requests

try:
    from playwright.sync_api import sync_playwright  # noqa: F401

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

try:
    from playwright.sync_api import Page, expect
except ImportError:
    Page = object  # type: ignore[assignment,misc]
    expect = None  # type: ignore[assignment]

# プロジェクトルートを sys.path に追加
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# ── 既知 flaky の隔離（quarantine）──────────────────────────────────
# 隔離機構は残すが、現在は 0 件（Phase A で全件を根本修正して解除した）。
# 恒久修正の記録は docs/sdlc/40_test/WS2D-DL-001_不具合管理台帳.md を参照。
# 将来 flaky が出た場合はここに "ファイル::クラス::テスト" を追加する。
# 一時解除するには WEBSPEC2DOC_E2E_NO_QUARANTINE=1 を設定する。
_QUARANTINED_TESTS: frozenset[str] = frozenset()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """隔離指定のテストをスキップする（環境変数で無効化可能）。現在は 0 件。"""
    if not _QUARANTINED_TESTS or os.environ.get("WEBSPEC2DOC_E2E_NO_QUARANTINE") == "1":
        return
    marker = pytest.mark.skip(reason="quarantined: 既知 flaky（tests/e2e/conftest.py 参照）")
    for item in items:
        for suffix in _QUARANTINED_TESTS:
            # nodeid 例: tests/e2e/test_x.py::TestY::test_z[chromium]
            base = item.nodeid.split("[", 1)[0]
            if base.endswith(suffix):
                item.add_marker(marker)
                break


def _server_is_up(url: str, timeout: float = 0.5) -> bool:
    """WebSpec2Doc 自身が応答しているかを確認する。

    生存確認だけでは、同じポートを別アプリが握っていても True になり、
    E2E が「別アプリを検証して緑」という偽陽性を出す。健全性エンドポイントの
    中身まで見て、WebSpec2Doc であることを確かめる。
    """
    try:
        response = requests.get(f"{url.rstrip('/')}/api/v1/healthz", timeout=timeout)
        payload = response.json()
    except Exception:
        return False
    return isinstance(payload, dict) and "scheduler" in payload


def _port_is_taken_by_other_app(url: str, timeout: float = 0.5) -> bool:
    """ポートは埋まっているが WebSpec2Doc ではない、という状態を検出する。"""
    try:
        requests.get(url, timeout=timeout)
    except Exception:
        return False
    return not _server_is_up(url, timeout)


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

    if _port_is_taken_by_other_app(BASE_URL):
        pytest.fail(
            f"{BASE_URL} で WebSpec2Doc 以外のアプリが応答しています。"
            "そのまま実行すると別アプリを検証して緑になるため中止しました。"
            "該当プロセスを止めるか、WEBSPEC2DOC_E2E_URL で別ポートを指定してください。"
        )

    # app.py は WEBSPEC2DOC_PORT を見て待ち受けポートを決める。
    # BASE_URL（= WEBSPEC2DOC_E2E_URL）で別ポートを指定しても、起動側へ
    # そのポートを渡さないと既定 8765 で起動して疎通せず、全テストが
    # スキップ→「緑」になってしまう（E2E ゲートが形骸化する）。
    # BASE_URL のポートを起動側にも必ず渡す。
    base_port = urlparse(BASE_URL).port or 8765
    env = {
        **os.environ,
        "FLASK_TESTING": "1",
        "PYTHONPATH": str(ROOT),
        "WEBSPEC2DOC_PORT": str(base_port),
    }
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
        # ここを skip にすると「サーバーが起動しなかった＝未検証」を「緑」と
        # 誤認させる。E2E を要求した以上、起動できないのは失敗として扱う。
        pytest.fail(
            f"Flask サーバーが {BASE_URL} で起動しませんでした。E2E は未実行です"
            "（この状態を PASS 扱いにしない）。"
        )

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


@pytest.fixture(scope="session", autouse=True)
def configure_expect_timeout() -> None:
    """非同期UIの期待値待機を、連続E2E向けに明示設定する。"""
    if expect is not None:
        expect.set_options(timeout=15_000)


@pytest.fixture(autouse=True)
def configure_page_timeouts(request: pytest.FixtureRequest) -> None:
    """page を使うテストに、長い連続実行向けの実タイムアウトを適用する。"""
    if "page" not in request.fixturenames:
        return
    page = request.getfixturevalue("page")
    page.set_default_timeout(45_000)
    page.set_default_navigation_timeout(60_000)


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
