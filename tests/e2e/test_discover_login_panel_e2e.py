"""ウィザードの「認証が必要なページ」バナー直下にログインフォームが実際に
可視で描画されることを検証する実ブラウザ E2E（B-auth-ux #1 再発防止）。

背景（ユーザー報告 / P0）:
    [条件設定]（サイト追加・再クロールのステップ）で
    「🔒 認証が必要なページ（N件）— 各画面の認証情報を入力してください」という
    バナーは表示されるが、その直下に本来あるべきユーザー名/パスワード入力欄と
    ログインボタンが表示されない、という不具合が過去繰り返し再発していた。
    これは DOM 構造やスタイルシートを目視・grep するだけでは検出できず、
    実ブラウザで DOM の可視性（visible）を機械的にアサートするテストが
    存在しなかったことが再発の一因だった。

このテストは同梱デモサイト（demo/site）の login.html を index.html からの
BFS 発見対象として使う。login.html を discover の「起点 URL」に直接使うと
ログインウォール判定でスキップされ空振りする（docs/specs/CONVENTIONS.md §4-5）が、
ここでは index.html を起点にして login.html を「発見された子ページ」として
検出させるため、その罠には該当しない。

実行方法:
    make verify-ui
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

# デモサイトへのクロールを許可する（SSRF 保護の既定拒否を解除）。
# flask_server セッション fixture（conftest.py）がこの後の「収集完了→フィクスチャ起動」の
# 順で Flask サブプロセスへ環境を引き継ぐため、モジュールレベル（collection 時）で設定する。
os.environ.setdefault("WEBSPEC2DOC_ALLOW_LOCAL", "1")

try:
    from playwright.sync_api import Page, expect
except ImportError:  # pragma: no cover - conftest 側で skip される
    Page = object  # type: ignore[assignment,misc]
    expect = None  # type: ignore[assignment]

ROOT = Path(__file__).parent.parent.parent
BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")
# 既存 E2E が 8765/8766/8894/8896/8898-8904/8910/8911 を使用済みのため 8912 を使う。
DEMO_PORT = int(os.environ.get("WEBSPEC2DOC_E2E_LOGIN_PANEL_DEMO_PORT", "8912"))
DEMO_URL = f"http://127.0.0.1:{DEMO_PORT}"
_DISCOVER_TIMEOUT_MS = 60_000


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


class TestDiscoverLoginPanelVisibility:
    def test_login_required_pages_show_username_password_form(
        self, demo_site: str, page: Page
    ) -> None:
        """認証必須ページのバナー直下に、ユーザー名/パスワード入力とログインボタンが
        実際に可視で存在することをアサートする（再発防止の核心）。"""
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        # 既定表示はダッシュボード。ウィザード（画面分析）ビューへ遷移する。
        page.locator("#nav-new-analysis-btn").click()
        page.wait_for_selector("#url-input", state="visible")

        page.fill("#url-input", f"{demo_site}/index.html")
        page.click("#discover-btn")

        # 解析完了（解析結果サマリー表示）を待つ
        page.wait_for_selector("#p1-summary", state="visible", timeout=_DISCOVER_TIMEOUT_MS)

        # ログイン必須画面が1件以上検出されていることを前提として進める
        login_num_text = page.locator("#p1-login-num").inner_text()
        assert int(login_num_text) >= 1, (
            f"デモサイトで認証必須ページが検出されなかった（login_num={login_num_text}）。"
            "login.html のログインウォール判定が壊れている可能性がある。"
        )

        # 条件設定ステップへ進む（実際のユーザー操作と同じ経路）
        page.click("#p1-next-btn")
        page.wait_for_selector("#wizard-p2", state="visible")

        # バナー（件数表示）が見えること
        banner = page.locator(".disc-login-group-separator").first
        expect(banner).to_be_visible()
        expect(banner).to_contain_text("認証が必要なページ")

        # バナー直下のログインフォーム本体（過去に消えていた部分）が実際に可視であること
        panel = page.locator(".disc-item-login-panel").first
        expect(panel).to_be_visible()

        username_input = panel.locator(".disc-item-login-user")
        password_input = panel.locator(".disc-item-login-pass")
        login_btn = panel.locator(".disc-item-login-btn")
        expect(username_input).to_be_visible()
        expect(password_input).to_be_visible()
        expect(login_btn).to_be_visible()
        expect(login_btn).to_have_text("ログイン")

        # 入力欄が実際に操作可能であること（disabled/readonly で偽陽性にならないよう確認）
        username_input.fill("qa-user@example.com")
        password_input.fill("dummy-password")
        assert username_input.input_value() == "qa-user@example.com"
        assert password_input.input_value() == "dummy-password"
