"""実ブラウザでの操作記録→探索カバレッジの E2E。

デモサイトを標的に、(1) クロールでインベントリ（分母）を作り、
(2) 実ブラウザ上でテスターの操作を模擬しながらセッション記録し、
(3) 突合したカバレッジにモーダル状態の足跡が載ることを検証する。

pytest-playwright のセッション fixture が保持する asyncio ループとの衝突を
避けるため、ブラウザ処理は専用スレッドで実行する（既存の実ブラウザ E2E と
同じパターン）。
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

DEMO_PORT = int(os.environ.get("WEBSPEC2DOC_E2E_CAPTURE_PORT", "8896"))
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


class TestCaptureCoverageE2E:
    def test_recorded_modal_state_appears_in_coverage(self, demo_site: str, tmp_path: Path) -> None:
        """記録した実操作（モーダルを開く）がヒートマップの分子として集計される。"""

        def _scenario() -> dict[str, Any]:
            from analyzer.html_analyzer import analyze_pages
            from capture.coverage import (
                compute_exploration_coverage,
                load_session_events,
            )
            from capture.session_recorder import SessionRecorder
            from crawler.page_crawler import _browser_page, crawl_page
            from generator.json_reporter import generate_json_report
            from graph.transition_graph import build_graph

            with _browser_page(None) as page:
                # (1) 分母: dashboard（モーダルあり）と contact をクロール
                dashboard = crawl_page(page, f"{demo_site}/dashboard.html", None)
                contact = crawl_page(page, f"{demo_site}/contact.html", None)
                analyzed = analyze_pages([dashboard, contact])
                report = json.loads(
                    generate_json_report(analyzed, build_graph(analyzed), demo_site)
                )

                # (2) 分子: テスターの操作を模擬（dashboard を開いてモーダルを開く）
                # 実利用と同じく、対象ページへ移動してから記録を開始する
                page.goto(f"{demo_site}/dashboard.html")
                session_path = tmp_path / "sessions" / "session_001.jsonl"
                recorder = SessionRecorder(page=page, session_path=session_path)
                recorder.start()
                page.click("#open-withdraw-modal")
                page.wait_for_timeout(300)
                recorder.poll_once()
                recorder.flush()

            # (3) 突合
            events = load_session_events(tmp_path)
            return compute_exploration_coverage(report, events)

        coverage = _run_in_thread(_scenario)["value"]
        summary = coverage["summary"]
        assert summary["total_screens"] >= 2
        assert summary["explored_screens"] >= 1

        dashboard = next(s for s in coverage["screens"] if s["url"].endswith("dashboard.html"))
        assert dashboard["explored"] is True
        assert dashboard["visits"] >= 1
        assert dashboard["actions"] >= 1, "モーダルを開くクリックが操作として記録されていない"
        # クロールが検出したモーダル状態に、記録セッションの足跡が載っている
        assert any(
            s["touched"] >= 1 for s in dashboard["states"]
        ), f"状態の足跡が突合されていない: {dashboard['states']}"

        contact = next(s for s in coverage["screens"] if s["url"].endswith("contact.html"))
        assert contact["explored"] is False, "触っていない画面が未探索と判定されていない"
