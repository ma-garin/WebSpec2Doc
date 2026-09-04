"""システムテスト（docs/system_test_cases.csv）共通ヘルパー。

セレクタ・APIパスはすべて templates/ と既存 E2E（test_auth_tenant_e2e.py 等）
から実測したものを使う。推測セレクタをここに追加しないこと。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from playwright.sync_api import Page, expect

TENANT_NAME = "ST System Tenant"


@dataclass(frozen=True)
class StUser:
    email: str
    password: str
    name: str
    role: str


OWNER = StUser("st-owner@example.com", "st-owner-pass-123", "ST Owner", "owner")
ADMIN = StUser("st-admin@example.com", "st-admin-pass-123", "ST Admin", "admin")
MEMBER = StUser("st-member@example.com", "st-member-pass-123", "ST Member", "member")
# ST-029 が自分のパスワードを変更するため、他テストと共有しない専用ユーザー
PW_CHANGE_MEMBER = StUser("st-member2@example.com", "st-member2-pass-123", "ST Member2", "member")


# ログイン着地点。テナント選択（/auth/tenant）を経てシステム選択（/systems）へ着地する。
LANDING_URL_RE = re.compile(r"/auth/tenant$|/systems$")


def login(page: Page, base_url: str, user: StUser) -> None:
    """ログイン→（テナント選択画面があれば通過）→ システム選択（/systems）到達まで。"""
    page.goto(f"{base_url}/auth/login")
    page.locator("#email").fill(user.email)
    page.locator("#password").fill(user.password)
    page.locator("button.auth-submit").click()
    page.wait_for_url(LANDING_URL_RE)
    if "/auth/tenant" in page.url:
        page.locator('form[action="/auth/tenant"] button[type="submit"]').first.click()
    expect(page).to_have_url(f"{base_url}/systems")


def open_docs_system(page: Page, base_url: str, user: StUser) -> None:
    """ログインして旧シェル（AutoRun・観点管理・設定を持つ index.html）を開く。

    ログイン着地点は /systems になったため、旧シェルの画面は
    /dashboard 等の画面別 URL から開く。
    """
    login(page, base_url, user)
    page.goto(f"{base_url}/dashboard")
    expect(page.locator('[data-view="dashboard"]').first).to_be_visible()


def switch_view(page: Page, view: str) -> None:
    """nav のビュー切替（[data-view=...]）で移動し、描画を確認する。"""
    page.locator(f'[data-view="{view}"]').first.click()
    expect(page.locator(f"#view-{view}")).to_be_visible()


def switch_view_by_script(page: Page, view: str) -> None:
    """nav に無いビュー（feedback / usage 等）へ core.js の switchView で移動する。

    導線の検証は対象外（各 ST の目的はビュー内の機能であるため）。
    """
    page.wait_for_function("() => typeof switchView === 'function'")
    page.evaluate(f"switchView('{view}')")
    expect(page.locator(f"#view-{view}")).to_be_visible()


def _extract_list(payload: object, keys: tuple[str, ...]) -> list[dict]:
    """API 応答の一覧部分を取り出す（{"users": [...]} / 素の配列の両対応）。"""
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return payload if isinstance(payload, list) else []


def list_users(page: Page, base_url: str) -> list[dict]:
    resp = page.request.get(f"{base_url}/api/auth/users")
    assert resp.ok, f"GET /api/auth/users 失敗: {resp.status} {resp.text()}"
    return _extract_list(resp.json(), ("users", "items", "data"))


def find_user_id(page: Page, base_url: str, email: str) -> str:
    for user in list_users(page, base_url):
        if user.get("email") == email:
            user_id = user.get("id") or user.get("user_id")
            assert user_id, f"ユーザー一覧の項目に id がありません: {user}"
            return str(user_id)
    raise AssertionError(f"ユーザーが見つかりません: {email}")


def create_user(page: Page, base_url: str, user: StUser) -> None:
    """テナント内ユーザー作成 API（owner/admin のみ）でユーザーを作る。"""
    resp = page.request.post(
        f"{base_url}/api/auth/users",
        data={
            "name": user.name,
            "email": user.email,
            "password": user.password,
            "role": user.role,
        },
    )
    assert resp.ok, f"ユーザー作成失敗 ({user.email}): {resp.status} {resp.text()}"


def list_api_tokens(page: Page, base_url: str) -> list[dict]:
    resp = page.request.get(f"{base_url}/api/auth/api-tokens")
    assert resp.ok, f"GET /api/auth/api-tokens 失敗: {resp.status} {resp.text()}"
    return _extract_list(resp.json(), ("tokens", "items", "data"))
