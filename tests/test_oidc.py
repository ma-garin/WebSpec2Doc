"""SSO（OIDC）とAPIトークンスコープの契約。

守るべきは「検証を省略しないこと」。issuer / audience / nonce / state のどれかを
素通しにすると、他人のトークンでログインできてしまう。
"""

from __future__ import annotations

import pytest
from web.services.oidc import (
    DEFAULT_SCOPES,
    PROVIDER_ENTRA,
    PROVIDER_GOOGLE,
    OidcConfig,
    OidcError,
    build_authorization_url,
    extract_identity,
    load_config,
    new_state,
    oidc_enabled,
    verify_state,
)


def _config(**kwargs) -> OidcConfig:
    base = {
        "provider": PROVIDER_ENTRA,
        "client_id": "client-123",
        "client_secret": "secret",
        "issuer": "https://login.microsoftonline.com/tid/v2.0",
        "redirect_uri": "https://app.example.com/auth/oidc/callback",
    }
    return OidcConfig(**{**base, **kwargs})


def _token(**claims) -> dict:
    base = {
        "iss": "https://login.microsoftonline.com/tid/v2.0",
        "aud": "client-123",
        "nonce": "n-1",
        "sub": "user-sub",
    }
    return {"id_token_claims": {**base, **claims}}


# ─────────────────── 設定 ───────────────────


def test_disabled_when_provider_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEBSPEC2DOC_OIDC_PROVIDER", raising=False)

    assert oidc_enabled() is False


def test_unsupported_provider_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBSPEC2DOC_OIDC_PROVIDER", "okta")

    with pytest.raises(OidcError, match="未対応のSSOプロバイダ"):
        load_config()


def test_missing_credentials_are_reported_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBSPEC2DOC_OIDC_PROVIDER", PROVIDER_GOOGLE)
    monkeypatch.delenv("WEBSPEC2DOC_OIDC_CLIENT_ID", raising=False)
    monkeypatch.delenv("WEBSPEC2DOC_OIDC_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("WEBSPEC2DOC_OIDC_REDIRECT_URI", raising=False)

    with pytest.raises(OidcError, match="WEBSPEC2DOC_OIDC_CLIENT_ID"):
        load_config()


def test_entra_issuer_is_built_from_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {
        "WEBSPEC2DOC_OIDC_PROVIDER": PROVIDER_ENTRA,
        "WEBSPEC2DOC_OIDC_CLIENT_ID": "c",
        "WEBSPEC2DOC_OIDC_CLIENT_SECRET": "s",
        "WEBSPEC2DOC_OIDC_REDIRECT_URI": "https://app/cb",
        "WEBSPEC2DOC_OIDC_TENANT": "contoso",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("WEBSPEC2DOC_OIDC_ISSUER", raising=False)

    assert load_config().issuer == "https://login.microsoftonline.com/contoso/v2.0"


def test_auto_provision_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {
        "WEBSPEC2DOC_OIDC_PROVIDER": PROVIDER_GOOGLE,
        "WEBSPEC2DOC_OIDC_CLIENT_ID": "c",
        "WEBSPEC2DOC_OIDC_CLIENT_SECRET": "s",
        "WEBSPEC2DOC_OIDC_REDIRECT_URI": "https://app/cb",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("WEBSPEC2DOC_OIDC_AUTO_PROVISION", raising=False)

    assert load_config().auto_provision is False


# ─────────────────── 認可要求 ───────────────────


def test_authorization_url_carries_state_and_nonce() -> None:
    url = build_authorization_url(_config(), state="st-1", nonce="n-1")

    assert url.startswith("https://login.microsoftonline.com/tid/v2.0/authorize?")
    assert "state=st-1" in url
    assert "nonce=n-1" in url
    assert "response_type=code" in url
    assert "scope=openid+email+profile" in url


def test_google_uses_its_own_endpoints() -> None:
    config = _config(provider=PROVIDER_GOOGLE, issuer="https://accounts.google.com")

    assert config.authorization_endpoint.startswith("https://accounts.google.com/o/oauth2")
    assert config.token_endpoint == "https://oauth2.googleapis.com/token"


def test_default_scopes_request_openid_email_profile() -> None:
    assert _config().scopes == DEFAULT_SCOPES


def test_state_values_are_unique() -> None:
    assert new_state() != new_state()


def test_state_mismatch_is_rejected() -> None:
    with pytest.raises(OidcError, match="照合に失敗"):
        verify_state("expected", "tampered")


def test_empty_state_is_rejected() -> None:
    with pytest.raises(OidcError):
        verify_state("", "")


# ─────────────────── ID トークン検証 ───────────────────


def test_valid_token_yields_identity() -> None:
    identity = extract_identity(
        _config(), _token(), {"email": "User@Example.com", "name": "利用者"}, "n-1"
    )

    assert identity == {"email": "user@example.com", "name": "利用者", "subject": "user-sub"}


def test_missing_id_token_claims_is_rejected() -> None:
    with pytest.raises(OidcError, match="IDトークンを検証できません"):
        extract_identity(_config(), {}, {"email": "a@b.com"}, "n-1")


def test_wrong_issuer_is_rejected() -> None:
    with pytest.raises(OidcError, match="発行者"):
        extract_identity(
            _config(), _token(iss="https://evil.example.com"), {"email": "a@b.com"}, "n-1"
        )


def test_wrong_audience_is_rejected() -> None:
    with pytest.raises(OidcError, match="宛先"):
        extract_identity(_config(), _token(aud="other-client"), {"email": "a@b.com"}, "n-1")


def test_audience_list_containing_client_is_accepted() -> None:
    identity = extract_identity(
        _config(), _token(aud=["other", "client-123"]), {"email": "a@b.com"}, "n-1"
    )

    assert identity["email"] == "a@b.com"


def test_nonce_mismatch_is_rejected() -> None:
    with pytest.raises(OidcError, match="nonce"):
        extract_identity(_config(), _token(nonce="different"), {"email": "a@b.com"}, "n-1")


def test_missing_email_is_rejected() -> None:
    with pytest.raises(OidcError, match="メールアドレスを取得できません"):
        extract_identity(_config(), _token(), {}, "n-1")


def test_domain_outside_allowlist_is_rejected() -> None:
    config = _config(allowed_domains=("example.com",))

    with pytest.raises(OidcError, match="ドメインはSSOで許可されていません"):
        extract_identity(config, _token(), {"email": "user@other.com"}, "n-1")


def test_domain_in_allowlist_is_accepted() -> None:
    config = _config(allowed_domains=("example.com",))

    identity = extract_identity(config, _token(), {"email": "user@example.com"}, "n-1")

    assert identity["email"] == "user@example.com"


def test_no_allowlist_permits_any_domain() -> None:
    identity = extract_identity(_config(), _token(), {"email": "user@anywhere.jp"}, "n-1")

    assert identity["email"] == "user@anywhere.jp"


# ─────────────────── APIトークンのスコープ ───────────────────


def _store(tmp_path):
    from web.services.auth_store import AuthStore

    store = AuthStore(tmp_path / "auth.db")
    store.initialize()
    return store


def test_read_only_token_is_recorded_with_scope(tmp_path) -> None:
    from web.services.auth_store import SCOPE_READ

    store = _store(tmp_path)
    tenant = store.create_tenant("テナント1")

    issued = store.create_api_token(tenant["id"], "readonly", scope=SCOPE_READ)

    assert issued["scope"] == SCOPE_READ
    assert store.resolve_api_token(issued["token"])["token_scope"] == SCOPE_READ


def test_default_token_scope_is_full(tmp_path) -> None:
    from web.services.auth_store import SCOPE_FULL

    store = _store(tmp_path)
    tenant = store.create_tenant("テナント2")

    issued = store.create_api_token(tenant["id"], "default")

    assert issued["scope"] == SCOPE_FULL
    assert store.resolve_api_token(issued["token"])["token_scope"] == SCOPE_FULL


def test_invalid_scope_is_rejected(tmp_path) -> None:
    from web.services.auth_store import AuthError

    store = _store(tmp_path)
    tenant = store.create_tenant("テナント3")

    with pytest.raises(AuthError, match="不正なスコープ"):
        store.create_api_token(tenant["id"], "bad", scope="admin")
