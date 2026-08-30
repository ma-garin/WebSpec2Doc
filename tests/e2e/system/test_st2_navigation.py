"""システムテスト L3: テナント選択〜システム選択〜画面遷移
（docs/system_test_cases.csv ST-006〜ST-009, ST-031）。

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
    switch_view_by_script,
)


class TestStNavigation:
    """テナント選択・システム選択カード・全ビュー描画。"""

    def test_st006_tenant_gate_leads_to_workspace_home(
        self, page: Page, system_server: str
    ) -> None:
        """ST-006: ログイン後、テナント選択を通過してホーム（サイト一覧）へ到達する。

        所属が 1 件のみの構成ではテナント選択が省略されることを許容する
        （その場合も "/" へ直行することを検証する）。製品統合により、
        旧システム選択ハブ（/systems・4 カード）は "/" へ 302 になった。
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
        expect(page).to_have_url(f"{system_server}/")

    def test_st007_home_shows_unified_workspace_rail(self, page: Page, system_server: str) -> None:
        """ST-007: ホームは統合ワークスペースのシェル（7 ワークスペースのレール）。

        旧「ドキュメント作成」カード（.syscard-doc）はハブごと廃止されたため、
        カードの押下ではなくホームの骨格を検証する。旧シェルの各画面へは
        画面別 URL（/dashboard 等）から到達する。
        """
        login(page, system_server, MEMBER)
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
        """ST-009: ホームのユーザーメニューから個人設定（アカウント）へ移動できる。"""
        login(page, system_server, MEMBER)
        account_link = page.locator('a.uitem[href="/account"]')
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

        # System 02 テスト活動支援（nav.html:26-65 の data-system="testlab"）。
        # 入口は /test-activity（system-scope.js:15-19 TESTLAB_PATHS）。
        page.goto(f"{system_server}/test-activity")
        expect(page.locator("#view-test-activity")).to_be_visible()
        # 工程ゲート（web/services/process_gate.py）が未到達工程の nav を
        # disabled にし、JS 側（ta-process-gate.js）も switchView を止める。
        # 本テストの目的は「全ビューが JS エラーなく描画されること」なので、
        # 先に全工程を完了 API で解放してから巡回する
        # （ゲートが効くこと自体の検証は test_st2_process_gate 側の責務）。
        gate_domain = page.evaluate(
            "async () => {"
            " const r = await fetch('/api/history');"
            " const d = await r.json();"
            " return (d.items && d.items[0] && d.items[0].domain) || '';"
            "}"
        )
        if gate_domain:
            for phase in (
                "test-plan",
                "test-analysis",
                "test-strategy",
                "test-design",
                "test-implementation",
                "test-execution",
                "manual-execution",
                "defect-analysis",
                "code-fix",
                "test-completion",
            ):
                page.evaluate(
                    "async ([domain, phase]) => {"
                    " await fetch('/api/ta/process/complete', {"
                    "  method: 'POST',"
                    "  headers: {'Content-Type': 'application/json'},"
                    "  body: JSON.stringify({domain, phase})"
                    " });"
                    "}",
                    [gate_domain, phase],
                )
            page.reload()
            expect(page.locator("#view-test-activity")).to_be_visible()

        for view in (
            "test-activity",
            "test-plan",
            "test-analysis",
            "test-strategy",
            "test-design",
            "test-implementation",
            "test-execution",
            "manual-execution",
            "defect-analysis",
            "code-fix",
            "test-completion",
            "integrations",
        ):
            nav = page.locator(f'[data-view="{view}"]').first
            if nav.count() and nav.is_enabled():
                switch_view(page, view)
            else:
                switch_view_by_script(page, view)

        # System 03 AutoRun（nav.html:10-18 の data-system="autorun"）。
        # 入口は /auto-run（system-scope.js:13 AUTORUN_PATHS）。
        page.goto(f"{system_server}/auto-run")
        expect(page.locator("#view-auto-run")).to_be_visible()
        switch_view(page, "auto-run")
        page.locator("#nav-run-history-btn").click()
        expect(page.locator("#view-run-history")).to_be_visible()

        assert not errors, f"ビュー描画中に JS エラー: {errors}"
