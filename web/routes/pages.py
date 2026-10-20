from __future__ import annotations

from flask import Blueprint, Response, abort, redirect, render_template

bp = Blueprint("pages", __name__)

# 統合ワークスペース（workspace.html）のワークスペース名。
# URL は /sites/<domain>/<ws> の 1 系統だけで、レール・パネルの初期表示を <body data-ws> で決める。
_WS = frozenset({"spec", "tests", "changes", "schedule", "report", "team"})

# 旧シェル（index.html）に残っている画面（templates/partials/nav.html の data-view と対応）。
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
        # テスト自動化（System 02）の旧 12 画面。/test-automation 経由でホームへ 302 で送る。
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

# テスト自動化（System 02）の旧画面。中身は統合ワークスペースに移ったため、
# ここに載っている名前はすべて /test-automation へ 302 で送るだけになる
# （/test-automation 自身も domain 付きなら /sites/<domain>/tests、無ければ / へ 302）。
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


def _forbidden_page() -> tuple[str, int]:
    """素の 403 を出さず、理由と次の行動を書いた画面を返す（ステータスは 403 のまま）。"""
    return render_template("forbidden.html"), 403


@bp.route("/")
def index() -> Response:
    """ドキュメント作成（System 01）の入口。実体は /dashboard に一本化する。
    / と /dashboard が同じ画面を返していると、URL とビューが 1:1 にならず
    ブラウザの戻る・ブックマークが壊れる。"""
    return redirect("/dashboard")


@bp.route("/team")
def team() -> str:
    """チーム（メンバー・API トークン）。

    ワークスペース全体の設定であってサイトには属さない。サイトを 1 件も
    持たないテナントでも同僚を招けるよう、サイト無しで開ける経路を持たせる。
    """
    return render_template("workspace.html", ws="team", domain="", mode="full")


@bp.route("/sites/<domain>")
def site_root(domain: str) -> Response:
    """サイトの入口。主役の価値は仕様なので、既定で仕様ワークスペースへ送る。"""
    return redirect(f"/sites/{domain}/spec")


@bp.route("/sites/<domain>/<ws>")
def site_workspace(domain: str, ws: str) -> str | Response:
    """サイト単位のワークスペース（仕様 / テスト / 変更 / 定期実行 / 報告 / チーム）。

    未解析のドメインをここで開いても見せるものが無いため、ホームへ戻して
    「URL を入れる」導線に着地させる（404 にすると行き止まりになる）。
    """
    from web.config import OUTPUT_DIR
    from web.tenancy import scoped_output_dir
    from web.validation import _valid_domain

    if ws not in _WS:
        abort(404)
    if not _valid_domain(domain):
        abort(404)
    if not _may_use_testlab():
        # 存在は隠さず 403 にする。404 にすると権限の問題か綴り違いか切り分けられない。
        return _forbidden_page()
    if not (scoped_output_dir(OUTPUT_DIR) / domain / "report.json").is_file():
        return redirect("/")
    return render_template("workspace.html", ws=ws, domain=domain, mode="full")


@bp.route("/test-automation")
def test_automation() -> str:
    """テスト自動化単体モード。統合ワークスペースをテスト系パネルだけに絞って開く。"""
    if not _may_use_testlab():
        # /sites/<domain>/* と同じ。画面骨格に入れてから中の API で初めて拒否される不揃いを避ける。
        return _forbidden_page()
    return render_template("workspace.html", ws="home", domain="", mode="test-only")


@bp.route("/systems")
def systems() -> str:
    """システム選択ハブ。ドキュメント作成／テスト自動化のどちらを開くか選ばせる。"""
    return render_template("system-select.html")


@bp.route("/doc-app")
def doc_app() -> str:
    """ドキュメント作成(app)。System 01 をスマホアプリ（APK / .app）向けに特化した入口。

    画面はドキュメント作成そのもの（index.html: 解析 → 条件設定 → 実行 → レポート）を共用し、
    ステップ 1 の入力だけをアプリ向けに差し替える（app_mode）。対象は ``https://app.<package>``
    という擬似 URL で流し、サーバ側（web/services/app_mock.py）がモック実行に切り替える。
    """
    return render_template("index.html", app_mode=True)


@bp.route("/cli")
def cli_mode() -> str:
    """CLI モード（System 04。番号の正本は web/system_registry.py）の案内。

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
    if view_name == "home":
        # 旧ホーム（ダッシュボード）は統合ワークスペースのホームに置き換わった。
        return redirect("/")
    if view_name not in _VIEW_NAMES:
        abort(404)
    if view_name in _TESTLAB_VIEWS:
        # 旧 12 画面は /test-automation に統合済み。権限判定は移送先で行う。
        # ここでも 403 を出すと判定が 2 箇所に散り、片方だけ直し忘れる。
        return redirect("/test-automation")
    # 実際の画面切替はクライアント側の switchView() が location.pathname を見て行う。
    return render_template("index.html")
