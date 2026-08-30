from __future__ import annotations

from flask import Blueprint, Response, abort, redirect, render_template

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
        # サイドバーには無く、トップバーのユーザーメニューから開く画面。
        # 表示方法を他のビューに揃えたので、URL も同じ規則で持たせる。
        "account",
        "user-management",
        "tenant-management",
        "feedback",
        # テスト自動化（System 02）の旧 12 画面。新シェル /test-automation へ 302 で送る。
        # 名前を残すのは、既存のブックマーク・共有リンクを 404 にしないため。
        "test-activity",
        "test-plan",
        "test-analysis",
        "test-strategy",
        "test-design",
        "test-implementation",
        "test-execution",
        "manual-execution",
        "defect-analysis",
        "code-fix",
        "test-completion",
        "integrations",
    }
)
_VIEW_ALIASES = {"home": "dashboard"}

# テスト自動化（System 02）の旧画面。中身は /test-automation に統合済みで、
# ここに載っている名前はすべて 302 で新シェルへ送るだけになる。
_TESTLAB_VIEWS = frozenset(
    {
        "test-activity",
        "test-plan",
        "test-analysis",
        "test-strategy",
        "test-design",
        "test-implementation",
        "test-execution",
        "manual-execution",
        "defect-analysis",
        "code-fix",
        "test-completion",
        "integrations",
    }
)


# 設定画面のタブ（templates/partials/view-settings.html の data-tab と対応）。
# タブごとに URL を持たせ、共有・ブックマーク・ブラウザの戻るを効かせる。
_SETTINGS_TABS = frozenset(
    {"api", "crawl", "notify", "integrations", "operations", "data", "audit", "test-design"}
)



def _may_use_testlab() -> bool:
    """テスト自動化を使えるか。認証オフの開発環境では制限しない。"""
    from flask import g

    from web.auth import auth_enabled

    if not auth_enabled():
        return True
    user: dict[str, object] | None = getattr(g, "auth_user", None)
    if not user:
        return False
    return user.get("role") == "admin"


@bp.route("/")
def index() -> str:
    return render_template("index.html")


@bp.route("/test-automation")
def test_automation() -> str:
    """テスト自動化（System 02）。index.html とは別の独立シェルを返す。"""
    if not _may_use_testlab():
        # 存在は隠さず 403 にする。404 にすると権限の問題か綴り違いか切り分けられない。
        abort(403)
    return render_template("test-automation.html")


@bp.route("/systems")
def systems() -> str:
    """ログイン後のシステム選択ハブ。ドキュメント作成 / テスト自動化 / AutoRun / CLI・API を選ぶ。"""
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
def view(view_name: str) -> str | Response:
    resolved = _VIEW_ALIASES.get(view_name, view_name)
    if resolved not in _VIEW_NAMES:
        abort(404)
    if resolved in _TESTLAB_VIEWS:
        # 旧 12 画面は /test-automation に統合済み。権限判定は移送先で行う。
        # ここでも 403 を出すと判定が 2 箇所に散り、片方だけ直し忘れる。
        return redirect("/test-automation")
    # 実際の画面切替はクライアント側の switchView() が location.pathname を見て行う。
    return render_template("index.html")
