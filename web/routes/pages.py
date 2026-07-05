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
        "settings",
    }
)
_VIEW_ALIASES = {"home": "dashboard"}


@bp.route("/")
def index() -> str:
    return render_template("index.html")


@bp.route("/<view_name>")
def view(view_name: str) -> str:
    resolved = _VIEW_ALIASES.get(view_name, view_name)
    if resolved not in _VIEW_NAMES:
        abort(404)
    # 実際の画面切替はクライアント側の switchView() が location.pathname を見て行う。
    return render_template("index.html")
