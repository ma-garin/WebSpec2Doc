"""状態 9 種・通知の検証ページ（開発時のみ）。

認証オフ（WEBSPEC2DOC_AUTH_MODE=off）のときだけ /dev/states を返し、それ以外は 404。
本番の利用者には存在しない画面として扱う。
"""
from __future__ import annotations

from flask import Blueprint, abort, render_template, request

from web.auth import effective_auth_mode

bp = Blueprint("dev_states", __name__)

STATES = ("normal", "empty", "no-match", "loading", "error", "forbidden", "dirty", "conflict", "restored")


@bp.get("/dev/states")
def states_demo():
    if effective_auth_mode() != "off":
        abort(404)
    state = request.args.get("state", "normal")
    if state not in STATES:
        state = "normal"
    return render_template("_states_demo.html", initial_state=state, states=STATES)
