"""アプリ利用者認証・テナント管理の E2E テスト（L3 システムテスト、新規）。

対象（quality/feature_contracts.yml の critical だが L3(E2E) で未検証だった機能）:
    - account_auth: 本システムへのログイン認証（web/routes/account.py）
    - tenant_membership: テナント選択と所属管理（web/routes/tenant_admin.py, account.py）
    - tenant_isolation: テナント分離（web/tenancy.py の scoped_output_dir の効果）

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

設計上の注意（パスワードを使わない理由）:
    templates/auth/setup.html は `{% if not mock_auth %}` でパスワード欄自体を
    描画しない。WEBSPEC2DOC_AUTH_MOCK は既定で有効（モック認証）のため、
    このテストで作る全アカウントはパスワードなし（authenticate_passwordless）で
    統一する。既定設定のまま実挙動を検証するための選択であり、意図的にモックを
    無効化していない（無効化すると今度はパスワードなしメンバー作成が
    enforce_password_policy に落ちる）。

実行方法:
    venv/bin/python -m pytest tests/e2e/test_auth_tenant_e2e.py -q
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
import requests
from playwright.sync_api import Page, expect

ROOT = Path(__file__).parent.parent.parent

_ADMIN_EMAIL = "e2e-admin@example.com"
_TENANT_A_NAME = "E2E Tenant A"
_TENANT_B_NAME = "E2E Tenant B"
_TENANT_B_SLUG = "e2e-tenant-b"
_MEMBER_EMAIL = "e2e-member@example.com"

USER_SELECT = "/auth/user"
TENANT_SELECT = "/auth/tenant"
SYSTEM_SELECT = "/systems"


def _wait_for_health(url: str, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(f"{url}/api/v1/healthz", timeout=0.5).ok:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.3)
    return False


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


def _login_as(page: Page, base_url: str, email: str) -> None:
    """ログイン→ユーザー選択→テナント選択を経て /systems に到達する（モック認証・パスワードなし）。

    mock_auth 有効時、login.html はパスワード未入力なら
    store.authenticate_passwordless を通す（web/routes/account.py の login_submit）。
    """
    page.goto(f"{base_url}/auth/login")
    page.locator("#email").fill(email)
    page.locator("button.auth-submit").click()

    expect(page).to_have_url(f"{base_url}{USER_SELECT}")
    # 「自分のまま続ける」（候補一覧の先頭、user_id が空の隠しフィールドを持つフォーム）
    page.locator(
        'form[action="/auth/user"]:has(input[name="user_id"][value=""]) button[type="submit"]'
    ).click()

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

        # setup.html は mock_auth 有効時にパスワード欄を出さない（{% if not mock_auth %}）。
        # 空パスワードのまま作成され、以降はモック認証（パスワードなし）で扱われる。
        page.locator("#tenant_name").fill(_TENANT_A_NAME)
        page.locator("#name").fill("E2E Admin")
        page.locator("#email").fill(_ADMIN_EMAIL)
        page.locator("button.auth-submit").click()
        # setup_submit はセッションを即座に発行し、テナントも決定済みで /systems へ進む
        expect(page).to_have_url(f"{auth_server}{SYSTEM_SELECT}")

        # ログアウト（ログアウトフォームは複数画面に重複して存在するため、
        # 同一の実ルートへ直接 POST して検証を簡潔にする。ブラウザの Cookie は
        # page.request と共有されるため、以降のページ遷移にも反映される）。
        page.request.post(f"{auth_server}/auth/logout")

        # 匿名アクセス: ユーザーが存在するため認証が有効になり、保護ページは
        # ログイン画面へリダイレクトされる（ログアウトで再びガードされることの確認）。
        page.goto(f"{auth_server}{SYSTEM_SELECT}")
        expect(page).to_have_url(re.compile(r"/auth/login"))

        # 再ログイン→ 本来の遷移（ユーザー選択→テナント選択→システム選択）に進む
        _login_as(page, auth_server, _ADMIN_EMAIL)
        expect(page).to_have_url(f"{auth_server}{SYSTEM_SELECT}")


class TestTenantMembership:
    """tenant_membership: テナント選択と所属管理（管理者/一般の出し分け）。"""

    def test_admin_console_lists_members_and_restricts_by_role(
        self, page: Page, auth_server: str
    ) -> None:
        """管理コンソールにメンバー一覧が表示され、一般メンバーは到達できない。"""
        _login_as(page, auth_server, _ADMIN_EMAIL)

        # 管理者は管理コンソールに到達できる
        page.goto(f"{auth_server}/admin/console")
        expect(page).to_have_url(f"{auth_server}/admin/console")
        expect(page.locator("#tenant-form")).to_be_visible()

        # テナントB・一般メンバーを作る。管理コンソールと同一の実APIを、認証済みの
        # ブラウザセッション（page.request は Cookie を共有する）から直接叩く。
        # admin-console.js のフォーム送信の実装詳細に依存せず、ゲートの効果
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
            },
        )
        assert user_resp.ok, user_resp.text()

        # 管理コンソールを開き直すと、作成したテナント・メンバーが一覧に表示される
        page.goto(f"{auth_server}/admin/console")
        expect(page.locator("#tenant-rows")).to_contain_text(_TENANT_B_NAME)
        rows_text = page.locator("#user-rows").inner_text()
        assert "E2E Member" in rows_text or _MEMBER_EMAIL in rows_text, rows_text

        # ログアウトして一般メンバーとしてログイン（パスワードなし＝モック認証）
        page.request.post(f"{auth_server}/auth/logout")
        _login_as(page, auth_server, _MEMBER_EMAIL)

        # 一般メンバーは管理コンソールに到達できず /systems へ戻される
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
        _login_as(page, auth_server, _ADMIN_EMAIL)

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
        _login_as(page, auth_server, _MEMBER_EMAIL)
        report_b = page.request.get(f"{auth_server}/api/v1/sites/{sample_domain}/report")
        assert not report_b.ok, (
            f"テナント分離が効いていません。テナントBからテナントAのサンプルの"
            f"レポートが見えています: {report_b.status}"
        )
