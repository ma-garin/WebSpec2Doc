"""Prometheus のスクレイプ先 `/metrics`。

Prometheus の慣行に従いルート直下へ置く（exporter は既定で /metrics を見る）。
公開するのは本プロセスが観測した値のみで、対象サイトの品質は含まない。
"""

from __future__ import annotations

from flask import Blueprint, Response

bp = Blueprint("metrics", __name__)


@bp.get("/metrics")
def metrics() -> Response:
    """Prometheus 形式のメトリクスを返す。"""
    from web.services.metrics import render_metrics

    body, content_type = render_metrics()
    return Response(body, mimetype=content_type)
