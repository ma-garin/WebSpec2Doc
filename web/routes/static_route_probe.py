"""静的 route 候補の到達確認（System 03）の API。

POST /api/sites/<domain>/static-routes/probe  GET の遷移だけで候補を開く（同期・サイト単位で二重実行不可）
GET  /api/sites/<domain>/static-routes/probe  直近の到達確認の結果（現在のリバース解析結果に対するものだけ）
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app

from web.config import OUTPUT_DIR
from web.routes.reverse_analysis import site_evidence
from web.services import static_route_probe as probe
from web.tenancy import scoped_output_dir
from web.validation import _valid_domain

bp = Blueprint("static_route_probe", __name__)

_HTTP = {"success": 200, "busy": 409, "no_rea": 422, "error": 500}
_BAD = {"message": "サイトの指定が正しくありません。", "next_action": "サイト一覧から開き直してください。"}


def _base() -> Path:
    return scoped_output_dir(OUTPUT_DIR)


@bp.post("/api/sites/<domain>/static-routes/probe")
def api_static_route_probe_run(domain: str) -> tuple[dict, int]:
    if not _valid_domain(domain):
        return {"result": "error", **_BAD}, 404
    try:
        res = probe.run_probe(_base(), domain, site_evidence(domain))
    except Exception as exc:  # noqa: BLE001
        current_app.logger.warning("static_route_probe の実行に失敗: %s (%s)", domain, type(exc).__name__)
        res = probe.ProbeRun("error", "到達確認を完了できませんでした。結果は更新していません。",
                             "時間をおいて再実行してください。")  # fmt: skip
    return {"result": res.result, "message": res.message, "next_action": res.next_action}, _HTTP[res.result]


@bp.get("/api/sites/<domain>/static-routes/probe")
def api_static_route_probe_status(domain: str) -> tuple[dict, int] | dict:
    if not _valid_domain(domain):
        return {"state": "error", **_BAD}, 400
    try:
        return probe.build_status(_base(), domain, site_evidence(domain))
    except Exception as exc:  # noqa: BLE001
        current_app.logger.warning("static_route_probe の読み込みに失敗: %s (%s)", domain, type(exc).__name__)
        return {"state": "error", "message": "到達確認の結果を読み込めませんでした。",
                "next_action": "到達確認を再実行してください。"}, 500  # fmt: skip
