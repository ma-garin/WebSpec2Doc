from __future__ import annotations

import ipaddress
import os
import socket
import urllib.request
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

    # 公開名がプライベート IP に解決される DNS 経由の SSRF（169.254.169.254 等）を防ぐ。
    # 解決できない名前は到達不能なので通す（実行時に接続失敗になる）。
    for resolved in _resolve_host(host):
        if not resolved.is_global:
            raise UnsafeUrlError(f"プライベート/予約済みアドレスに解決されるホストは禁止です: {host}")


def is_local_target(url_or_host: str) -> bool:
    """ループバック / プライベート / ローカル名前空間のホストかどうかを返す。

    ``validate_target_url`` がローカル判定に使う条件と同じものを、
    許可/拒否の判断とは切り離して真偽値で返す。URL でもホスト単体でも受ける。
    """
    raw = (url_or_host or "").strip()
    if not raw:
        return False
    parsed = urlparse(raw if "//" in raw else f"//{raw}")
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host in LOCAL_HOSTNAMES or host.endswith(LOCAL_SUFFIXES):
        return True
    ip = _as_ip_address(host)
    return ip is not None and not ip.is_global


def local_targets_allowed() -> bool:
    """ローカル対象のクロールが opt-in で許可されているか。"""
    return _local_targets_allowed()


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


def _resolve_host(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    if _as_ip_address(host) is not None:
        return []
    try:
        infos = socket.getaddrinfo(host, None)
    except (OSError, UnicodeError):
        return []
    addresses = []
    for info in infos:
        candidate = _as_ip_address(str(info[4][0]).split("%", 1)[0])
        if candidate is not None:
            addresses.append(candidate)
    return addresses


class _ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """リダイレクト先も ``validate_target_url`` で検証する（公開 URL → 内部への転送を防ぐ）。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        validate_target_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def safe_urlopen(request: urllib.request.Request | str, timeout: float):  # type: ignore[no-untyped-def]
    """宛先とリダイレクト先を検証してから開く ``urlopen``。不正なら ``UnsafeUrlError``。"""
    url = request.full_url if isinstance(request, urllib.request.Request) else request
    validate_target_url(url)
    opener = urllib.request.build_opener(_ValidatingRedirectHandler())
    return opener.open(request, timeout=timeout)  # nosec B310  # noqa: S310
