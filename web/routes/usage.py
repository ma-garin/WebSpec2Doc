"""ROI ダッシュボード: 利用実績と推定削減工数を表示する。

/api/usage        累計実績・推定削減工数（時間・円）を JSON で返す
/usage            ダッシュボードビュー（HTML）
"""

from __future__ import annotations

from flask import Blueprint, render_template

from web.config import OUTPUT_DIR
from web.services.usage_tracker import load_usage, summarize_usage
from web.tenancy import scoped_output_dir

bp = Blueprint("usage", __name__)


@bp.get("/api/usage")
def api_usage() -> dict:
    """累計利用実績と推定削減工数（ROI）を返す。"""
    records = load_usage(scoped_output_dir(OUTPUT_DIR))
    summary = summarize_usage(records)
    summary["record_count"] = len(records)
    return summary


@bp.get("/usage")
def view_usage() -> str:
    """ROI ダッシュボードビューをレンダリングする。"""
    return render_template("partials/view-usage.html")
