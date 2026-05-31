from __future__ import annotations

from flask import Response, request


def csrf_guard() -> Response | None:
    """状態変更(POST)は同一オリジンのみ許可。ブラウザに開かれた悪意ページからの
    localhost への cross-site POST を防ぐ簡易CSRF対策。"""
    if request.method != "POST":
        return None
    origin = request.headers.get("Origin") or request.headers.get("Referer") or ""
    if origin and request.host not in origin:
        return Response(status=403)
    return None
