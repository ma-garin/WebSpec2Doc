"""システムテスト L3: テナント選択〜システム選択〜画面遷移
（docs/system_test_cases.csv ST-006〜ST-009, ST-031）。

実行方法:
    make e2e-system
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect
from tests.e2e.system.helpers import ADMIN, MEMBER, login, open_docs_system, switch_view


class TestStNavigation:
    """テナント選択・システム選択カード・全ビュー描画。"""

    def test_st006_tenant_gate_leads_to_system_select(
        self, page: Page, system_server: str
    ) -> None:
        """ST-006: ログイン後、テナント選択を通過してシステム選択へ到達する。

        所属が 1 件のみの構成ではテナント選択が省略されることを許容する
        （その場合も /systems へ直行することを検証する）。
        """
        page.goto(f"{system_server}/auth/login")
        page.locator("#email").fill(MEMBER.email)
        page.locator("#password").fill(MEMBER.password)
        page.locator("button.auth-submit").click()
        page.wait_for_url(re.compile(r"/auth/tenant|/systems"))
        if "/auth/tenant" in page.url:
            tenant_form = page.locator('form[action="/auth/tenant"] button[type="submit"]')
            expect(tenant_form.first).to_be_visible()
            tenant_form.first.click()
        expect(page).to_have_url(re.compile(r"/systems"))

    def test_st007_syscard_opens_docs_system(self, page: Page, system_server: str) -> None:
        """ST-007: 「ドキュメント作成」カードからドキュメント作成システムへ遷移する。"""
        login(page, system_server, MEMBER)
        page.locator(".syscard-doc .syscard-open").click()
        expect(page.locator('[data-view="dashboard"]').first).to_be_visible()

    def test_st008_syscard_opens_autorun(self, page: Page, system_server: str) -> None:
        """ST-008: 「AutoRun」カードから AutoRun システムへ遷移する。"""
        login(page, system_server, MEMBER)
        page.locator(".syscard-run .syscard-open").click()
        expect(page.locator("#autorun-leadbar")).to_be_visible()

    def test_st009_account_link_from_system_select(self, page: Page, system_server: str) -> None:
        """ST-009: システム選択画面から個人設定（アカウント）へ移動できる。"""
        login(page, system_server, MEMBER)
        page.locator(".sysselect-account").click()
        expect(page.locator("#view-account")).to_be_visible()

    def test_st031_all_nav_views_render_without_js_errors(
        self, page: Page, system_server: str
    ) -> None:
        """ST-031: nav の全ビューが JS エラーなく描画される（admin で実行）。

        settings は owner/admin のみのため admin で全ビューを回す。
        nav に無いビュー（feedback/usage 等）は各機能のテストで個別に開く。
        """
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        open_docs_system(page, system_server, ADMIN)
        for view in (
            "dashboard",
            "viewpoints",
            "qa-quality",
            "references",
            "settings",
            "user-guide",
            "auto-run",
        ):
            switch_view(page, view)
        page.locator(
            "#nav-docs-run-history-btn:visible, #nav-run-history-btn:visible"
        ).first.click()
        expect(page.locator("#view-run-history")).to_be_visible()
        assert not errors, f"ビュー描画中に JS エラー: {errors}"
