"""システムテスト L3: テナント選択〜システム選択〜画面遷移
（docs/process/quality/system_test_cases.csv ST-006〜ST-009, ST-031）。

実行方法:
    make e2e-system
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect
from tests.e2e.system.helpers import (
    ADMIN,
    LANDING_URL_RE,
    MEMBER,
    login,
    open_docs_system,
    switch_view,
)


class TestStNavigation:
    """テナント選択・システム選択カード・全ビュー描画。"""

    def test_st006_tenant_gate_leads_to_system_select(
        self, page: Page, system_server: str
    ) -> None:
        """ST-006: ログイン後、テナント選択を通過してシステム選択（/systems）へ到達する。

        所属が 1 件のみの構成ではテナント選択が省略されることを許容する
        （その場合も /systems へ直行することを検証する）。
        """
        page.goto(f"{system_server}/auth/login")
        page.locator("#email").fill(MEMBER.email)
        page.locator("#password").fill(MEMBER.password)
        page.locator("button.auth-submit").click()
        page.wait_for_url(LANDING_URL_RE)
        if "/auth/tenant" in page.url:
            tenant_form = page.locator('form[action="/auth/tenant"] button[type="submit"]')
            expect(tenant_form.first).to_be_visible()
            tenant_form.first.click()
        expect(page).to_have_url(f"{system_server}/systems")

    def test_st007_workspace_shell_shows_rail(self, page: Page, system_server: str) -> None:
        """ST-007: 統合ワークスペースのシェルは 7 ワークスペースのレールを出す。

        "/" はアプリシェル（index.html）に戻ったため、workspace.html は
        /team 等のワークスペース URL から開く。
        """
        login(page, system_server, MEMBER)
        page.goto(f"{system_server}/team")
        expect(page.locator('.rail [data-view="home"]')).to_be_visible()
        assert page.locator(".rail [data-view]").count() == 7
        assert page.locator(".rail [data-view].on").count() == 1

    def test_st008_autorun_intake_is_reachable(self, page: Page, system_server: str) -> None:
        """ST-008: AutoRun の受付画面へ到達できる。

        旧システム選択ハブの AutoRun カード（templates/system-select.html）は
        製品統合で廃止された。AutoRun は旧シェルに残っており、画面別 URL
        （/auto-run）から開く（Phase D で新シェルへ移す予定）。

        到達判定は `#autorun-leadbar` を使わない。あれは実行状態が無いと
        display:none にされる状態駆動の要素（static/js/autorun-leadbar.js:30-34）で、
        画面遷移の有無を表さないため。AutoRun 受付画面の恒常要素
        （templates/partials/view-auto-run.html:2 `#view-auto-run`、
        同 :47 `#autorun-url`、同 :108 `#autorun-start-btn`）で判定する。
        """
        login(page, system_server, MEMBER)
        page.goto(f"{system_server}/auto-run")
        expect(page).to_have_url(re.compile(r"/auto-run"))
        expect(page.locator("#view-auto-run")).to_be_visible()
        expect(page.locator("#autorun-url")).to_be_visible()
        expect(page.locator("#autorun-start-btn")).to_be_visible()

    def test_st009_account_link_from_workspace_user_menu(
        self, page: Page, system_server: str
    ) -> None:
        """ST-009: ホームのユーザーメニューから個人設定（アカウント）へ移動できる。

        ログイン着地点の /systems は partials/topbar.html の共通トップバーを使う。
        個人設定はそこでは `<a href="/account">` ではなく、ユーザーメニュー内の
        ボタン `#usermenu-account-btn`（templates/partials/topbar.html:55）で、
        クリックすると static/js/user-menu.js:55 が switchView('account') を呼ぶ。
        """
        login(page, system_server, MEMBER)
        account_link = page.locator("#usermenu-account-btn")
        assert account_link.count() == 1, "ユーザーメニューに個人設定の導線が無い"
        page.goto(f"{system_server}/account")
        expect(page.locator("#view-account")).to_be_visible()

    def test_st031_all_nav_views_render_without_js_errors(
        self, page: Page, system_server: str
    ) -> None:
        """ST-031: nav の全ビューが JS エラーなく描画される（admin で実行）。

        settings は owner/admin のみのため admin で全ビューを回す。
        nav に無いビュー（feedback/usage 等）は各機能のテストで個別に開く。

        4 システム構成では nav がシステムごとに独立しており、
        static/js/system-scope.js:54-62 が現在の系に属さない `data-system` 要素を
        display:none にする。系の判定はパス優先（同 :13-33 の AUTORUN_PATHS /
        TESTLAB_PATHS / DOCS_PATHS）なので、系ごとに入口 URL を開いてから
        その系のナビだけを巡回する。1 画面から全ビューへ飛べる前提は成立しない。
        """
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        # System 01 ドキュメント作成 + 共通（templates/partials/nav.html の
        # data-system="docs" / "common"）。入口は "/"（system-scope.js:20-23 DOCS_PATHS）。
        open_docs_system(page, system_server, ADMIN)
        for view in (
            "dashboard",
            "qa-quality",
            "viewpoints",
            "references",
            "settings",
            "user-guide",
        ):
            switch_view(page, view)
        # 実行履歴は data-view を持たない専用ボタン（nav.html:63 の docs 側）。
        page.locator("#nav-docs-run-history-btn").click()
        expect(page.locator("#view-run-history")).to_be_visible()

        # System 02 テスト自動化の旧 12 画面（test-activity 等）は統合ワークスペース
        # （templates/workspace.html）に統合済みで、nav.html にも
        # data-system="testlab" は残っていない（system-scope.js も TESTLAB_PATHS を
        # 持たない = 「ここでは扱わない」とコメントあり）。旧 URL は
        # web/routes/pages.py:31-49 の _TESTLAB_VIEWS に載っている名前だけ、
        # 同 :190-193 で /test-automation へ 302 される。/test-automation 自身は
        # 同 :137-139 で workspace.html を mode="test-only" として返す
        # （テスト前提が旧アーキテクチャのままだったため、リダイレクト先の
        # 検証に置き換えた）。
        page.goto(f"{system_server}/test-activity")
        expect(page).to_have_url(re.compile(r"/test-automation$"))
        expect(page.locator('body[data-ws="home"]')).to_be_visible()

        # System 03 AutoRun（nav.html:10-18 の data-system="autorun"）。
        # 入口は /auto-run（system-scope.js:13 AUTORUN_PATHS）。
        page.goto(f"{system_server}/auto-run")
        expect(page.locator("#view-auto-run")).to_be_visible()
        switch_view(page, "auto-run")
        page.locator("#nav-run-history-btn").click()
        expect(page.locator("#view-run-history")).to_be_visible()

        assert not errors, f"ビュー描画中に JS エラー: {errors}"
