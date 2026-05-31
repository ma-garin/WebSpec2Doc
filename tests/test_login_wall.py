"""analyzer.login_wall.detect_login_wall のユニットテスト"""

from __future__ import annotations

from analyzer.login_wall import (
    REASON_FORBIDDEN,
    REASON_PASSWORD_FIELD,
    REASON_REDIRECT_TO_LOGIN,
    PageAuthSignals,
    detect_login_wall,
)


def _signals(**kw) -> PageAuthSignals:
    base = dict(
        requested_url="https://example.com/dashboard",
        final_url="https://example.com/dashboard",
        status=200,
        has_password_field=False,
    )
    base.update(kw)
    return PageAuthSignals(**base)


class TestDetectLoginWall:
    def test_http_401_is_login_required(self) -> None:
        verdict = detect_login_wall(_signals(status=401))
        assert verdict.is_login_required
        assert REASON_FORBIDDEN in verdict.reasons

    def test_http_403_is_login_required(self) -> None:
        verdict = detect_login_wall(_signals(status=403))
        assert verdict.is_login_required
        assert REASON_FORBIDDEN in verdict.reasons

    def test_redirect_to_login_url_is_login_required(self) -> None:
        verdict = detect_login_wall(
            _signals(
                requested_url="https://example.com/dashboard",
                final_url="https://example.com/login?next=/dashboard",
            )
        )
        assert verdict.is_login_required
        assert REASON_REDIRECT_TO_LOGIN in verdict.reasons

    def test_password_field_is_login_required(self) -> None:
        verdict = detect_login_wall(_signals(has_password_field=True))
        assert verdict.is_login_required
        assert REASON_PASSWORD_FIELD in verdict.reasons

    def test_public_page_is_not_login_required(self) -> None:
        verdict = detect_login_wall(_signals())
        assert not verdict.is_login_required
        assert verdict.reasons == ()

    def test_public_url_with_login_substring_not_redirect(self) -> None:
        # 「同URLのまま」かつログイン語を含まない通常ページは誤検知しない
        verdict = detect_login_wall(
            _signals(
                requested_url="https://example.com/blog/authentication-guide",
                final_url="https://example.com/blog/authentication-guide",
            )
        )
        assert not verdict.is_login_required

    def test_multiple_signals_are_all_reported(self) -> None:
        verdict = detect_login_wall(_signals(status=403, has_password_field=True))
        assert verdict.is_login_required
        assert REASON_FORBIDDEN in verdict.reasons
        assert REASON_PASSWORD_FIELD in verdict.reasons

    def test_login_page_reached_directly_has_no_redirect_reason(self) -> None:
        verdict = detect_login_wall(
            _signals(
                requested_url="https://example.com/login",
                final_url="https://example.com/login",
                has_password_field=True,
            )
        )
        assert verdict.is_login_required
        assert REASON_PASSWORD_FIELD in verdict.reasons
        assert REASON_REDIRECT_TO_LOGIN not in verdict.reasons
