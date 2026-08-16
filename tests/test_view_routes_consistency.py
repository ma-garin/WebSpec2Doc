"""画面名の一覧が、サーバー（Flask）とクライアント（core.js）でずれていないか。

画面ごとの URL は二重に定義されている:
- `web/routes/pages.py` の `_VIEW_NAMES` … その URL を配ってよいかの判定
- `static/js/core.js` の `VIEW_PATHS` … ビュー名から URL を組み立てる表

片方にだけ足すと、404 になるか「URL は通るのに何も表示されない」状態になる。
どちらも人手で書く表なので、集合が一致することをここで担保する。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# core.js の VIEW_PATHS は `name: '/path',` の並び。クォート有無の両方を拾う。
_ENTRY_RE = re.compile(r"^\s*'?([a-z0-9-]+)'?\s*:\s*'(/[^']*)'\s*,", re.MULTILINE)


def _client_view_paths() -> dict[str, str]:
    text = (ROOT / "static" / "js" / "core.js").read_text(encoding="utf-8")
    start = text.index("const VIEW_PATHS = {")
    end = text.index("};", start)
    return dict(_ENTRY_RE.findall(text[start:end]))


def _server_view_names() -> set[str]:
    from web.routes.pages import _VIEW_NAMES

    return set(_VIEW_NAMES)


def test_client_and_server_agree_on_view_names() -> None:
    client = _client_view_paths()
    # dashboard だけは "/" を持ち、`/<view_name>` ではなく専用ルートで配られる
    client_names = set(client) - {"dashboard"}
    server_names = _server_view_names() - {"dashboard"}

    assert client_names == server_names, (
        f"core.js にのみ存在: {sorted(client_names - server_names)} / "
        f"pages.py にのみ存在: {sorted(server_names - client_names)}"
    )


def test_view_paths_match_their_names() -> None:
    """URL は画面名からそのまま作る（/account なら 'account'）。"""
    for name, path in _client_view_paths().items():
        if name == "dashboard":
            continue
        assert path == f"/{name}", f"{name} の URL が {path} になっている"


def test_parser_actually_found_entries() -> None:
    """正規表現が壊れて 0 件になったとき、上の2件が空振りで PASS しないようにする。"""
    assert len(_client_view_paths()) >= 10
