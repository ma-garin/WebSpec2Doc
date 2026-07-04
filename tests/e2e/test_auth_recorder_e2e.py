"""認証フローレコーダー（SPEC-3-2）の実ブラウザ E2E。

標的はデモサイト login.html（唯一この機能ではログインページが正しい標的。
CONVENTIONS §4-5 の「ログイン画面を避ける」はクロール E2E の話であり、
このレコーダーはログイン画面そのものを扱う機能のため意図的な例外とする）。

headless=True で起動し、フォーム送信はテストコードが代行する（人のログイン
操作の代わり）→ シグナルファイル作成 → auth.json 保存と verified を検証する
（AC-1, AC-2, AC-6）。

pytest-playwright のセッション fixture が保持する asyncio ループとの衝突を
避けるため、ブラウザ処理は専用スレッドで実行する
（tests/e2e/test_capture_realbrowser_e2e.py と同じパターン）。

ポートについて: 仕様書（docs/specs/spec-3-2_auth_recorder.md §6-2）は 8900 を
指定しているが、8900 は本タスクの実行環境で他ワークフローに予約済みのため
（CONVENTIONS §4-7 の一覧に含まれる）、衝突を避けて 8910 を用いる
（仕様外判断: ポート番号のみ変更。動作・検証内容は仕様通り）。
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

DEMO_PORT = int(os.environ.get("WEBSPEC2DOC_E2E_AUTH_RECORDER_PORT", "8910"))
DEMO_URL = f"http://127.0.0.1:{DEMO_PORT}"
_THREAD_TIMEOUT_SEC = 60


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


class TestAuthRecorderE2E:
    def test_signal_after_login_saves_and_verifies(self, demo_site: str, tmp_path: Path) -> None:
        """フォーム送信（テストコードが人の代わりに実施）→ シグナル → 保存・検証（AC-1,2,6）。"""

        def _scenario() -> dict[str, Any]:
            from playwright.sync_api import sync_playwright

            from crawler.auth_recorder import _run_recorder_loop

            login_url = f"{demo_site}/login.html"
            auth_path = tmp_path / "auth.json"
            signal_file = tmp_path / ".login_signal"
            status_file = tmp_path / ".login_status.json"

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    context = browser.new_context()
                    page = context.new_page()
                    page.goto(login_url)

                    # 人のログイン操作をテストコードが代行する
                    page.fill("#email", "user@example.com")
                    page.fill("#password", "password123")
                    page.click("button[type=submit]")
                    page.wait_for_load_state("networkidle")

                    # 「ログイン完了」ボタンに相当する操作
                    signal_file.touch()

                    status = _run_recorder_loop(
                        page=page,
                        context=context,
                        login_url=login_url,
                        auth_path=auth_path,
                        signal_file=signal_file,
                        status_file=status_file,
                        timeout=10.0,
                        poll_interval=0.1,
                        playwright=playwright,
                    )
                finally:
                    browser.close()

            return {
                "status": status,
                "auth_exists": auth_path.exists(),
                "auth_perm": oct(auth_path.stat().st_mode)[-3:] if auth_path.exists() else "",
                "status_file_exists": status_file.exists(),
            }

        result = _run_in_thread(_scenario)["value"]

        assert result["status"].phase == "saved"
        assert result["auth_exists"], "auth.json が保存されていない"
        assert result["auth_perm"] == "600", "auth.json のパーミッションが 600 でない"
        assert result["status_file_exists"], "status_file が出力されていない"
        # login.html は静的ページで cookie 有無に関わらずパスワード欄を常に描画するため、
        # verify_auth_state は「未確認(None)」ではなく確定的に False を返す
        # （到達できてページ内容から判定した結果であり、未確認とは異なる）。
        # AC-6 が求めるのは verify が実行され結果を明示することであり、ここではその経路を確認する。
        assert result["status"].verified is False

    def test_timeout_without_signal_leaves_no_auth_file(
        self, demo_site: str, tmp_path: Path
    ) -> None:
        """AC-4: シグナルが来なければタイムアウトし、auth.json は作成されない。"""

        def _scenario() -> dict[str, Any]:
            from playwright.sync_api import sync_playwright

            from crawler.auth_recorder import _run_recorder_loop

            login_url = f"{demo_site}/login.html"
            auth_path = tmp_path / "auth_timeout.json"
            signal_file = tmp_path / ".login_signal_never"

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    context = browser.new_context()
                    page = context.new_page()
                    page.goto(login_url)
                    status = _run_recorder_loop(
                        page=page,
                        context=context,
                        login_url=login_url,
                        auth_path=auth_path,
                        signal_file=signal_file,
                        status_file=None,
                        timeout=1.0,
                        poll_interval=0.1,
                    )
                finally:
                    browser.close()

            return {"status": status, "auth_exists": auth_path.exists()}

        result = _run_in_thread(_scenario)["value"]
        assert result["status"].phase == "timeout"
        assert not result["auth_exists"]
