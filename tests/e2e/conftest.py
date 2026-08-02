"""E2E テスト共通設定。

使用方法:
    make verify-ui          # Flask サーバーを自動起動して E2E 実行
    pytest tests/e2e/ -v    # サーバーが起動済みの場合に単独実行

必要条件:
    - venv が有効化されていること
    - playwright install chromium が完了していること
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Generator
from pathlib import Path
from urllib.parse import urlparse

import pytest
import requests

try:
    from playwright.sync_api import sync_playwright  # noqa: F401

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

try:
    from playwright.sync_api import Page, expect
except ImportError:
    Page = object  # type: ignore[assignment,misc]
    expect = None  # type: ignore[assignment]

# プロジェクトルートを sys.path に追加
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")
# 利用者が宛先を明示したか。明示されているなら、E2E の都合で勝手に別ポートへ
# 動かさない。指定した先を見ているつもりで別のサーバーを検証させない。
URL_WAS_PINNED = bool(os.environ.get("WEBSPEC2DOC_E2E_URL", "").strip())
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# ── 既知 flaky の隔離（quarantine）──────────────────────────────────
# 隔離機構は残すが、現在は 0 件（Phase A で全件を根本修正して解除した）。
# 恒久修正の記録は docs/sdlc/40_test/WS2D-DL-001_不具合管理台帳.md を参照。
# 将来 flaky が出た場合はここに "ファイル::クラス::テスト" を追加する。
# 一時解除するには WEBSPEC2DOC_E2E_NO_QUARANTINE=1 を設定する。
_QUARANTINED_TESTS: frozenset[str] = frozenset()


def pytest_configure(config: pytest.Config) -> None:
    """収集より前に、E2E が使う宛先を確定させる。

    各テストはモジュール読み込み時に WEBSPEC2DOC_E2E_URL から宛先を組み立てる。
    収集はこのフックの後に走るので、ここで決めれば全テストに伝わる。
    fixture まで待つと手遅れになる。
    """
    if os.environ.get("WEBSPEC2DOC_E2E_EXTERNAL") == "1":
        return
    if not (_server_is_up(BASE_URL) and not _server_uses_isolated_db(BASE_URL)):
        return
    if URL_WAS_PINNED:
        # 明示された宛先を黙って変えない。利用者はそのURLを検証したいはずで、
        # 別ポートへ移すと「指定した先を見ているつもりで別物を見る」ことになる。
        pytest.exit(
            f"{BASE_URL} で開発用DBを使うサーバーが動いています。"
            "WEBSPEC2DOC_E2E_URL で宛先を指定しているため別ポートへは移しません。"
            "そのサーバーを止めるか、共有してよいなら WEBSPEC2DOC_E2E_EXTERNAL=1 を"
            "指定してください。",
            returncode=1,
        )
    _use_fallback_port()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """隔離指定のテストをスキップする（環境変数で無効化可能）。現在は 0 件。"""
    if not _QUARANTINED_TESTS or os.environ.get("WEBSPEC2DOC_E2E_NO_QUARANTINE") == "1":
        return
    marker = pytest.mark.skip(reason="quarantined: 既知 flaky（tests/e2e/conftest.py 参照）")
    for item in items:
        for suffix in _QUARANTINED_TESTS:
            # nodeid 例: tests/e2e/test_x.py::TestY::test_z[chromium]
            base = item.nodeid.split("[", 1)[0]
            if base.endswith(suffix):
                item.add_marker(marker)
                break


def _server_is_up(url: str, timeout: float = 0.5) -> bool:
    """WebSpec2Doc 自身が応答しているかを確認する。

    生存確認だけでは、同じポートを別アプリが握っていても True になり、
    E2E が「別アプリを検証して緑」という偽陽性を出す。健全性エンドポイントの
    中身まで見て、WebSpec2Doc であることを確かめる。
    """
    try:
        response = requests.get(f"{url.rstrip('/')}/api/v1/healthz", timeout=timeout)
        payload = response.json()
    except Exception:
        return False
    return isinstance(payload, dict) and "scheduler" in payload


def _port_is_taken_by_other_app(url: str, timeout: float = 0.5) -> bool:
    """ポートは埋まっているが WebSpec2Doc ではない、という状態を検出する。"""
    try:
        requests.get(url, timeout=timeout)
    except Exception:
        return False
    return not _server_is_up(url, timeout)


@pytest.fixture(scope="session", autouse=True)
def require_playwright() -> None:
    """Playwright が未インストールの場合は E2E テストをスキップする。"""
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("playwright not installed — skipping E2E tests", allow_module_level=True)


E2E_DB_NAME = "viewpoints.e2e.db"


def _server_uses_isolated_db(url: str, timeout: float = 0.5) -> bool:
    """既に動いているサーバーが、E2E 専用の観点DBを使っているか。

    判定できない（古いサーバーで項目を返さない等）場合は False を返す。
    共有してよいか分からないものを共有しない。
    """
    try:
        payload = requests.get(f"{url.rstrip('/')}/api/v1/healthz", timeout=timeout).json()
    except Exception:
        return False
    return isinstance(payload, dict) and payload.get("viewpoints_db") == E2E_DB_NAME


# 退避先ポートを押さえておくソケット。選んだ直後に手放すと、サーバーが
# bind するまでの間に他プロセスへ奪われうる。起動直前まで握り続ける。
_RESERVED_SOCKET: socket.socket | None = None


def _use_fallback_port() -> None:
    """開発サーバーと衝突しないポートへ移る。

    開発サーバーが既定ポートを握っているとき、それを止めさせるのは
    作業の中断を強いる。E2E 側が別ポートで自前のサーバーを立てればよい。

    各テストは conftest の変数ではなく WEBSPEC2DOC_E2E_URL から独自に
    宛先を組み立てる。モジュール変数だけ書き換えても伝わらないため、
    環境変数も同時に更新する。収集はこの呼び出しより後に走るので間に合う。
    """
    global BASE_URL, _RESERVED_SOCKET
    _RESERVED_SOCKET = socket.socket()
    _RESERVED_SOCKET.bind(("127.0.0.1", 0))
    BASE_URL = f"http://127.0.0.1:{_RESERVED_SOCKET.getsockname()[1]}"
    os.environ["WEBSPEC2DOC_E2E_URL"] = BASE_URL


def _release_reserved_port() -> None:
    """押さえていたポートを手放す。サーバーを起動する直前に呼ぶ。"""
    global _RESERVED_SOCKET
    if _RESERVED_SOCKET is not None:
        _RESERVED_SOCKET.close()
        _RESERVED_SOCKET = None


@pytest.fixture(scope="session", autouse=True)
def flask_server() -> Generator[None, None, None]:
    """Flask サーバーを session スコープで起動・終了する。

    環境変数 WEBSPEC2DOC_E2E_EXTERNAL=1 が設定されている場合は
    外部サーバーを使用し、自動起動をスキップする。

    既にサーバーが動いていても、それが開発用DBを使っているなら乗らない。
    E2E は観点セットを作ったり消したりするため、開発中のデータに検証用の
    残骸が残る。実際に「E2E削除対象-*」が469件溜まり、分類ツリーが
    読めなくなったことがある。専用DBで起動し直す。
    """
    if os.environ.get("WEBSPEC2DOC_E2E_EXTERNAL") == "1":
        yield
        return

    if _server_is_up(BASE_URL):
        yield
        return

    if _port_is_taken_by_other_app(BASE_URL):
        pytest.fail(
            f"{BASE_URL} で WebSpec2Doc 以外のアプリが応答しています。"
            "そのまま実行すると別アプリを検証して緑になるため中止しました。"
            "該当プロセスを止めるか、WEBSPEC2DOC_E2E_URL で別ポートを指定してください。"
        )

    # app.py は WEBSPEC2DOC_PORT を見て待ち受けポートを決める。
    # BASE_URL（= WEBSPEC2DOC_E2E_URL）で別ポートを指定しても、起動側へ
    # そのポートを渡さないと既定 8765 で起動して疎通せず、全テストが
    # スキップ→「緑」になってしまう（E2E ゲートが形骸化する）。
    # BASE_URL のポートを起動側にも必ず渡す。
    # E2E は観点セットを作ったり消したりする。既定の instance/viewpoints.db を
    # そのまま使うと、開発中のデータに検証用のセットや観点が残る。実際に
    # 「E2E削除対象-*」が469件溜まり、分類ツリーが読めなくなったことがある。
    # 専用DBへ逃がし、実行のたびに作り直す。
    e2e_db = ROOT / "instance" / E2E_DB_NAME
    for pattern in (f"{e2e_db.name}*", "auth.e2e.db*"):
        for leftover in e2e_db.parent.glob(pattern):
            leftover.unlink(missing_ok=True)

    proc = _spawn_server(e2e_db)
    try:
        yield
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _spawn_server(e2e_db: Path) -> subprocess.Popen[bytes]:
    """サーバーを起動し、疎通するまで待つ。

    退避先のポートは、選んだ時点から起動直前まで握り続けている。
    ここで手放してすぐ起動するため、他プロセスに奪われる隙をほぼ残さない。
    奪われた場合は疎通せず、緑にはならない（失敗として扱う）。
    """
    # app.py は WEBSPEC2DOC_PORT を見て待ち受けポートを決める。
    # BASE_URL（= WEBSPEC2DOC_E2E_URL）で別ポートを指定しても、起動側へ
    # そのポートを渡さないと既定 8765 で起動して疎通せず、全テストが
    # スキップ→「緑」になってしまう（E2E ゲートが形骸化する）。
    env = {
        **os.environ,
        "FLASK_TESTING": "1",
        # E2E は認証なし（ユーザー0人）の前提で画面を触る。初期管理者ができると
        # 全ページがログイン必須になり、既存のE2Eが一斉にログイン壁へ落ちる。
        # 自動作成を止めるだけでなく、認証DBも観点DBと同様に専用ファイルへ逃がす
        # （開発中の instance/auth.db を E2E が読み書きしないようにする）。
        "WEBSPEC2DOC_BOOTSTRAP_ADMIN": "0",
        "WEBSPEC2DOC_AUTH_DB": str(e2e_db.with_name("auth.e2e.db")),
        "PYTHONPATH": str(ROOT),
        "WEBSPEC2DOC_PORT": str(urlparse(BASE_URL).port or 8765),
        "VIEWPOINTS_DB": str(e2e_db),
    }
    _release_reserved_port()
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(20):  # 最大10秒
        if _server_is_up(BASE_URL):
            return proc
        time.sleep(0.5)
    proc.terminate()
    proc.wait(timeout=10)
    # ここを skip にすると「サーバーが起動しなかった＝未検証」を「緑」と
    # 誤認させる。E2E を要求した以上、起動できないのは失敗として扱う。
    pytest.fail(
        f"Flask サーバーが {BASE_URL} で起動しませんでした。"
        "E2E は未実行です（この状態を PASS 扱いにしない）。"
    )


@pytest.fixture(scope="session")
def browser_context_args() -> dict:
    return {
        "viewport": {"width": 1280, "height": 800},
        "locale": "ja-JP",
    }


# playwright タイムアウトを明示設定（デフォルト 30 秒では CI 環境で不安定になることがある）
@pytest.fixture(scope="session")
def playwright_timeout() -> int:
    return 45_000  # 45 秒


@pytest.fixture(scope="session", autouse=True)
def configure_expect_timeout() -> None:
    """非同期UIの期待値待機を、連続E2E向けに明示設定する。"""
    if expect is not None:
        expect.set_options(timeout=15_000)


@pytest.fixture(autouse=True)
def skip_onboarding_tour(request: pytest.FixtureRequest) -> None:
    """オンボーディングツアーを完了済みとして始め、E2E を決定的にする。

    driver.js のツアーはフレッシュなブラウザで自動起動し、その SVG オーバーレイ
    （`.driver-overlay`）がクリックを遮る。テストごとに新しいコンテキストが作られるため、
    ツアーが出るかどうかがタイミング次第になり「element intercepts pointer events」で
    45 秒タイムアウトする経路があった（ユーザーガイド・観点ダイアログ等）。

    ツアー自体を検証する E2E は無いため、常に完了済みにして固定する。
    ツアーを検証したくなった場合は、そのテストで localStorage を消してから遷移する。
    """
    if "page" not in request.fixturenames:
        return
    page = request.getfixturevalue("page")
    page.add_init_script(
        "try { localStorage.setItem('webspec2doc.onboarding.tour-completed', '1'); }"
        " catch (e) { /* private mode 等では何もしない */ }"
    )


@pytest.fixture(autouse=True)
def configure_page_timeouts(request: pytest.FixtureRequest) -> None:
    """page を使うテストに、長い連続実行向けの実タイムアウトを適用する。"""
    if "page" not in request.fixturenames:
        return
    page = request.getfixturevalue("page")
    page.set_default_timeout(45_000)
    page.set_default_navigation_timeout(60_000)


@pytest.fixture()
def page_with_screenshot(page: Page, request: pytest.FixtureRequest) -> Generator[Page, None, None]:
    """テスト失敗時に自動スクリーンショットを保存するページフィクスチャ。"""
    yield page
    if request.node.rep_call.failed if hasattr(request.node, "rep_call") else False:
        name = request.node.name.replace("/", "_").replace(":", "_")
        page.screenshot(path=str(SCREENSHOT_DIR / f"FAIL_{name}.png"), full_page=True)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Generator:
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)
