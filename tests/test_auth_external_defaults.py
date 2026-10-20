"""外部公開構成（TRUSTED_HOSTS 設定時）は、未設定の認証設定を安全側に倒す。"""
from web import auth


def test_external_defaults_are_fail_safe(monkeypatch) -> None:
    monkeypatch.setenv("WEBSPEC2DOC_TRUSTED_HOSTS", "ws2d.example.com")
    monkeypatch.delenv(auth.AUTH_MODE_ENV, raising=False)
    monkeypatch.delenv(auth.AUTH_MOCK_ENV, raising=False)
    assert auth.effective_auth_mode() == "required"
    assert auth.mock_auth_enabled() is False


def test_explicit_settings_win_when_external(monkeypatch) -> None:
    monkeypatch.setenv("WEBSPEC2DOC_TRUSTED_HOSTS", "ws2d.example.com")
    monkeypatch.setenv(auth.AUTH_MODE_ENV, "auto")
    monkeypatch.setenv(auth.AUTH_MOCK_ENV, "1")
    assert auth.effective_auth_mode() == "auto"
    assert auth.mock_auth_enabled() is True


def test_local_defaults_unchanged(monkeypatch) -> None:
    monkeypatch.delenv("WEBSPEC2DOC_TRUSTED_HOSTS", raising=False)
    monkeypatch.delenv(auth.AUTH_MODE_ENV, raising=False)
    monkeypatch.delenv(auth.AUTH_MOCK_ENV, raising=False)
    assert auth.effective_auth_mode() == "auto"
    assert auth.mock_auth_enabled() is True
