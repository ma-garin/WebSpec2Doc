from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

ALLOWED_SCHEMES = frozenset({"http", "https"})
LOCAL_HOSTNAMES = frozenset({"localhost", "ip6-localhost", "ip6-loopback"})
LOCAL_SUFFIXES = (".local", ".localhost", ".internal")


class UnsafeUrlError(ValueError):
    """クロール対象として許可されない URL。"""


def validate_target_url(url: str) -> None:
    """SSRF / file:// 等を防ぐため、クロール対象 URL を検証する。

    http/https 以外、localhost 系ホスト、プライベート/予約済み IP リテラルを拒否する。
    問題があれば ``UnsafeUrlError`` を送出する。
    """
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"http/https の URL のみ対応しています: {url!r}")

    host = (parsed.hostname or "").lower()
    if not host:
        raise UnsafeUrlError(f"ホスト名が取得できません: {url!r}")

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
