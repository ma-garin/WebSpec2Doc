from __future__ import annotations

from urllib.parse import urlparse

from flask import Response, request


def _host_matches(header_val: str, expected_host: str) -> bool:
    """Origin / Referer ヘッダーのホスト部分が expected_host と完全一致するか検証する。
    サブストリング一致（攻撃者ドメインが victim を含む場合）を防ぐため exact match にする。"""
    try:
        netloc = urlparse(header_val).netloc
        return netloc == expected_host
    except Exception:
        return False


def csrf_guard() -> Response | None:
    """状態変更リクエスト（POST/PUT/PATCH/DELETE）は同一オリジンのみ許可。
    Origin が存在する場合は Origin で検証、存在しない場合は Referer で検証する。
    どちらも存在しない場合は curl/CLI 等のノンブラウザ利用として許可する。"""
    if request.method in ("GET", "HEAD", "OPTIONS", "TRACE"):
        return None
    origin = request.headers.get("Origin", "").strip()
    referer = request.headers.get("Referer", "").strip()
    host = request.host
    if origin:
        # "null" は file:// や opaque オリジンで発生する — このツールでは拒否しない
        if origin != "null" and not _host_matches(origin, host):
            return Response(status=403)
        return None
    if referer:
        if not _host_matches(referer, host):
            return Response(status=403)
    return None
