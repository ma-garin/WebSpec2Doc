"""システムテスト L3: 権限境界・管理機能
（docs/system_test_cases.csv ST-022〜ST-028）。

実行方法:
    make e2e-system
"""

from __future__ import annotations

import re
from dataclasses import replace

from playwright.sync_api import Browser, Page, expect
from tests.e2e.system.helpers import (
    ADMIN,
    MEMBER,
    OWNER,
    StUser,
    create_user,
    find_user_id,
    list_api_tokens,
    list_users,
    login,
    open_docs_system,
    switch_view,
)


class TestStAdminBoundary:
    """member の管理機能アクセス遮断（ST-022）。"""

    def test_st022_member_cannot_access_admin_features(
        self, page: Page, system_server: str
    ) -> None:
        """ST-022: member は user-management の管理フォームも管理 API も使えない。"""
        login(page, system_server, MEMBER)
        page.goto(f"{system_server}/user-management")
        # 拒否の形（リダイレクト or 管理フォーム非表示）は問わず、操作不能を確認する
        expect(page.locator("#uadm-tenant-form")).not_to_be_visible()
        resp = page.request.post(
            f"{system_server}/api/admin/tenancy/tenants",
            data={"name": "ST Forbidden", "slug": "st-forbidden"},
        )
        assert not resp.ok, f"member でテナント作成 API が成功: {resp.status}"


class TestStAdminOperations:
    """admin/owner の設定・ユーザー管理・API トークン（ST-023〜ST-028）。"""

    def test_st023_settings_tabs_switch(self, page: Page, system_server: str) -> None:
        """ST-023: 設定画面のタブが切り替わり、API 設定項目が表示される。

        値の変更保存は保存導線のセレクタ未実測のため対象外
        （タブ切替は過去の実不具合（C-broken-views #2）の再発防止を兼ねる）。
        """
        open_docs_system(page, system_server, ADMIN)
        switch_view(page, "settings")
        page.locator("#set-tab-crawl").click()
        expect(page.locator("#set-panel-crawl")).to_be_visible()
        page.locator("#set-tab-api").click()
        expect(page.locator("#set-panel-api")).to_be_visible()
        expect(page.locator("#api-key")).to_be_attached()

    def test_st024_admin_creates_user_who_can_login(
        self, page: Page, system_server: str
    ) -> None:
        """ST-024: admin がユーザーを作成し、一覧に表示され、その本人がログインできる。"""
        target = StUser("st-created@example.com", "st-created-pass-1", "ST Created", "member")
        login(page, system_server, ADMIN)
        create_user(page, system_server, target)
        page.goto(f"{system_server}/user-management")
        expect(page.locator("#uadm-user-rows")).to_contain_text(target.email)

        page.request.post(f"{system_server}/auth/logout")
        login(page, system_server, target)

    def test_st025_password_reset_invalidates_sessions(
        self, page: Page, system_server: str, browser: Browser
    ) -> None:
        """ST-025: 管理者のパスワード再設定で対象の全セッションが失効し、
        新パスワードでのみログインできる。"""
        target = StUser("st-reset@example.com", "st-reset-pass-1", "ST Reset", "member")
        new_password = "st-reset-updated-2"
        login(page, system_server, ADMIN)
        create_user(page, system_server, target)
        user_id = find_user_id(page, system_server, target.email)

        # 対象ユーザーを別セッション（別コンテキスト）でログインさせておく
        context2 = browser.new_context()
        page2 = context2.new_page()
        try:
            login(page2, system_server, target)

            resp = page.request.post(
                f"{system_server}/api/admin/tenancy/users/{user_id}/password",
                data={"password": new_password},
            )
            assert resp.ok, f"パスワード再設定失敗: {resp.status} {resp.text()}"

            # 既存セッションは失効している
            page2.goto(f"{system_server}/systems")
            expect(page2).to_have_url(re.compile(r"/auth/login"))
            # 新パスワードでログインできる
            login(page2, system_server, replace(target, password=new_password))
        finally:
            context2.close()

    def test_st026_role_change_grants_admin_access(
        self, page: Page, system_server: str
    ) -> None:
        """ST-026: member を admin へ変更すると管理画面へアクセスできるようになる。"""
        target = StUser("st-promote@example.com", "st-promote-pass-1", "ST Promote", "member")
        login(page, system_server, ADMIN)
        create_user(page, system_server, target)
        user_id = find_user_id(page, system_server, target.email)
        resp = page.request.patch(
            f"{system_server}/api/auth/users/{user_id}", data={"role": "admin"}
        )
        assert resp.ok, f"ロール変更失敗: {resp.status} {resp.text()}"

        page.request.post(f"{system_server}/auth/logout")
        login(page, system_server, target)
        page.goto(f"{system_server}/user-management")
        expect(page.locator("#uadm-tenant-form")).to_be_visible()

    def test_st027_last_owner_cannot_be_demoted(self, page: Page, system_server: str) -> None:
        """ST-027: 最後の有効オーナーは自身を降格できない。"""
        login(page, system_server, OWNER)
        owner_id = find_user_id(page, system_server, OWNER.email)
        resp = page.request.patch(
            f"{system_server}/api/auth/users/{owner_id}", data={"role": "member"}
        )
        assert not resp.ok, "最後のオーナーの降格が成功してしまいました"
        entry = next(
            user for user in list_users(page, system_server) if user.get("email") == OWNER.email
        )
        assert entry.get("role") in (None, "owner"), f"オーナーが降格されています: {entry}"

    def test_st028_api_token_issue_and_revoke(self, page: Page, system_server: str) -> None:
        """ST-028: API トークンを発行すると一度だけ表示され、削除後は一覧から消える。"""
        token_name = "st-e2e-token"
        login(page, system_server, ADMIN)
        page.locator(".sysselect-account").click()
        expect(page.locator("#token-form")).to_be_visible()
        page.locator("#token-name").fill(token_name)
        page.locator('#token-form button[type="submit"]').click()
        expect(page.locator("#token-once")).to_contain_text(re.compile(r"\S"))
        expect(page.locator("#token-rows")).to_contain_text(token_name)

        tokens = list_api_tokens(page, system_server)
        token_id = next(
            (t.get("id") or t.get("token_id") for t in tokens if t.get("name") == token_name),
            None,
        )
        assert token_id, f"発行したトークンが一覧にありません: {tokens}"
        resp = page.request.delete(f"{system_server}/api/auth/api-tokens/{token_id}")
        assert resp.ok, f"トークン削除失敗: {resp.status} {resp.text()}"
        remaining = [t for t in list_api_tokens(page, system_server) if t.get("name") == token_name]
        assert not remaining, f"削除後もトークンが残っています: {remaining}"
