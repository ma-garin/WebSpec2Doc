from __future__ import annotations

import json

from flask import Blueprint, Response, request

from web.config import MAX_DEPTH, MAX_PAGES_LIMIT
from web.services.fast_discover import discover_pages_fast, stream_discovery_events
from web.validation import _clean_int, _safe_auth_path

bp = Blueprint("discover", __name__)


@bp.post("/api/discover")
def api_discover() -> Response | tuple[dict, int] | dict:
    url = request.form.get("url", "").strip()
    depth = _clean_int(request.form.get("depth", "2"), 2, 1, MAX_DEPTH)
    max_pages = _clean_int(request.form.get("max_pages", "30"), 30, 1, MAX_PAGES_LIMIT)
    auth = _safe_auth_path(request.form.get("auth", "").strip())
    if not url:
        return {"pages": [], "error": "URLを入力してください"}, 400

    try:
        pages = discover_pages_fast(
            url=url,
            depth=depth,
            max_pages=max_pages,
            auth_state=str(auth) if auth else None,
        )
    except Exception as exc:
        return {"pages": [], "error": f"画面リスト取得に失敗しました: {exc}"}, 500
    return {"pages": pages}


@bp.post("/api/discover-stream")
def api_discover_stream() -> Response | tuple[dict, int]:
    """発見ページを SSE（text/event-stream）でリアルタイム配信する。"""
    url = request.form.get("url", "").strip()
    depth = _clean_int(request.form.get("depth", "2"), 2, 1, MAX_DEPTH)
    max_pages = _clean_int(request.form.get("max_pages", "30"), 30, 1, MAX_PAGES_LIMIT)
    auth = _safe_auth_path(request.form.get("auth", "").strip())
    if not url:
        return {"error": "URLを入力してください"}, 400

    def generate():
        try:
            yield from stream_discovery_events(
                url=url,
                depth=depth,
                max_pages=max_pages,
                auth_state=str(auth) if auth else None,
            )
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
