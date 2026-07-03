"""実ブラウザ（Chromium）でクローラの状態探索・バリデーション実測を検証する E2E。

同梱デモサイト（DemoMart）を標的に、モックではなく本物の Playwright で
crawl_page を実行し、実サイトで壊れやすい機能の動作を保証する。
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

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

DEMO_PORT = int(os.environ.get("WEBSPEC2DOC_E2E_DEMO_PORT", "8894"))
DEMO_URL = f"http://127.0.0.1:{DEMO_PORT}"


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


@pytest.fixture(scope="module")
def crawler_page(demo_site: str) -> Generator[object, None, None]:
    """クローラと同じ設定（UA・ja-JP ロケール）の実ブラウザページ。"""
    os.environ["WEBSPEC2DOC_ALLOW_LOCAL"] = "1"
    from crawler.page_crawler import _browser_page

    with _browser_page(None) as page:
        yield page


class TestRealBrowserCrawl:
    def test_crawl_page_dashboard_detects_modal_state(self, crawler_page, demo_site) -> None:
        """実ブラウザで、モーダルを持つページの画面状態が検出される。"""
        from crawler.page_crawler import crawl_page

        page_data = crawl_page(crawler_page, f"{demo_site}/dashboard.html", None)

        kinds = {state.kind for state in page_data.page_states}
        assert page_data.page_states, "画面状態が1つも検出されていない"
        assert "modal" in kinds or "tabpanel" in kinds or "accordion" in kinds

    def test_crawl_page_contact_measures_validation(self, crawler_page, demo_site) -> None:
        """実ブラウザで、必須未入力のバリデーションメッセージが実測される。"""
        from crawler.page_crawler import crawl_page

        page_data = crawl_page(crawler_page, f"{demo_site}/contact.html", None)

        observed = {obs.field_name: obs.message for obs in page_data.validation_observations}
        assert "name" in observed
        assert observed["name"].strip() != ""
        # 実測値は confidence=1.0・evidence 付き
        first = page_data.validation_observations[0]
        assert first.confidence == 1.0
        assert first.evidence is not None and first.evidence.selector

    def test_crawl_page_spa_records_transitions(self, crawler_page, demo_site) -> None:
        """実ブラウザで、pushState/hashchange の SPA 遷移が捕捉される。"""
        from crawler.page_crawler import crawl_page

        page_data = crawl_page(crawler_page, f"{demo_site}/spa.html", None)

        kinds = {t.kind for t in page_data.spa_transitions}
        assert kinds & {"pushstate", "hashchange"}, f"SPA 遷移が捕捉されていない: {kinds}"

    def test_crawl_page_checkout_fields_have_evidence(self, crawler_page, demo_site) -> None:
        """実ブラウザで、抽出フィールドに根拠（selector・bbox）が付与される。"""
        from crawler.page_crawler import crawl_page

        page_data = crawl_page(crawler_page, f"{demo_site}/checkout.html", None)

        fields = [f for form in page_data.forms for f in form.fields]
        assert fields
        with_evidence = [f for f in fields if f.evidence is not None]
        assert len(with_evidence) == len(fields), "evidence のないフィールドがある"
        assert any(f.evidence.bbox is not None for f in with_evidence), "bbox が1つも取れていない"
