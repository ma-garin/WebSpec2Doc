from __future__ import annotations

import os
from urllib.parse import urlparse

from flask import Response, request

# 社内サーバ展開用: 追加で許可するホストをカンマ区切りで指定する。
# 既定（未設定）はローカルループバックのみ許可＝現行のセキュリティ態勢を維持。
TRUSTED_HOSTS_ENV = "WEBSPEC2DOC_TRUSTED_HOSTS"

# localhost 専用ツールとして実用的な CSP。
# 'unsafe-inline' は生成済み report.html (Mermaid 初期化インラインスクリプト) のため必要。
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "frame-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'"
)

_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "same-origin",
    "Content-Security-Policy": _CSP,
}

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _trusted_hosts() -> frozenset[str]:
    """許可ホスト集合を返す（ローカルループバック ＋ 環境変数の追加ホスト）。

    WEBSPEC2DOC_TRUSTED_HOSTS が未設定なら現行どおりローカルのみ許可する。
    社内サーバへ展開する場合のみ、そのホスト名／IP をカンマ区切りで追加する。
    """
    raw = os.environ.get(TRUSTED_HOSTS_ENV, "")
    extra = {host.strip().lower() for host in raw.split(",") if host.strip()}
    return _LOCAL_HOSTS | extra


def add_security_headers(response: Response) -> Response:
    """全レスポンスにセキュリティヘッダーを付与する。"""
    for key, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(key, value)
    return response


def _host_matches(header_val: str, expected_host: str) -> bool:
    """Origin / Referer ヘッダーのホスト部分が expected_host と完全一致するか検証する。
    サブストリング一致（攻撃者ドメインが victim を含む場合）を防ぐため exact match にする。"""
    try:
        netloc = urlparse(header_val).netloc
        return netloc == expected_host
    except Exception:
        return False


def localhost_guard() -> Response | None:
    """Host ヘッダーが許可ホスト（ローカル＋TRUSTED_HOSTS）を指す場合のみ許可する。

    既定ではローカルループバックのみ許可。社内サーバ展開時は
    WEBSPEC2DOC_TRUSTED_HOSTS で許可ホストを明示的に追加する。
    """
    try:
        hostname = urlparse(f"//{request.host}").hostname
    except ValueError:
        hostname = None
    allowed = _trusted_hosts()
    if hostname is None or hostname.lower() not in allowed:
        return Response(status=403)
    return None


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
        if origin == "null" or not _host_matches(origin, host):
            return Response(status=403)
        return None
    if referer:
        if not _host_matches(referer, host):
            return Response(status=403)
    return None
