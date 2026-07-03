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
    return "127.0.0.1", True


def _open_browser() -> None:
    import time

    time.sleep(1.0)
    webbrowser.open(f"http://127.0.0.1:{PORT}")


if __name__ == "__main__":
    host, open_browser = _bind_host()
    if open_browser:
        threading.Thread(target=_open_browser, daemon=True).start()
    app.run(host=host, port=PORT, debug=False)
