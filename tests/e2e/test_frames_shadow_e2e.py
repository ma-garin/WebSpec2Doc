"""iframe / Shadow DOM 対応（SPEC-3-1）の実ブラウザ E2E。

同梱デモサイト（DemoMart）の legacy_frame.html（同一オリジン iframe）・
components.html（open/closed shadow DOM）を標的に、crawl_page が
フレーム境界・シャドウ境界を越えて正しく仕様を抽出できることを検証する。

pytest-playwright のセッション fixture が保持する asyncio ループとの衝突を
避けるため、ブラウザ処理は専用スレッドで実行する
（tests/e2e/test_capture_realbrowser_e2e.py と同じパターン）。
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

DEMO_PORT = int(os.environ.get("WEBSPEC2DOC_E2E_FRAMES_PORT", "8898"))
DEMO_URL = f"http://127.0.0.1:{DEMO_PORT}"
_THREAD_TIMEOUT_SEC = 120


def _demo_is_up() -> bool:
    try:
        requests.get(f"{DEMO_URL}/", timeout=0.5)
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def demo_site() -> Generator[str, None, None]:
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
    """asyncio ループのない専用スレッドで crawl_page を実行する。"""
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
    thread.join(timeout=_THREAD_TIMEOUT_SEC)
    if thread.is_alive():
        pytest.fail(f"クロールが {_THREAD_TIMEOUT_SEC} 秒以内に完了しませんでした: {url}")
    if "error" in result:
        raise result["error"]
    return result["page_data"]


class TestIframeExtraction:
    def test_iframe_links_and_headings_merged(self, demo_site: str) -> None:
        """同一オリジン iframe 内のリンク・見出しが親ページの仕様に統合される。"""
        page_data = _crawl_in_thread(f"{demo_site}/legacy_frame.html")

        assert any(link.endswith("/products.html") for link in page_data.links)
        assert any("フレーム内お問い合わせ" in h for h in page_data.headings)

    def test_same_origin_iframe_recorded_as_readable(self, demo_site: str) -> None:
        """同一オリジン iframe が embedded_frames に readable=True で記録される。"""
        page_data = _crawl_in_thread(f"{demo_site}/legacy_frame.html")

        frame_records = [
            ef for ef in page_data.embedded_frames if ef.src.endswith("frame_content.html")
        ]
        assert (
            frame_records
        ), f"iframe が embedded_frames に記録されていない: {page_data.embedded_frames}"
        assert frame_records[0].readable is True


class TestShadowDomExtraction:
    def test_shadow_form_field_has_evidence(self, demo_site: str) -> None:
        """open shadow DOM 内のフォームフィールドが evidence 付きで抽出される。"""
        page_data = _crawl_in_thread(f"{demo_site}/components.html")

        fields = [f for form in page_data.forms for f in form.fields]
        shadow_field = next((f for f in fields if f.name == "shadow-field"), None)
        assert shadow_field is not None, f"shadow 内フィールドが抽出されていない: {fields}"
        assert shadow_field.required is True
        assert shadow_field.evidence is not None
        assert shadow_field.evidence.selector == "#shadow-email"

    def test_shadow_modal_state_detected(self, demo_site: str) -> None:
        """open shadow DOM 内のボタンで出現するモーダルが状態として検出される。"""
        page_data = _crawl_in_thread(f"{demo_site}/components.html")

        modal_states = [s for s in page_data.page_states if s.kind == "modal"]
        assert modal_states, f"shadow 内モーダル状態が検出されていない: {page_data.page_states}"

    def test_closed_shadow_reported_as_unreadable(self, demo_site: str) -> None:
        """closed shadow root が「検出したが読めない」として embedded_frames に記録される。"""
        page_data = _crawl_in_thread(f"{demo_site}/components.html")

        closed_records = [ef for ef in page_data.embedded_frames if ef.src.startswith("shadow:")]
        assert closed_records, f"closed shadow が記録されていない: {page_data.embedded_frames}"
        assert closed_records[0].readable is False
        assert "my-closed-widget" in closed_records[0].src


class TestExistingPagesUnaffected:
    def test_dashboard_still_detects_modal_without_regression(self, demo_site: str) -> None:
        """既存ページ（iframe/shadow を含まない）の挙動が変化しないことを確認する。"""
        page_data = _crawl_in_thread(f"{demo_site}/dashboard.html")

        kinds = {state.kind for state in page_data.page_states}
        assert page_data.page_states
        assert "modal" in kinds or "tabpanel" in kinds or "accordion" in kinds
        assert page_data.embedded_frames == ()
