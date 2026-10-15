"""システムテスト L3: 認証（docs/process/quality/system_test_cases.csv ST-001〜ST-005, ST-032）。

実行方法:
    make e2e-system
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect
from tests.e2e.system.helpers import MEMBER, OWNER, login


class TestStAuth:
    """認証まわり: 未認証遮断・ログイン・ログアウト・セッション失効。"""

    def test_st001_unauthenticated_access_redirects_to_login(
        self, page: Page, system_server: str
    ) -> None:
        """ST-001: 未認証でトップへアクセスするとログインへ誘導される。"""
        page.goto(f"{system_server}/")
        expect(page).to_have_url(re.compile(r"/auth/login"))

    def test_st002_login_reaches_system_select(self, page: Page, system_server: str) -> None:
        """ST-002: ログイン成功でテナント選択を経てシステム選択に到達する。"""
        login(page, system_server, MEMBER)
        expect(page.locator(".sysselect-grid")).to_be_visible()

    def test_st003_login_failure_stays_on_login(self, page: Page, system_server: str) -> None:
        """ST-003: 誤ったパスワードではログイン画面に留まる。

        エラーメッセージの文言はテンプレート未実測のため、遷移しないことと
        フォームが再表示されることを目印にする。
        """
        page.goto(f"{system_server}/auth/login")
        page.locator("#email").fill(OWNER.email)
        page.locator("#password").fill("wrong-password-123")
        page.locator("button.auth-submit").click()
        expect(page).to_have_url(re.compile(r"/auth/login"))
        expect(page.locator("#password")).to_be_visible()

    def test_st004_signup_page_renders(self, page: Page, system_server: str) -> None:
        """ST-004: サインアップ画面が表示される（表示スモーク）。

        登録の完遂は招待要否など前提が未確定のため、このサイクルでは
        画面表示までを検証範囲とする。
        """
        page.goto(f"{system_server}/auth/signup")
        expect(page.locator("#email")).to_be_visible()

    def test_st005_logout_blocks_back_navigation(self, page: Page, system_server: str) -> None:
        """ST-005: ログアウト後は認証後ページへ戻れない。"""
        login(page, system_server, MEMBER)
        page.request.post(f"{system_server}/auth/logout")
        page.goto(f"{system_server}/dashboard")
        expect(page).to_have_url(re.compile(r"/auth/login"))

    def test_st032_session_invalidation_blocks_access(
        self, page: Page, system_server: str
    ) -> None:
        """ST-032: セッション失効後は画面・API とも操作できない。"""
        login(page, system_server, MEMBER)
        page.context.clear_cookies()
        page.goto(f"{system_server}/")
        expect(page).to_have_url(re.compile(r"/auth/login"))
        resp = page.request.get(f"{system_server}/api/auth/users")
        assert (not resp.ok) or "/auth/login" in resp.url, (
            f"失効セッションで API が成功: {resp.status} {resp.url}"
        )
