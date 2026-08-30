"""アプリ利用者認証・テナント管理の E2E テスト（L3 システムテスト、新規）。

対象（quality/feature_contracts.yml の critical だが L3(E2E) で未検証だった機能）:
    - account_auth: 本システムへのログイン認証（web/routes/account.py）
    - tenant_membership: テナント選択と所属管理（web/routes/tenant_admin.py, account.py）
    - tenant_isolation: テナント分離（web/tenancy.py の scoped_output_dir の効果）
    - user_menu_feedback: トップバーのユーザーメニューとフィードバック送信
      （ログイン済みでないとメニュー自体が描画されないため、この専用サーバーで検証する）

注意:
    これは WebSpec2Doc 自体のユーザー認証のテストである。
    tests/e2e/test_auth_recorder_e2e.py（クロール対象サイトへの認証フローレコーダー）
    とは無関係の別機能。

設計上の注意（専用サーバーで隔離する理由）:
    共有 E2E サーバー（conftest.py の flask_server フィクスチャ）は「ユーザー0人・
    認証オフ」を前提に他の全 E2E が動いている。ここでユーザーを1人でも作ると
    web/auth.py の auto モードにより認証が有効になり、同じサーバーへ反映すると
    他の既存 E2E が軒並みログイン壁に落ちて壊れる。ポート・認証DB・観点DBを
    完全に分離した専用 Flask プロセスをこのファイル専用に起動することで、
    既存 E2E への影響をゼロにする。

設計上の注意（パスワードを必ず入力する理由）:
    ログインは「ログインID + パスワード」の1経路だけで、ユーザー選択画面は廃止した。
    WEBSPEC2DOC_AUTH_MOCK（既定で有効）が変えるのはパスワードの長さ要件だけなので、
    このテストは既定設定のまま、全アカウントにパスワードを設定して検証する。

実行方法:
    venv/bin/python -m pytest tests/e2e/test_auth_tenant_e2e.py -q
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from tests.e2e.wait_helpers import wait_http_success

ROOT = Path(__file__).parent.parent.parent

_ADMIN_EMAIL = "e2e-admin@example.com"
_ADMIN_PASSWORD = "e2e-admin-pass-123"
_TENANT_A_NAME = "E2E Tenant A"
_TENANT_B_NAME = "E2E Tenant B"
_TENANT_B_SLUG = "e2e-tenant-b"
_MEMBER_EMAIL = "e2e-member@example.com"
_MEMBER_PASSWORD = "e2e-member-pass-123"
# ユーザー管理ビューで作成し、そのままパスワードリセットの対象にするアカウント
_RESET_EMAIL = "e2e-reset@example.com"
_RESET_INITIAL_PASSWORD = "e2e-reset-initial-1"
_RESET_NEW_PASSWORD = "e2e-reset-updated-2"

TENANT_SELECT = "/auth/tenant"
# 製品統合でシステム選択ハブは廃止。ログイン後の着地点はホーム（サイト一覧）。
SYSTEM_SELECT = "/"


def _wait_for_health(url: str, timeout: float = 20.0) -> bool:
    """サーバーの健全性エンドポイントが応答するまで待つ。"""
    return wait_http_success(f"{url}/api/v1/healthz", timeout_sec=timeout, interval_sec=0.3)


@pytest.fixture(scope="module")
def auth_server() -> Generator[str, None, None]:
    """認証・テナント E2E 専用の Flask サーバー（他の E2E から完全に隔離）。"""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    run_id = uuid.uuid4().hex[:8]
    auth_db = ROOT / "instance" / f"auth.e2e-authtest-{run_id}.db"
    viewpoints_db = ROOT / "instance" / f"viewpoints.e2e-authtest-{run_id}.db"

    env = {
        **os.environ,
        "FLASK_TESTING": "1",
        # 初期管理者を自動作成させず、/auth/setup の実UIで作る（setup_initial を実際に検証する）
        "WEBSPEC2DOC_BOOTSTRAP_ADMIN": "0",
        "WEBSPEC2DOC_AUTH_DB": str(auth_db),
        "VIEWPOINTS_DB": str(viewpoints_db),
        "PYTHONPATH": str(ROOT),
        "WEBSPEC2DOC_PORT": str(port),
    }
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    if not _wait_for_health(base_url):
        proc.terminate()
        proc.wait(timeout=10)
        pytest.fail(
            f"認証E2E専用サーバーが {base_url} で起動しませんでした"
            "（未実行の状態をPASS扱いにしない）。"
        )

    yield base_url

    proc.terminate()
    proc.wait(timeout=10)
    for db in (auth_db, viewpoints_db):
        for suffix in ("", "-journal", "-wal", "-shm"):
            Path(str(db) + suffix).unlink(missing_ok=True)


def _login_as(page: Page, base_url: str, email: str, password: str) -> None:
    """ログイン→テナント選択を経てホーム（"/"）に到達する（ID＋パスワード認証）。"""
    page.goto(f"{base_url}/auth/login")
    page.locator("#email").fill(email)
    page.locator("#password").fill(password)
    page.locator("button.auth-submit").click()

    expect(page).to_have_url(re.compile(re.escape(f"{base_url}{TENANT_SELECT}")))
    # 所属テナントの先頭を選ぶ（このテスト群では常に1件以上の所属がある状態で呼ぶ）
    page.locator('form[action="/auth/tenant"] button[type="submit"]').first.click()
    expect(page).to_have_url(f"{base_url}{SYSTEM_SELECT}")


class TestAccountAuth:
    """account_auth: 本システムのログイン認証（L3/E2E 初検証）。"""

    def test_login_lifecycle_guards_protected_pages(self, page: Page, auth_server: str) -> None:
        """未ログイン→保護ページはログイン画面へ / ログイン後は正規の遷移 / ログアウトで再ガード。"""
        # ユーザー0人の間は auto モード（web/auth.py）で認証オフ。
        # /auth/login にアクセスすると初期セットアップへ誘導される。
        page.goto(f"{auth_server}/auth/login")
        expect(page).to_have_url(f"{auth_server}/auth/setup")

        # 初期セットアップで最初のテナントと管理者を作る。パスワードは必須。
        page.locator("#tenant_name").fill(_TENANT_A_NAME)
        page.locator("#name").fill("E2E Admin")
        page.locator("#email").fill(_ADMIN_EMAIL)
        page.locator("#password").fill(_ADMIN_PASSWORD)
        page.locator("#password_confirm").fill(_ADMIN_PASSWORD)
        page.locator("button.auth-submit").click()
        # setup_submit はセッションを即座に発行し、テナントも決定済みでホームへ進む
        expect(page).to_have_url(f"{auth_server}{SYSTEM_SELECT}")

        # ログアウト（ログアウトフォームは複数画面に重複して存在するため、
        # 同一の実ルートへ直接 POST して検証を簡潔にする。ブラウザの Cookie は
        # page.request と共有されるため、以降のページ遷移にも反映される）。
        page.request.post(f"{auth_server}/auth/logout")

        # 匿名アクセス: ユーザーが存在するため認証が有効になり、保護ページは
        # ログイン画面へリダイレクトされる（ログアウトで再びガードされることの確認）。
        page.goto(f"{auth_server}{SYSTEM_SELECT}")
        expect(page).to_have_url(re.compile(r"/auth/login"))

        # 再ログイン→ 本来の遷移（テナント選択→システム選択）に進む
        _login_as(page, auth_server, _ADMIN_EMAIL, _ADMIN_PASSWORD)
        expect(page).to_have_url(f"{auth_server}{SYSTEM_SELECT}")


class TestTenantMembership:
    """tenant_membership: テナント選択と所属管理（管理者/一般の出し分け）。"""

    def test_user_management_lists_members_and_restricts_by_role(
        self, page: Page, auth_server: str
    ) -> None:
        """管理画面はユーザー管理ビューに統合済み。旧URLは転送され、一般メンバーは弾かれる。"""
        _login_as(page, auth_server, _ADMIN_EMAIL, _ADMIN_PASSWORD)

        # 旧 /admin/console はブックマークを壊さずユーザー管理ビューへ転送する
        page.goto(f"{auth_server}/admin/console")
        expect(page).to_have_url(f"{auth_server}/user-management")
        expect(page.locator("#uadm-add-btn")).to_be_visible()

        # テナントB・一般メンバーを作る。画面と同一の実APIを、認証済みの
        # ブラウザセッション（page.request は Cookie を共有する）から直接叩く。
        # user-admin-view.js のフォーム送信の実装詳細に依存せず、ゲートの効果
        # （表示・遷移）そのものの検証に集中するための選択。
        tenant_resp = page.request.post(
            f"{auth_server}/api/admin/tenancy/tenants",
            data={"name": _TENANT_B_NAME, "slug": _TENANT_B_SLUG},
        )
        assert tenant_resp.ok, tenant_resp.text()
        tenant_b_id = tenant_resp.json()["tenant"]["id"]

        user_resp = page.request.post(
            f"{auth_server}/api/admin/tenancy/users",
            data={
                "name": "E2E Member",
                "email": _MEMBER_EMAIL,
                "role": "member",
                "tenant_id": tenant_b_id,
                "password": _MEMBER_PASSWORD,
            },
        )
        assert user_resp.ok, user_resp.text()

        # 作成したメンバーはユーザー管理、テナントはテナント管理に出る（画面を分けている）
        page.goto(f"{auth_server}/user-management")
        expect(page.locator("#uadm-user-rows")).to_contain_text(_MEMBER_EMAIL)
        page.goto(f"{auth_server}/tenant-management")
        expect(page.locator("#tadm-rows")).to_contain_text(_TENANT_B_NAME)

        # ログアウトして一般メンバーとしてログイン
        page.request.post(f"{auth_server}/auth/logout")
        _login_as(page, auth_server, _MEMBER_EMAIL, _MEMBER_PASSWORD)

        # 一般メンバーは旧URLからも到達できずホームへ戻される
        # （権限による操作の出し分け＝ tenant_admin.py console_page のガード）
        page.goto(f"{auth_server}/admin/console")
        expect(page).to_have_url(f"{auth_server}{SYSTEM_SELECT}")


class TestTenantIsolation:
    """tenant_isolation: 出力のテナント分離（scoped_output_dir の効果をUI経由で確認）。"""

    def test_sample_report_is_not_visible_from_other_tenant(
        self, page: Page, auth_server: str
    ) -> None:
        """テナントAで展開したサンプルレポートは、テナントBのセッションから見えない。

        TestTenantMembership で作成済みの「テナントBだけに所属する一般メンバー」を
        再利用する（同一モジュールの専用サーバー内で状態を引き継ぐ）。
        """
        _login_as(page, auth_server, _ADMIN_EMAIL, _ADMIN_PASSWORD)

        # サンプルレポートをテナントAの出力先へ展開する
        # （UI の「サンプルレポートを見る」ボタン data-sample-report と同一の実API）。
        sample_resp = page.request.post(f"{auth_server}/api/sample-report")
        assert sample_resp.ok, sample_resp.text()
        sample_domain = sample_resp.json().get("domain")
        assert sample_domain, f"サンプルレポートの展開先ドメインが取得できません: {sample_resp.text()}"

        # /api/v1/sites は site_registry 由来（サンプル展開では登録されない）、
        # /api/history はサンプルを意図的に一覧から除外する設計（history.py のコメント参照）
        # のため、いずれもテナント分離の確認には使えない。scoped_output_dir をそのまま
        # 経由するドメイン別レポート取得エンドポイントで確認する。
        report_a = page.request.get(f"{auth_server}/api/v1/sites/{sample_domain}/report")
        assert report_a.ok, (
            f"テナントAでサンプル({sample_domain})のレポートが見えません: "
            f"{report_a.status} {report_a.text()}"
        )
        page.request.post(f"{auth_server}/auth/logout")

        # テナントBだけに所属する一般メンバーには見えない（scoped_output_dir の効果）
        _login_as(page, auth_server, _MEMBER_EMAIL, _MEMBER_PASSWORD)
        report_b = page.request.get(f"{auth_server}/api/v1/sites/{sample_domain}/report")
        assert not report_b.ok, (
            f"テナント分離が効いていません。テナントBからテナントAのサンプルの"
            f"レポートが見えています: {report_b.status}"
        )


class TestUserMenu:
    """user_menu_feedback: トップバーのユーザーメニューとフィードバック送信。"""

    def test_menu_opens_with_admin_items_and_no_shortcut_button(
        self, page: Page, auth_server: str
    ) -> None:
        """アイコンは即遷移せずメニューを開く。管理者は管理2画面を含む6項目。"""
        _login_as(page, auth_server, _ADMIN_EMAIL, _ADMIN_PASSWORD)
        page.goto(f"{auth_server}/")

        trigger = page.locator("#usermenu-trigger")
        expect(trigger).to_have_attribute("aria-expanded", "false")
        expect(page.locator("#usermenu-pop")).to_be_hidden()

        trigger.click()
        expect(trigger).to_have_attribute("aria-expanded", "true")
        items = page.locator("#usermenu-pop .usermenu-item")
        expect(items).to_have_count(6)
        expect(items.nth(0)).to_contain_text("個人設定")
        expect(items.nth(1)).to_contain_text("ユーザー管理")
        expect(items.nth(2)).to_contain_text("テナント管理")
        expect(items.nth(3)).to_contain_text("ユーザーガイド")
        expect(items.nth(4)).to_contain_text("フィードバック")
        expect(items.nth(5)).to_contain_text("ログアウト")

        # ヘッダーのキーボードショートカット起動ボタンは削除済み
        expect(page.locator("#shortcut-help-btn")).to_have_count(0)

        # Escape で閉じる（開きっぱなしで他の操作を塞がない）
        page.keyboard.press("Escape")
        expect(page.locator("#usermenu-pop")).to_be_hidden()

    def test_personal_settings_opens_as_in_app_view(self, page: Page, auth_server: str) -> None:
        """「個人設定」も画面内ビュー。サイドバーごと残り、別ページへ飛ばさない。"""
        _login_as(page, auth_server, _ADMIN_EMAIL, _ADMIN_PASSWORD)
        page.goto(f"{auth_server}/")
        page.locator("#usermenu-trigger").click()
        page.locator("#usermenu-account-btn").click()

        expect(page).to_have_url(f"{auth_server}/account")
        expect(page.locator("#topbar-title")).to_have_text("個人設定")
        # アプリの枠（サイドバー・ユーザーメニュー）が残っていることが「統一」の実体
        expect(page.locator(".app-sidebar")).to_be_visible()
        expect(page.locator("#usermenu-trigger")).to_be_visible()

        # モック認証でもログインにパスワードが要るので、変更手段が必ずある
        expect(page.locator("#password-form")).to_be_visible()
        # 中身は API から描かれる
        expect(page.locator("#account-profile")).to_contain_text(_ADMIN_EMAIL)
        # 他人の管理はユーザー管理ビューへ移した。この画面は「自分のこと」だけを扱う
        expect(page.locator("#account-members-card")).to_have_count(0)

    def test_old_account_url_redirects_to_view(self, page: Page, auth_server: str) -> None:
        """旧 /auth/account を開いても同じビューに着く。"""
        _login_as(page, auth_server, _ADMIN_EMAIL, _ADMIN_PASSWORD)
        page.goto(f"{auth_server}/auth/account")
        expect(page).to_have_url(f"{auth_server}/account")
        expect(page.locator("#view-account")).to_be_visible()

    def test_system_select_can_reach_personal_settings(
        self, page: Page, auth_server: str
    ) -> None:
        """システム選択からも個人設定へ行ける。

        この画面はアプリシェルの外でユーザーメニューが無く、システムを選ぶまで
        パスワード変更にすら到達できない状態だったため、専用の導線を置いている。
        """
        _login_as(page, auth_server, _ADMIN_EMAIL, _ADMIN_PASSWORD)
        page.goto(f"{auth_server}{SYSTEM_SELECT}")

        page.locator('.sysselect-account a[href="/account"]').click()
        expect(page).to_have_url(f"{auth_server}/account")
        expect(page.locator("#account-profile")).to_contain_text(_ADMIN_EMAIL)

    def test_user_guide_switches_view_in_place(self, page: Page, auth_server: str) -> None:
        """「ユーザーガイド」は画面内のビュー切替で、別ページへ飛ばさない。"""
        _login_as(page, auth_server, _ADMIN_EMAIL, _ADMIN_PASSWORD)
        page.goto(f"{auth_server}/")
        page.locator("#usermenu-trigger").click()
        page.locator("#usermenu-guide-btn").click()

        expect(page.locator("#topbar-title")).to_have_text("ユーザーガイド")
        expect(page.locator("#usermenu-pop")).to_be_hidden()

    def test_feedback_is_submitted_and_readable_by_admin(
        self, page: Page, auth_server: str
    ) -> None:
        """空送信はその場で止め、入力すれば保存され、管理者が読める。"""
        _login_as(page, auth_server, _ADMIN_EMAIL, _ADMIN_PASSWORD)
        page.goto(f"{auth_server}/")
        page.locator("#usermenu-trigger").click()
        page.locator("#usermenu-feedback-btn").click()

        # モーダルではなく画面内ビュー（他のメニュー項目と同じ表示方法）
        expect(page).to_have_url(f"{auth_server}/feedback")
        expect(page.locator("#view-feedback")).to_be_visible()
        expect(page.locator(".app-sidebar")).to_be_visible()
        # 送信者と「直前の画面」は画面側で補うため、空欄のまま出さない
        expect(page.locator("#feedback-meta-user")).not_to_have_text("-")
        expect(page.locator("#feedback-meta-view")).to_have_text("QAドキュメント生成")

        # 空のまま送ると、その場で止まる（サーバーまで往復しない）
        page.locator("#feedback-submit-btn").click()
        expect(page.locator("#feedback-status")).to_contain_text("内容を入力してください")

        message = "E2E からのフィードバック送信"
        page.locator("#feedback-message").fill(message)
        page.locator('input[name="feedback-category"][value="request"]').check()
        page.locator("#feedback-submit-btn").click()
        expect(page.locator("#feedback-status")).to_contain_text("送信しました")

        # ビューなので閉じない。入力だけ消えて、その場に留まる
        expect(page.locator("#view-feedback")).to_be_visible()
        expect(page.locator("#feedback-message")).to_have_value("")

        # 画面の成功表示だけで終わらせず、保存されたことを実データで確かめる
        listed = page.request.get(f"{auth_server}/api/feedback")
        assert listed.ok, listed.text()
        entries = listed.json()["feedback"]
        assert any(
            entry["message"] == message and entry["category"] == "request" for entry in entries
        ), entries


class TestUserManagement:
    """ユーザー管理ビュー: 一覧は表、新規登録と編集はダイアログ、削除は行から。

    旧・管理者コンソール（/admin/console）を統合した1画面なので、テナント管理も
    ここで検証する。
    """

    def test_view_opens_from_menu_in_place(self, page: Page, auth_server: str) -> None:
        """「ユーザー管理」も画面内ビュー。別ページへ飛ばさない。"""
        _login_as(page, auth_server, _ADMIN_EMAIL, _ADMIN_PASSWORD)
        page.goto(f"{auth_server}/")
        page.locator("#usermenu-trigger").click()
        page.locator("#usermenu-users-btn").click()

        expect(page).to_have_url(f"{auth_server}/user-management")
        expect(page.locator("#topbar-title")).to_have_text("ユーザー管理")
        expect(page.locator(".app-sidebar")).to_be_visible()

        # ユーザーとテナントが同じ画面に並ぶ（別画面に分けない）
        admin_row = page.locator(f'#uadm-user-rows tr:has-text("{_ADMIN_EMAIL}")')
        expect(admin_row).to_have_count(1)
        # 自分自身は消せない・所属も変えられないので操作を出さない
        expect(admin_row).to_contain_text("自分")
        expect(admin_row.locator("button")).to_have_count(0)
        expect(page.locator("#uadm-user-count")).to_contain_text("表示中")
        # テナント管理は別画面（この画面に混ぜない）
        expect(page.locator("#uadm-tenant-rows")).to_have_count(0)

        # 新規登録はフォーム常設ではなくダイアログ（開くまで出さない）
        expect(page.locator("#uadm-add-modal")).to_be_hidden()
        page.locator("#uadm-add-btn").click()
        expect(page.locator("#uadm-add-modal")).to_be_visible()
        page.keyboard.press("Escape")
        expect(page.locator("#uadm-add-modal")).to_be_hidden()

    def test_registers_user_then_resets_password_in_dialog(
        self, page: Page, auth_server: str
    ) -> None:
        """新規登録も編集もダイアログで行い、リセット後の資格情報で実際にログインできる。

        画面の成功表示だけで終わらせず、保存されたことを実データで確かめる
        （保存されたかどうかが利用者にとっての結果のため）。
        """
        _login_as(page, auth_server, _ADMIN_EMAIL, _ADMIN_PASSWORD)
        page.goto(f"{auth_server}/user-management")

        page.locator("#uadm-add-btn").click()
        page.locator("#uadm-add-name").fill("E2E Reset Target")
        page.locator("#uadm-add-email").fill(_RESET_EMAIL)
        page.locator("#uadm-add-password").fill(_RESET_INITIAL_PASSWORD)
        page.locator("#uadm-add-tenant").select_option(label=_TENANT_A_NAME)
        page.locator("#uadm-add-form button[type=submit]").click()

        expect(page.locator("#uadm-add-modal")).to_be_hidden()
        expect(page.locator("#uadm-user-status")).to_contain_text("登録しました")

        row = page.locator(f'#uadm-user-rows tr:has-text("{_RESET_EMAIL}")')
        expect(row).to_have_count(1)
        # 行に並ぶ操作は「編集」「削除」の2つ（列幅に収まる大きさに抑えている）
        expect(row.locator("button")).to_have_count(2)

        row.locator(".uadm-edit-btn").click()
        modal = page.locator("#uadm-edit-modal")
        expect(modal).to_be_visible()
        expect(page.locator("#uadm-edit-title")).to_have_text("E2E Reset Target を編集")

        page.locator("#uadm-edit-password").fill(_RESET_NEW_PASSWORD)
        page.locator("#uadm-reset-submit").click()
        expect(modal).to_be_hidden()
        expect(page.locator("#uadm-user-status")).to_contain_text("リセットしました")

        # 旧パスワードでは入れない
        page.request.post(f"{auth_server}/auth/logout")
        page.goto(f"{auth_server}/auth/login")
        page.locator("#email").fill(_RESET_EMAIL)
        page.locator("#password").fill(_RESET_INITIAL_PASSWORD)
        page.locator("button.auth-submit").click()
        expect(page).to_have_url(re.compile(re.escape(f"{auth_server}/auth/login")))

        # 新パスワードなら入れる
        _login_as(page, auth_server, _RESET_EMAIL, _RESET_NEW_PASSWORD)

    def test_edit_dialog_closes_without_applying(self, page: Page, auth_server: str) -> None:
        """閉じただけでは何も起きない（ダイアログを開くこと自体で確定させない）。"""
        _login_as(page, auth_server, _ADMIN_EMAIL, _ADMIN_PASSWORD)
        page.goto(f"{auth_server}/user-management")

        page.locator(f'#uadm-user-rows tr:has-text("{_RESET_EMAIL}")').locator(
            ".uadm-edit-btn"
        ).click()
        modal = page.locator("#uadm-edit-modal")
        expect(modal).to_be_visible()
        page.locator("#uadm-edit-password").fill("typed-but-not-applied-1")
        modal.locator(".file-preview-header [data-dialog-close]").click()
        expect(modal).to_be_hidden()

        # 直前のリセットで設定したパスワードのままログインできる
        page.request.post(f"{auth_server}/auth/logout")
        _login_as(page, auth_server, _RESET_EMAIL, _RESET_NEW_PASSWORD)

    def test_membership_is_edited_in_dialog_across_tenants(
        self, page: Page, auth_server: str
    ) -> None:
        """所属とロールは編集ダイアログで変更でき、開き直しても維持される。"""
        _login_as(page, auth_server, _ADMIN_EMAIL, _ADMIN_PASSWORD)
        page.goto(f"{auth_server}/user-management")

        row = page.locator(f'#uadm-user-rows tr:has-text("{_RESET_EMAIL}")')
        expect(row).to_contain_text("一般")
        row.locator(".uadm-edit-btn").click()

        modal = page.locator("#uadm-edit-modal")
        expect(modal).to_be_visible()

        # テナントAでのロールを管理者へ上げ、テナントBにも所属させる
        tenant_a = modal.locator(f'.uadm-membership-row:has-text("{_TENANT_A_NAME}")')
        tenant_a.locator(".uadm-role-select").select_option("admin")
        tenant_b = modal.locator(f'.uadm-membership-row:has-text("{_TENANT_B_NAME}")')
        # 未所属のうちはロールを触らせない
        expect(tenant_b.locator(".uadm-role-select")).to_be_disabled()
        tenant_b.locator("input[type=checkbox]").check()
        expect(tenant_b.locator(".uadm-role-select")).to_be_enabled()

        page.locator("#uadm-membership-save").click()
        expect(modal).to_be_hidden()
        expect(page.locator("#uadm-user-status")).to_contain_text("所属を更新しました")

        page.reload()
        updated = page.locator(f'#uadm-user-rows tr:has-text("{_RESET_EMAIL}")')
        expect(updated).to_contain_text(f"{_TENANT_A_NAME} / 管理者")
        expect(updated).to_contain_text(f"{_TENANT_B_NAME} / 一般")

    def test_search_filters_the_list(self, page: Page, auth_server: str) -> None:
        """一覧上の絞り込みは名前・ログインID・テナント名に効き、件数も追随する。"""
        _login_as(page, auth_server, _ADMIN_EMAIL, _ADMIN_PASSWORD)
        page.goto(f"{auth_server}/user-management")

        expect(page.locator(f'#uadm-user-rows tr:has-text("{_ADMIN_EMAIL}")')).to_have_count(1)
        page.locator("#uadm-user-search").fill("e2e-reset")
        expect(page.locator(f'#uadm-user-rows tr:has-text("{_RESET_EMAIL}")')).to_have_count(1)
        expect(page.locator(f'#uadm-user-rows tr:has-text("{_ADMIN_EMAIL}")')).to_have_count(0)
        expect(page.locator("#uadm-user-count")).to_contain_text("1件 表示中")

        # 一致が無いときは黙って空の表を見せない
        page.locator("#uadm-user-search").fill("no-such-person-xyz")
        expect(page.locator("#uadm-user-rows")).to_contain_text("一致するユーザーがいません")

    def test_user_is_deleted_from_the_row(self, page: Page, auth_server: str) -> None:
        """行の操作は無効化ではなく削除。消えたら一覧からもログインからも消える。"""
        _login_as(page, auth_server, _ADMIN_EMAIL, _ADMIN_PASSWORD)
        page.goto(f"{auth_server}/user-management")

        row = page.locator(f'#uadm-user-rows tr:has-text("{_RESET_EMAIL}")')
        # 無効化は廃止済み（同じ目的の操作が2通りあると、どちらが正か分からなくなる）
        expect(page.locator("#uadm-user-rows .uadm-active-btn")).to_have_count(0)

        page.once("dialog", lambda dialog: dialog.accept())
        row.locator(".uadm-delete-user-btn").click()
        expect(page.locator("#uadm-user-status")).to_contain_text("削除しました")
        expect(page.locator(f'#uadm-user-rows tr:has-text("{_RESET_EMAIL}")')).to_have_count(0)

        # 画面の表示だけで終わらせず、実際にログインできなくなったことを確かめる
        page.request.post(f"{auth_server}/auth/logout")
        page.goto(f"{auth_server}/auth/login")
        page.locator("#email").fill(_RESET_EMAIL)
        page.locator("#password").fill(_RESET_NEW_PASSWORD)
        page.locator("button.auth-submit").click()
        expect(page).to_have_url(re.compile(re.escape(f"{auth_server}/auth/login")))

    def test_member_cannot_see_or_use_user_management(
        self, page: Page, auth_server: str
    ) -> None:
        """一般メンバーにはメニュー項目を出さず、URL直打ちでも操作させない。"""
        _login_as(page, auth_server, _MEMBER_EMAIL, _MEMBER_PASSWORD)
        page.goto(f"{auth_server}/")

        page.locator("#usermenu-trigger").click()
        expect(page.locator("#usermenu-users-btn")).to_have_count(0)
        expect(page.locator("#usermenu-pop .usermenu-item")).to_have_count(4)

        page.goto(f"{auth_server}/user-management")
        expect(page.locator("#uadm-denied-card")).to_be_visible()
        expect(page.locator("#uadm-add-btn")).to_be_hidden()

        page.goto(f"{auth_server}/tenant-management")
        expect(page.locator("#tadm-denied-card")).to_be_visible()
        expect(page.locator("#tadm-add-btn")).to_be_hidden()

    def test_password_reset_api_rejects_non_admin(self, page: Page, auth_server: str) -> None:
        """画面を隠すだけでなく、APIそのものが一般メンバーを拒否する。"""
        _login_as(page, auth_server, _MEMBER_EMAIL, _MEMBER_PASSWORD)
        resp = page.request.post(
            f"{auth_server}/api/admin/tenancy/users/anything/password",
            data={"password": "should-not-work-1"},
        )
        assert resp.status == 403, f"{resp.status} {resp.text()}"


class TestTenantManagement:
    """テナント管理ビュー: ユーザー管理とは別画面で、登録・改名・削除まで完結する。"""

    def test_view_opens_from_menu_in_place(self, page: Page, auth_server: str) -> None:
        _login_as(page, auth_server, _ADMIN_EMAIL, _ADMIN_PASSWORD)
        page.goto(f"{auth_server}/")
        page.locator("#usermenu-trigger").click()
        page.locator("#usermenu-tenants-btn").click()

        expect(page).to_have_url(f"{auth_server}/tenant-management")
        expect(page.locator("#topbar-title")).to_have_text("テナント管理")
        expect(page.locator(".app-sidebar")).to_be_visible()
        expect(page.locator("#tadm-rows tr")).not_to_have_count(0)
        # 利用者の管理は持ち込まない（画面の責務を分けている）
        expect(page.locator("#uadm-user-rows tr")).to_have_count(0)

    def test_tenant_is_registered_renamed_and_deleted(
        self, page: Page, auth_server: str
    ) -> None:
        """登録・改名・削除がダイアログと行の操作で完結する。"""
        _login_as(page, auth_server, _ADMIN_EMAIL, _ADMIN_PASSWORD)
        page.goto(f"{auth_server}/tenant-management")

        page.locator("#tadm-add-btn").click()
        page.locator("#tadm-name").fill("E2E Tenant C")
        page.locator("#tadm-slug").fill("e2e-tenant-c")
        page.locator("#tadm-add-form button[type=submit]").click()
        expect(page.locator("#tadm-add-modal")).to_be_hidden()
        expect(page.locator("#tadm-status")).to_contain_text("登録しました")

        row = page.locator('#tadm-rows tr:has-text("e2e-tenant-c")')
        expect(row).to_have_count(1)

        row.locator(".tadm-edit-btn").click()
        expect(page.locator("#tadm-edit-modal")).to_be_visible()
        # slug は保存先ディレクトリ名なので変更させず、そのことを画面に出す
        expect(page.locator("#tadm-edit-slug")).to_have_text("e2e-tenant-c")
        page.locator("#tadm-rename").fill("E2E Tenant C2")
        page.locator("#tadm-edit-form button[type=submit]").click()
        expect(page.locator("#tadm-edit-modal")).to_be_hidden()
        expect(page.locator("#tadm-rows")).to_contain_text("E2E Tenant C2")

        page.once("dialog", lambda dialog: dialog.accept())
        page.locator('#tadm-rows tr:has-text("e2e-tenant-c")').locator(
            ".tadm-delete-btn"
        ).click()
        # 生成物が残ることを黙って伏せない
        expect(page.locator("#tadm-status")).to_contain_text("残っています")
        expect(page.locator('#tadm-rows tr:has-text("e2e-tenant-c")')).to_have_count(0)

    def test_search_filters_the_list(self, page: Page, auth_server: str) -> None:
        """名前・slug での絞り込みと件数表示。"""
        _login_as(page, auth_server, _ADMIN_EMAIL, _ADMIN_PASSWORD)
        page.goto(f"{auth_server}/tenant-management")

        expect(page.locator(f'#tadm-rows tr:has-text("{_TENANT_B_SLUG}")')).to_have_count(1)
        page.locator("#tadm-search").fill("no-such-tenant-xyz")
        expect(page.locator("#tadm-rows")).to_contain_text("一致するテナントがありません")
        expect(page.locator("#tadm-count")).to_contain_text("0件 表示中")
