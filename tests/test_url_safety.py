from __future__ import annotations

import pytest

from crawler.url_safety import (
    UnsafeUrlError,
    domain_key_from_url,
    is_safe_target,
    validate_target_url,
)

SAFE_URLS = [
    "https://example.com",
    "http://example.com/path?q=1",
    "https://www.veriserve.co.jp/services/",
    "https://sub.example.co.jp",
]

UNSAFE_URLS = [
    "file:///etc/passwd",
    "javascript:alert(1)",
    "ftp://example.com",
    "http://localhost:8000",
    "https://localhost",
    "http://127.0.0.1/admin",
    "http://169.254.169.254/latest/meta-data/",
    "http://192.168.1.1",
    "http://10.0.0.5:8080",
    "http://[::1]/",
    "http://printer.local",
    "https://app.internal",
    "https://",
    "not-a-url",
]


@pytest.mark.parametrize("url", SAFE_URLS)
def test_safe_urls_pass(url: str) -> None:
    validate_target_url(url)  # 例外が出なければ OK
    assert is_safe_target(url) is True


@pytest.mark.parametrize("url", UNSAFE_URLS)
def test_unsafe_urls_rejected(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        validate_target_url(url)
    assert is_safe_target(url) is False


def test_allow_local_env_permits_private_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    """WEBSPEC2DOC_ALLOW_LOCAL=1 でローカル/プライベートアドレスを許可（ステージング環境用）。"""
    monkeypatch.setenv("WEBSPEC2DOC_ALLOW_LOCAL", "1")
    validate_target_url("http://127.0.0.1:8899/index.html")
    validate_target_url("http://localhost:3000")
    validate_target_url("http://10.0.0.5:8080")
    assert is_safe_target("http://192.168.1.10/") is True


def test_allow_local_env_still_rejects_bad_schemes(monkeypatch: pytest.MonkeyPatch) -> None:
    """許可モードでも http/https 以外のスキームは拒否する。"""
    monkeypatch.setenv("WEBSPEC2DOC_ALLOW_LOCAL", "1")
    with pytest.raises(UnsafeUrlError):
        validate_target_url("file:///etc/passwd")


def test_local_rejected_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """環境変数なし（既定）ではローカルを拒否する（SSRF保護）。"""
    monkeypatch.delenv("WEBSPEC2DOC_ALLOW_LOCAL", raising=False)
    with pytest.raises(UnsafeUrlError):
        validate_target_url("http://127.0.0.1:8899/")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://EXAMPLE.COM:443/path", "example.com"),
        ("http://example.com:8080/path", "example.com:8080"),
        ("http://[::1]:8080/path", "[::1]:8080"),
    ],
)
def test_domain_key_matches_browser_url_host(url: str, expected: str) -> None:
    assert domain_key_from_url(url) == expected


def test_hostname_resolving_to_private_ip_is_rejected(monkeypatch) -> None:
    import socket

    from crawler import url_safety

    monkeypatch.delenv(url_safety.ALLOW_LOCAL_ENV, raising=False)
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("169.254.169.254", 0))]
    )
    with pytest.raises(url_safety.UnsafeUrlError):
        url_safety.validate_target_url("http://metadata.attacker.example/")


def test_redirect_to_private_ip_is_rejected(monkeypatch) -> None:
    from crawler import url_safety

    monkeypatch.delenv(url_safety.ALLOW_LOCAL_ENV, raising=False)
    handler = url_safety._ValidatingRedirectHandler()
    with pytest.raises(url_safety.UnsafeUrlError):
        handler.redirect_request(None, None, 302, "Found", {}, "http://127.0.0.1/admin")


def test_link_checker_does_not_open_private_targets(monkeypatch) -> None:
    from crawler import url_safety
    from diff.link_checker import STATUS_UNCONFIRMED, check_link

    monkeypatch.delenv(url_safety.ALLOW_LOCAL_ENV, raising=False)
    result = check_link("http://10.0.0.1/secret", "P001", sleeper=lambda _s: None)
    assert result.status == STATUS_UNCONFIRMED
    assert "安全でない宛先" in result.reason


def test_notifier_rejects_private_webhook(monkeypatch) -> None:
    from web.services import notifier

    from crawler import url_safety

    monkeypatch.delenv(url_safety.ALLOW_LOCAL_ENV, raising=False)
    assert notifier._post_json("http://192.168.0.10/hook", {"text": "x"}) is False
