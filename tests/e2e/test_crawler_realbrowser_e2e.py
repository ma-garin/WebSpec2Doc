"""実ブラウザ（Chromium）でクローラの状態探索・バリデーション実測を検証する E2E。

同梱デモサイト（DemoMart）を標的に、モックではなく本物の Playwright で
crawl_page を実行し、実サイトで壊れやすい機能の動作を保証する。

注意: pytest-playwright のセッション fixture（他の E2E テストが使用）は
メインスレッドで asyncio ループを保持し続けるため、同一スレッドで
sync_playwright() を直接呼ぶと「Sync API inside the asyncio loop」エラーに
なる。そこでクロールは専用スレッド内で実行する（parallel_crawler と同じ
スレッド内 sync API パターン）。
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import requests

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

DEMO_PORT = int(os.environ.get("WEBSPEC2DOC_E2E_DEMO_PORT", "8894"))
DEMO_URL = f"http://127.0.0.1:{DEMO_PORT}"
_CRAWL_TIMEOUT_SEC = 120


def _demo_is_up() -> bool:
    try:
        requests.get(f"{DEMO_URL}/", timeout=0.5)
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def demo_site() -> Generator[str, None, None]:
    """デモサイト（DemoMart）を module スコープで起動する。"""
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "demo" / "demo_site.py"), "--port", str(DEMO_PORT)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(20):
        if _demo_is_up():
            break
        time.sleep(0.5)
    else:
        proc.terminate()
        pytest.skip("デモサイトが起動しませんでした")
    yield DEMO_URL
    proc.terminate()
    proc.wait(timeout=5)


def _crawl_in_thread(url: str) -> Any:
    """asyncio ループのない専用スレッドでクローラ設定の実ブラウザクロールを行う。"""
    result: dict[str, Any] = {}

    def _run() -> None:
        os.environ["WEBSPEC2DOC_ALLOW_LOCAL"] = "1"
        from crawler.page_crawler import _browser_page, crawl_page

        try:
            with _browser_page(None) as page:
                result["page_data"] = crawl_page(page, url, None)
        except BaseException as exc:  # noqa: BLE001  # スレッド越しに例外を伝搬する
            result["error"] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=_CRAWL_TIMEOUT_SEC)
    if thread.is_alive():
        pytest.fail(f"クロールが {_CRAWL_TIMEOUT_SEC} 秒以内に完了しませんでした: {url}")
    if "error" in result:
        raise result["error"]
    return result["page_data"]


class TestRealBrowserCrawl:
    def test_crawl_page_dashboard_detects_modal_state(self, demo_site) -> None:
        """実ブラウザで、モーダルを持つページの画面状態が検出される。"""
        page_data = _crawl_in_thread(f"{demo_site}/dashboard.html")

        kinds = {state.kind for state in page_data.page_states}
        assert page_data.page_states, "画面状態が1つも検出されていない"
        assert "modal" in kinds or "tabpanel" in kinds or "accordion" in kinds

    def test_crawl_page_contact_measures_validation(self, demo_site) -> None:
        """実ブラウザで、必須未入力のバリデーションメッセージが実測される。"""
        page_data = _crawl_in_thread(f"{demo_site}/contact.html")

        observed = {obs.field_name: obs.message for obs in page_data.validation_observations}
        assert "name" in observed
        assert observed["name"].strip() != ""
        # 実測値は confidence=1.0・evidence 付き
        first = page_data.validation_observations[0]
        assert first.confidence == 1.0
        assert first.evidence is not None and first.evidence.selector

    def test_crawl_page_spa_records_transitions(self, demo_site) -> None:
        """実ブラウザで、pushState/hashchange の SPA 遷移が捕捉される。"""
        page_data = _crawl_in_thread(f"{demo_site}/spa.html")

        kinds = {t.kind for t in page_data.spa_transitions}
        assert kinds & {"pushstate", "hashchange"}, f"SPA 遷移が捕捉されていない: {kinds}"

    def test_crawl_page_checkout_fields_have_evidence(self, demo_site) -> None:
        """実ブラウザで、抽出フィールドに根拠（selector・bbox）が付与される。"""
        page_data = _crawl_in_thread(f"{demo_site}/checkout.html")

        fields = [f for form in page_data.forms for f in form.fields]
        assert fields
        with_evidence = [f for f in fields if f.evidence is not None]
        assert len(with_evidence) == len(fields), "evidence のないフィールドがある"
        assert any(f.evidence.bbox is not None for f in with_evidence), "bbox が1つも取れていない"
