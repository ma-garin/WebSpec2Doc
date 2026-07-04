"""気づき→バグ票変換（SPEC-2-3）の実ブラウザ E2E。

デモサイトの contact.html（フォーム — CONVENTIONS 罠#5）を標的に、
(1) 記録用ページに気づきウィジェットが表示されクリックで finding イベントが
JSONL に記録されること、(2) 操作 → マーク → export-findings で、生成された
票の再現手順にマーク前の操作が載ることを検証する。

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

# 8898=SPEC-3-1・8899=SPEC-2-1 予約済み。SPEC-2-3 は 8901 を使用する。
DEMO_PORT = int(os.environ.get("WEBSPEC2DOC_E2E_FINDING_PORT", "8901"))
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


class TestFindingWidgetE2E:
    def test_finding_widget_visible_and_marks(self, demo_site: str, tmp_path: Path) -> None:
        """記録ページに気づきウィジェットが表示され、クリックで finding イベントが記録される。"""

        def _scenario() -> dict[str, Any]:
            from capture.session_recorder import SessionRecorder, normalize_footprint_path
            from crawler.page_crawler import _browser_page

            with _browser_page(None) as page:
                page.goto(f"{demo_site}/contact.html")
                session_path = tmp_path / "sessions" / "session_001.jsonl"
                recorder = SessionRecorder(page=page, session_path=session_path)
                recorder.start()

                # ウィジェットが DOM に注入されていることを確認する
                page.wait_for_selector("#__ws2d_finding_btn", timeout=5000)
                widget_visible = page.is_visible("#__ws2d_finding_btn")

                # prompt() をスタブして気づきメモを自動入力する
                page.evaluate("window.prompt = () => 'お問い合わせボタンの色が薄い';")
                page.click("#__ws2d_finding_btn")
                page.wait_for_timeout(300)
                recorder.poll_once()
                recorder.flush()

            return {
                "widget_visible": widget_visible,
                "session_path": str(session_path),
                "path": normalize_footprint_path(f"{demo_site}/contact.html"),
            }

        result = _run_in_thread(_scenario)["value"]
        assert result["widget_visible"] is True

        lines = [
            json.loads(line)
            for line in Path(result["session_path"]).read_text(encoding="utf-8").splitlines()
        ]
        findings = [line for line in lines if line["kind"] == "finding"]
        assert len(findings) == 1
        assert findings[0]["note"] == "お問い合わせボタンの色が薄い"
        assert findings[0]["path"] == result["path"]
        # ウィジェット自体のクリックは操作イベントとして二重記録されない
        assert not any(
            line["kind"] == "action" and "__ws2d_finding_btn" in line.get("selector", "")
            for line in lines
        )

    def test_exported_ticket_has_repro_steps(self, demo_site: str, tmp_path: Path) -> None:
        """操作 → マーク → export-findings で、票の手順にマーク前の操作が載る。"""

        def _scenario() -> dict[str, Any]:
            from capture.coverage import load_session_events
            from capture.finding_reporter import build_finding_tickets, save_findings
            from capture.session_recorder import SessionRecorder
            from crawler.page_crawler import _browser_page

            with _browser_page(None) as page:
                page.goto(f"{demo_site}/contact.html")
                session_path = tmp_path / "sessions" / "session_001.jsonl"
                recorder = SessionRecorder(page=page, session_path=session_path)
                recorder.start()

                # マーク前の操作: 入力欄に値を入れる
                page.fill("input[name='name']", "テスト太郎")
                page.wait_for_timeout(200)
                recorder.poll_once()

                # 気づきマーク
                page.evaluate("window.prompt = () => '必須マークが表示されない';")
                page.wait_for_selector("#__ws2d_finding_btn", timeout=5000)
                page.click("#__ws2d_finding_btn")
                page.wait_for_timeout(300)
                recorder.poll_once()
                recorder.flush()

            events = load_session_events(tmp_path)
            tickets = build_finding_tickets(events)
            save_findings(tickets, tmp_path)
            return {"tickets": [t.repro_steps for t in tickets], "output_dir": str(tmp_path)}

        result = _run_in_thread(_scenario)["value"]
        assert len(result["tickets"]) == 1
        repro_steps = result["tickets"][0]
        assert any("を開く" in step for step in repro_steps), repro_steps
        assert any("name" in step for step in repro_steps), repro_steps

        output_dir = Path(result["output_dir"])
        assert (output_dir / "findings.json").exists()
        assert (output_dir / "findings.csv").exists()
