"""crawler.session_guard のユニットテスト（#7）"""
from __future__ import annotations

from pathlib import Path

from analyzer.login_wall import PageAuthSignals
from crawler.session_guard import is_session_expired


def _signals(**kw) -> PageAuthSignals:
    base = dict(
        requested_url="https://example.com/dashboard",
        final_url="https://example.com/dashboard",
        status=200,
        has_password_field=False,
    )
    base.update(kw)
    return PageAuthSignals(**base)


def test_not_expired_without_auth_state() -> None:
    assert is_session_expired(None, _signals(status=401)) is False


def test_expired_when_auth_present_and_login_wall() -> None:
    assert is_session_expired(Path("/tmp/auth.json"), _signals(status=401)) is True


def test_not_expired_when_auth_present_and_public_page() -> None:
    assert is_session_expired(Path("/tmp/auth.json"), _signals()) is False
