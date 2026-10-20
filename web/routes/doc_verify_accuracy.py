"""System 06 R5: 精度ページの API（FR-06-172・SCR-06-10）。

GET /api/docverify/accuracy … 規則別の適合率・再現率・n・測定日・限界。未測定は「未測定」。
中身は web/services/docverify/accuracy.py。測定は scripts/docverify_eval.py で行う。
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify

bp = Blueprint("doc_verify_accuracy", __name__)
log = logging.getLogger(__name__)


@bp.route("/api/docverify/accuracy", methods=["GET"])
def accuracy():
    from web.services.docverify import accuracy as acc
    try:
        return jsonify(acc.page())
    except ValueError as e:
        return jsonify(error=str(e)), 500
    except Exception:  # noqa: BLE001  詳細はログだけに出す
        log.exception("docverify accuracy page failed")
        return jsonify(error="精度を読めませんでした。時間をおいて再読み込みしてください。"), 500
