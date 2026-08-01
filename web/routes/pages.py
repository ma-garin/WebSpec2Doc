from __future__ import annotations

from flask import Blueprint, abort, render_template

bp = Blueprint("pages", __name__)

# サイドバーの各画面（templates/partials/nav.html の data-view と対応）。
# ブックマーク/共有/リロードでも同じ画面を開けるよう、画面名ごとに URL を割り当てる。
_VIEW_NAMES = frozenset(
    {
        "dashboard",
        "generate",
        "qa-quality",
        "viewpoints",
        "auto-run",
        "testcases",
        "run-history",
        "user-guide",
        "references",
        "settings",
    }
)
_VIEW_ALIASES = {"home": "dashboard"}

# 設定画面のタブ（templates/partials/view-settings.html の data-tab と対応）。
# タブごとに URL を持たせ、共有・ブックマーク・ブラウザの戻るを効かせる。
_SETTINGS_TABS = frozenset(
    {"api", "crawl", "notify", "operations", "data", "audit", "test-design"}
)


@bp.route("/")
def index() -> str:
    return render_template("index.html")


@bp.route("/systems")
def systems() -> str:
    """ログイン後のシステム選択ハブ。ドキュメント作成 / AutoRun / CLI モードを選ぶ。"""
    return render_template("system-select.html")


@bp.route("/cli")
def cli_mode() -> str:
    """CLI モード（System 03）の案内。

    CLI 自体は画面を持たない（端末で動かす）ため、このページは実行はせず、
    貼り付けられるコマンドの組み立てと、できること・終了コードの案内だけを行う。
    ドメインの候補は実際の出力先から取るので、存在しない名前を勧めない。
    """
    from web.config import OUTPUT_DIR
    from web.tenancy import TENANTS_DIR_NAME, scoped_output_dir

    out = scoped_output_dir(OUTPUT_DIR)
    domains: list[str] = []
    if out.is_dir():
        domains = sorted(
            d.name
            for d in out.iterdir()
            if d.is_dir() and not d.name.startswith(".") and d.name != TENANTS_DIR_NAME
        )
    return render_template("cli.html", domains=domains)


@bp.route("/settings/<tab>")
def settings_tab(tab: str) -> str:
    """設定画面をタブ指定で開く（例: /settings/api）。

    リロード・直リンクでも同じタブが開くようにする。実際のタブ切替は
    クライアント側の syncSettingsTabFromPath() が location.pathname を見て行う。
    """
    if tab not in _SETTINGS_TABS:
        abort(404)
    return render_template("index.html")


@bp.route("/<view_name>")
def view(view_name: str) -> str:
    resolved = _VIEW_ALIASES.get(view_name, view_name)
    if resolved not in _VIEW_NAMES:
        abort(404)
    # 実際の画面切替はクライアント側の switchView() が location.pathname を見て行う。
    return render_template("index.html")
