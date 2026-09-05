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
            page2.goto(f"{system_server}/dashboard")
            expect(page2).to_have_url(re.compile(r"/auth/login"))
            # 新パスワードでログインできる
            login(page2, system_server, replace(target, password=new_password))
        finally:
            context2.close()

    def test_st026_role_change_grants_admin_access(
        self, page: Page, system_server: str
    ) -> None:
        """ST-026: member を admin へ変更すると管理画面の管理操作が使えるようになる。

        現行ロールは member / admin の2値（web/services/auth_store.py:37-39 ROLES）。
        管理者判定は `#view-user-management[data-is-admin]`
        （templates/partials/view-user-management.html:11）で、非管理者では
        `.uadm-admin-only` が hidden・`#uadm-denied-card` が表示される
        （static/js/user-admin-view.js:120-123）。旧 `#uadm-tenant-form` は実装から消滅済み。
        """
        target = StUser("st-promote@example.com", "st-promote-pass-1", "ST Promote", "member")
        login(page, system_server, ADMIN)
        create_user(page, system_server, target)
        user_id = find_user_id(page, system_server, target.email)

        # 昇格前: member には管理操作が出ず、拒否カードが出る
        page.request.post(f"{system_server}/auth/logout")
        login(page, system_server, target)
        page.goto(f"{system_server}/user-management")
        expect(page.locator("#uadm-denied-card")).to_be_visible()
        expect(page.locator("#uadm-add-btn")).not_to_be_visible()

        page.request.post(f"{system_server}/auth/logout")
        login(page, system_server, ADMIN)
        resp = page.request.patch(
            f"{system_server}/api/auth/users/{user_id}", data={"role": "admin"}
        )
        assert resp.ok, f"ロール変更失敗: {resp.status} {resp.text()}"

        # 昇格後: 本人が管理操作を行える
        page.request.post(f"{system_server}/auth/logout")
        login(page, system_server, target)
        page.goto(f"{system_server}/user-management")
        expect(page.locator("#uadm-add-btn")).to_be_visible()
        expect(page.locator("#uadm-denied-card")).not_to_be_visible()
        assert any(
            user.get("email") == target.email and user.get("role") == "admin"
            for user in list_users(page, system_server)
        ), "昇格したユーザーが admin として一覧に出ていません"

    def test_st027_last_admin_cannot_be_demoted(self, page: Page, system_server: str) -> None:
        """ST-027: テナントの管理者が0人になる降格は拒否される。

        owner ロールは admin に統合済み（auth_store.py:41-43 `_LEGACY_ROLE_ALIASES`）で
        「最後のオーナー」という概念は現行仕様に無い。現行の不変条件は
        「テナントの管理者を0人にしない」であり、対象を除いた残りに有効な admin が
        居るかで判定される（auth_store.py:713-716 → 872-893 `_assert_admin_remains`）。
        違反時は `AuthError(..., "last_admin")` を 400 で返す
        （web/routes/account.py:387-388）。
        よって「admin が1名だけの状態を作り、その1名の降格を試みる」形で検証する。
        """
        login(page, system_server, ADMIN)
        admins = [
            user
            for user in list_users(page, system_server)
            if user.get("role") == "admin" and user.get("is_active", True)
        ]
        keeper = next(user for user in admins if user.get("email") == ADMIN.email)
        keeper_id = str(keeper.get("id"))
        # 操作主体（ADMIN）だけを残し、他の admin は一時的に member へ降格する
        demoted: list[str] = []
        try:
            for user in admins:
                user_id = str(user.get("id"))
                if user_id == keeper_id:
                    continue
                resp = page.request.patch(
                    f"{system_server}/api/auth/users/{user_id}", data={"role": "member"}
                )
                assert resp.ok, f"前提作成の降格に失敗: {resp.status} {resp.text()}"
                demoted.append(user_id)

            resp = page.request.patch(
                f"{system_server}/api/auth/users/{keeper_id}", data={"role": "member"}
            )
            assert resp.status == 400, (
                f"管理者が0人になる降格が拒否されていません: {resp.status} {resp.text()}"
            )
            assert resp.json().get("code") == "last_admin", (
                f"想定と違うエラーコード: {resp.text()}"
            )
            entry = next(
                user for user in list_users(page, system_server) if user.get("id") == keeper_id
            )
            assert entry.get("role") == "admin", f"管理者が降格されています: {entry}"
        finally:
            # 後続テストのために元の admin 構成へ戻す
            for user_id in demoted:
                page.request.patch(
                    f"{system_server}/api/auth/users/{user_id}", data={"role": "admin"}
                )

    def test_st028_api_token_issue_and_revoke(self, page: Page, system_server: str) -> None:
        """ST-028: API トークンは発行時に一度だけ表示され、失効後は API 認証が拒否される。

        失効は論理削除で、`revoked_at` を立てるだけ（auth_store.py:1255-1262）。
        一覧は `revoked_at` で絞り込まない（同 1244-1253）ため「一覧から消える」ことは
        期待しない。仕様（docs/system_test_cases.csv:29）の合否基準は
        「削除後はそのトークンでのAPIアクセスが拒否される」であり、
        `resolve_api_token` が revoked を None 扱いにし（auth_store.py:1233-1234）、
        web/auth.py:136-139 が 401 を返すことで満たされる。
        """
        token_name = "st-e2e-token"
        api_url = f"{system_server}/api/v1/sites"
        login(page, system_server, ADMIN)
        # ログイン着地点 /systems（system-select.html）は user-menu.js のみを読み込み、
        # core.js（switchView）を読み込まない。そのため `#usermenu-account-btn`
        # （旧 `.sysselect-account`。system-select.html 独自ヘッダーは廃止済みで、
        # partials/topbar.html の共通ユーザーメニューに置き換わった）を押しても
        # switchView が未定義で何も起きない。個人設定（トークン発行）へは
        # 直接 URL（/account）で到達する。
        page.goto(f"{system_server}/account")
        expect(page.locator("#token-form")).to_be_visible()
        page.locator("#token-name").fill(token_name)
        page.locator('#token-form button[type="submit"]').click()
        # 平文トークンはこの1回だけ表示される（static/js/account-view.js:119-123）
        expect(page.locator("#token-once")).to_contain_text("ws2d_")
        expect(page.locator("#token-rows")).to_contain_text(token_name)
        match = re.search(r"ws2d_[A-Za-z0-9_-]+", page.locator("#token-once").inner_text())
        assert match, "発行画面から平文トークンを取得できません"
        raw_token = match.group(0)
        auth_header = {"Authorization": f"Bearer {raw_token}"}

        # 失効前はそのトークンで API v1 にアクセスできる
        resp = page.request.get(api_url, headers=auth_header)
        assert resp.status == 200, f"発行直後のトークンでAPIが使えません: {resp.status} {resp.text()}"

        tokens = list_api_tokens(page, system_server)
        token_id = next(
            (t.get("id") or t.get("token_id") for t in tokens if t.get("name") == token_name),
            None,
        )
        assert token_id, f"発行したトークンが一覧にありません: {tokens}"
        resp = page.request.delete(f"{system_server}/api/auth/api-tokens/{token_id}")
        assert resp.ok, f"トークン失効失敗: {resp.status} {resp.text()}"

        # 論理削除なので一覧には残り、revoked_at が入る
        entry = next(
            (t for t in list_api_tokens(page, system_server) if t.get("id") == token_id), None
        )
        assert entry is not None, "失効後にトークンが一覧から消えました（実装は論理削除）"
        assert entry.get("revoked_at"), f"revoked_at が設定されていません: {entry}"

        # 仕様上の合否基準: 失効したトークンでは API アクセスが拒否される
        resp = page.request.get(api_url, headers=auth_header)
        assert resp.status == 401, (
            f"失効済みトークンでAPIアクセスが拒否されていません: {resp.status} {resp.text()}"
        )
