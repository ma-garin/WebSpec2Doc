from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse

ALLOWED_SCHEMES = frozenset({"http", "https"})
LOCAL_HOSTNAMES = frozenset({"localhost", "ip6-localhost", "ip6-loopback"})
LOCAL_SUFFIXES = (".local", ".localhost", ".internal")
ALLOW_LOCAL_ENV = "WEBSPEC2DOC_ALLOW_LOCAL"


class UnsafeUrlError(ValueError):
    """クロール対象として許可されない URL。"""


def domain_key_from_url(url: str) -> str:
    """JS の ``URL.host`` と一致する、出力ディレクトリ用のホストキーを返す。"""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if not host:
        return parsed.path.replace("/", "_") or "site"
    if ":" in host:
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        port = None
    default_port = (parsed.scheme.lower(), port) in {("http", 80), ("https", 443)}
    return f"{host}:{port}" if port is not None and not default_port else host


def _local_targets_allowed() -> bool:
    """ローカル/プライベートアドレスのクロールを許可するか（opt-in）。

    社内ステージング環境や開発環境のクロールに使う。
    環境変数 WEBSPEC2DOC_ALLOW_LOCAL=1 で有効化（既定は無効＝SSRF保護優先）。
    """
    return os.environ.get(ALLOW_LOCAL_ENV, "") == "1"


def validate_target_url(url: str) -> None:
    """SSRF / file:// 等を防ぐため、クロール対象 URL を検証する。

    http/https 以外、localhost 系ホスト、プライベート/予約済み IP リテラルを拒否する。
    問題があれば ``UnsafeUrlError`` を送出する。
    WEBSPEC2DOC_ALLOW_LOCAL=1 が設定されている場合のみローカル対象を許可する。
    """
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"http/https の URL のみ対応しています: {url!r}")

    host = (parsed.hostname or "").lower()
    if not host:
        raise UnsafeUrlError(f"ホスト名が取得できません: {url!r}")

    if _local_targets_allowed():
        return

    if host in LOCAL_HOSTNAMES or host.endswith(LOCAL_SUFFIXES):
        raise UnsafeUrlError(f"ローカルホストへのアクセスは禁止です: {host}")

    ip = _as_ip_address(host)
    if ip is not None and not ip.is_global:
        raise UnsafeUrlError(f"プライベート/予約済みアドレスへのアクセスは禁止です: {host}")


def is_safe_target(url: str) -> bool:
    """``validate_target_url`` が通る URL かどうかを真偽値で返す。"""
    try:
        validate_target_url(url)
    except UnsafeUrlError:
        return False
    return True


def _as_ip_address(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None
