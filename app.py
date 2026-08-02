from __future__ import annotations

import os
import threading
import webbrowser

from web import create_app
from web.config import PORT
from web.security import TRUSTED_HOSTS_ENV

app = create_app()


def _bind_host() -> tuple[str, bool]:
    """バインドするホストと、ブラウザ自動起動の要否を返す。

    WEBSPEC2DOC_TRUSTED_HOSTS が設定されている場合（社内サーバ/コンテナ展開）は
    0.0.0.0 で待ち受ける。localhost_guard が許可ホスト以外を 403 で拒否するため、
    到達制御はガード側で担保される。未設定なら従来どおり 127.0.0.1 限定。
    """
    if os.environ.get(TRUSTED_HOSTS_ENV, "").strip():
        # localhost_guard が許可ホスト以外を 403 で拒否するため到達制御はガード側で担保する。
        # 明示的な社内展開時（TRUSTED_HOSTS 設定時）のみ全 IF バインドする。
        return "0.0.0.0", False  # nosec B104  # noqa: S104
    testing = os.environ.get("FLASK_TESTING", "").strip() == "1"
    return "127.0.0.1", not testing


def _open_browser() -> None:
    import time

    time.sleep(1.0)
    webbrowser.open(f"http://127.0.0.1:{PORT}")


BOOTSTRAP_ADMIN_ENV = "WEBSPEC2DOC_BOOTSTRAP_ADMIN"


def _bootstrap_initial_admin() -> None:
    """ユーザーが1人も居なければ初期管理者（admin / password）を用意する。

    サーバー起動時にだけ呼ぶ。app モジュールを import するだけの単体テストは
    ここを通らないため、テスト用の空DB前提を壊さない。E2E は
    WEBSPEC2DOC_BOOTSTRAP_ADMIN=0 で明示的に無効化する。
    """
    if os.environ.get(BOOTSTRAP_ADMIN_ENV, "1").strip().lower() in ("0", "off", "false"):
        return
    from web.services.auth_store import INITIAL_ADMIN_LOGIN_ID, get_auth_store

    created = get_auth_store().ensure_initial_admin()
    if created is not None:
        print(f"初期管理者を作成しました: ログインID={INITIAL_ADMIN_LOGIN_ID} / パスワード=password")


if __name__ == "__main__":
    from crawler.playwright_runtime import PlaywrightRuntimeError, verify_playwright_runtime

    try:
        runtime = verify_playwright_runtime()
    except PlaywrightRuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        f"Playwright Chromium {runtime.chromium_version} 起動確認済み " f"({runtime.browsers_path})"
    )
    _bootstrap_initial_admin()
    host, open_browser = _bind_host()
    if open_browser:
        threading.Thread(target=_open_browser, daemon=True).start()
    app.run(host=host, port=PORT, debug=False)
