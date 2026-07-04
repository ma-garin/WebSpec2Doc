"""リバース生成（SPEC-2-1）の実ブラウザ E2E。

デモサイトを標的に、(1) クロールでインベントリを作り、(2) 実ブラウザで
テスターの操作（モーダルを開く）を記録し、(3) 逆生成したテストケースに
モーダル状態が観測結果として載ること、(4) recorded_candidates.json が
generate_spec_ts でエラーなく .spec.ts になることを検証する。

pytest-playwright のセッション fixture が保持する asyncio ループとの衝突を
避けるため、ブラウザ処理は専用スレッドで実行する
（tests/e2e/test_capture_realbrowser_e2e.py と同じパターン）。
"""

from __future__ import annotations

import json
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

DEMO_PORT = int(os.environ.get("WEBSPEC2DOC_E2E_REVERSE_PORT", "8899"))
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


def _run_in_thread(target: Any) -> dict[str, Any]:
    """asyncio ループのない専用スレッドでブラウザ処理を実行する。"""
    result: dict[str, Any] = {}

    def _run() -> None:
        os.environ["WEBSPEC2DOC_ALLOW_LOCAL"] = "1"
        try:
            result["value"] = target()
        except BaseException as exc:  # noqa: BLE001  # スレッド越しに例外を伝搬する
            result["error"] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=_THREAD_TIMEOUT_SEC)
    if thread.is_alive():
        pytest.fail("ブラウザ処理がタイムアウトしました")
    if "error" in result:
        raise result["error"]
    return result


class TestReverseAssetsE2E:
    def test_recorded_modal_click_reversed_to_case(self, demo_site: str, tmp_path: Path) -> None:
        """記録したモーダル操作が逆生成テストケースの観測結果に載る。"""

        def _scenario() -> dict[str, Any]:
            from analyzer.html_analyzer import analyze_pages
            from capture.coverage import load_session_events
            from capture.reverse_generator import generate_recorded_assets
            from capture.session_recorder import SessionRecorder
            from crawler.page_crawler import _browser_page, crawl_page
            from generator.json_reporter import generate_json_report
            from graph.transition_graph import build_graph

            with _browser_page(None) as page:
                dashboard = crawl_page(page, f"{demo_site}/dashboard.html", None)
                analyzed = analyze_pages([dashboard])
                report = json.loads(
                    generate_json_report(analyzed, build_graph(analyzed), demo_site)
                )

                page.goto(f"{demo_site}/dashboard.html")
                session_path = tmp_path / "sessions" / "session_001.jsonl"
                recorder = SessionRecorder(page=page, session_path=session_path)
                recorder.start()
                page.click("#open-withdraw-modal")
                page.wait_for_timeout(300)
                recorder.poll_once()
                recorder.flush()

            events = load_session_events(tmp_path)
            return generate_recorded_assets(report, events)

        assets = _run_in_thread(_scenario)["value"]
        assert len(assets["test_cases"]) == 1
        case = assets["test_cases"][0]
        assert any("画面状態" in step["observed"] for step in case["steps"])
        assert case["page_ids"] == ["P001"]

    def test_recorded_candidates_feed_spec_ts(self, demo_site: str, tmp_path: Path) -> None:
        """recorded_candidates.json が generate_spec_ts でエラーなく .spec.ts になる。"""

        def _scenario() -> dict[str, Any]:
            from analyzer.html_analyzer import analyze_pages
            from capture.coverage import load_session_events
            from capture.reverse_generator import generate_recorded_assets, save_recorded_assets
            from capture.session_recorder import SessionRecorder
            from crawler.page_crawler import _browser_page, crawl_page
            from generator.json_reporter import generate_json_report
            from graph.transition_graph import build_graph

            with _browser_page(None) as page:
                contact = crawl_page(page, f"{demo_site}/contact.html", None)
                analyzed = analyze_pages([contact])
                report = json.loads(
                    generate_json_report(analyzed, build_graph(analyzed), demo_site)
                )

                page.goto(f"{demo_site}/contact.html")
                session_path = tmp_path / "sessions" / "session_001.jsonl"
                recorder = SessionRecorder(page=page, session_path=session_path)
                recorder.start()
                page.click("button[type=submit]")
                page.wait_for_timeout(200)
                recorder.poll_once()
                recorder.flush()

            events = load_session_events(tmp_path)
            assets = generate_recorded_assets(report, events)
            save_recorded_assets(assets, tmp_path, domain="demo")
            return {}

        _run_in_thread(_scenario)

        from web.services.spec_ts_generator import generate_spec_ts

        output_path = tmp_path / "recorded.spec.ts"
        result = generate_spec_ts("demo", tmp_path / "recorded_candidates.json", output_path)
        content = result.read_text(encoding="utf-8")
        assert "page.goto(" in content
        assert "test(" in content
