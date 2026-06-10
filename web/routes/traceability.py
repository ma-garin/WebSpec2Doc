from __future__ import annotations

import json
import logging

from flask import Blueprint, render_template, request

from web.config import OUTPUT_DIR
from web.services.traceability import build_matrix, matrix_to_dict
from web.validation import _valid_domain

logger = logging.getLogger(__name__)

traceability_bp = Blueprint("traceability", __name__)

_REPORT_JSON = "report.json"
_CANDIDATES_JSON = "playwright_candidates.json"


def _load_json_file(path_obj) -> dict | list | None:
    """JSON ファイルを読み込む。失敗時は None を返す。"""
    try:
        return json.loads(path_obj.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("JSON 読み込みに失敗: %s — %s", path_obj, exc)
        return None


@traceability_bp.get("/traceability/matrix")
def api_traceability_matrix() -> tuple[dict, int] | dict:
    """report.json + playwright_candidates.json を読んで TraceabilityMatrix を返す。"""
    domain = request.args.get("domain", "").strip()
    if not domain or not _valid_domain(domain):
        return {"error": "invalid domain"}, 400

    domain_dir = OUTPUT_DIR / domain
    report_path = domain_dir / _REPORT_JSON
    candidates_path = domain_dir / _CANDIDATES_JSON

    if not report_path.is_file():
        return {"error": "report.json not found"}, 404

    report_data = _load_json_file(report_path)
    if report_data is None:
        return {"error": "report.json の読み込みに失敗しました"}, 500

    candidates_raw = None
    if candidates_path.is_file():
        candidates_raw = _load_json_file(candidates_path)

    candidates: list[dict] = []
    if isinstance(candidates_raw, dict):
        candidates = list(candidates_raw.get("candidates", []))
    elif isinstance(candidates_raw, list):
        candidates = list(candidates_raw)

    report_dict: dict = report_data if isinstance(report_data, dict) else {}
    matrix = build_matrix(domain, report_dict, candidates)
    return matrix_to_dict(matrix)


@traceability_bp.get("/traceability/view")
def view_traceability() -> str:
    """トレーサビリティマトリクスビューをレンダリングする。"""
    domain = request.args.get("domain", "").strip()
    return render_template("partials/view-traceability.html", domain=domain)
