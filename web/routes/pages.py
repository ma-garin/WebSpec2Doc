from __future__ import annotations

from flask import Blueprint, render_template

bp = Blueprint("pages", __name__)


@bp.route("/")
def index() -> str:
    return render_template("index.html")
