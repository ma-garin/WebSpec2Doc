"""web/services/auth_store.py（アプリ利用者認証ストア）のユニットテスト。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from web.services.auth_store import (
    MAX_FAILED_ATTEMPTS,
    AuthError,
    AuthStore,
    slugify_tenant_name,
    validate_password,
)


@pytest.fixture()
def store(tmp_path: Path) -> AuthStore:
    return AuthStore(tmp_path / "auth.db")


def _setup(store: AuthStore) -> dict:
    return store.setup_initial("QA Team", "owner@example.com", "Owner", "secret-pass-123")


# ---------- 初期セットアップ ----------


def test_setup_initial_creates_tenant_and_owner(store: AuthStore) -> None:
    result = _setup(store)
    assert result["tenant"]["slug"] == "qa-team"
    assert result["user"]["role"] == "owner"
    assert result["user"]["email"] == "owner@example.com"
    assert store.has_any_user()


def test_setup_initial_rejected_when_user_exists(store: AuthStore) -> None:
    _setup(store)
    with pytest.raises(AuthError) as exc:
        store.setup_initial("Another", "x@example.com", "X", "secret-pass-123")
    assert exc.value.code == "already_setup"


def test_slugify_fallback_for_japanese_name() -> None:
    assert slugify_tenant_name("品質保証チーム") == "tenant"
    assert slugify_tenant_name("QA Team 2026") == "qa-team-2026"


def test_tenant_slug_collision_gets_suffix(store: AuthStore) -> None:
    t1 = store.create_tenant("QA Team")
    t2 = store.create_tenant("QA Team")
    assert t1["slug"] == "qa-team"
    assert t2["slug"] == "qa-team-2"


# ---------- ユーザー作成・検証 ----------


def test_create_user_rejects_invalid_email(store: AuthStore) -> None:
    tenant = store.create_tenant("T")
    with pytest.raises(AuthError) as exc:
        store.create_user(tenant["id"], "not-an-email", "N", "secret-pass-123")
    assert exc.value.code == "invalid_email"


def test_create_user_rejects_weak_password(store: AuthStore) -> None:
    tenant = store.create_tenant("T")
    with pytest.raises(AuthError) as exc:
        store.create_user(tenant["id"], "a@example.com", "N", "short")
    assert exc.value.code == "weak_password"


def test_create_user_rejects_duplicate_email(store: AuthStore) -> None:
    tenant = store.create_tenant("T")
    store.create_user(tenant["id"], "a@example.com", "A", "secret-pass-123")
    with pytest.raises(AuthError) as exc:
        store.create_user(tenant["id"], "A@Example.com", "B", "secret-pass-456")
    assert exc.value.code == "email_taken"


def test_validate_password_rejects_email_as_password() -> None:
    with pytest.raises(AuthError):
        validate_password("user@example.com", "user@example.com")


def test_public_user_never_contains_password_hash(store: AuthStore) -> None:
    result = _setup(store)
    assert "password_hash" not in result["user"]
    assert "password_hash" not in (store.get_user(result["user"]["id"]) or {})


# ---------- 認証・ロックアウト ----------


def test_authenticate_success_and_wrong_password(store: AuthStore) -> None:
    _setup(store)
    user = store.authenticate("owner@example.com", "secret-pass-123")
    assert user["email"] == "owner@example.com"
    with pytest.raises(AuthError) as exc:
        store.authenticate("owner@example.com", "wrong-password")
    assert exc.value.code == "invalid_credentials"


def test_authenticate_unknown_user_same_error_code(store: AuthStore) -> None:
    with pytest.raises(AuthError) as exc:
        store.authenticate("nobody@example.com", "whatever-pass")
    assert exc.value.code == "invalid_credentials"


def test_lockout_after_max_failures_blocks_correct_password(store: AuthStore) -> None:
    _setup(store)
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(AuthError):
            store.authenticate("owner@example.com", "bad-password!")
    # ロック中は正しいパスワードでも拒否される
    with pytest.raises(AuthError) as exc:
        store.authenticate("owner@example.com", "secret-pass-123")
    assert exc.value.code == "locked"


def test_lock_expires_and_login_succeeds(store: AuthStore) -> None:
    _setup(store)
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(AuthError):
            store.authenticate("owner@example.com", "bad-password!")
    # ロック期限を過去に書き換えて期限切れを再現する
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    with store._connect() as conn:
        conn.execute("UPDATE users SET locked_until = ?", (past,))
    user = store.authenticate("owner@example.com", "secret-pass-123")
    assert user["email"] == "owner@example.com"


def test_inactive_user_cannot_authenticate(store: AuthStore) -> None:
    result = _setup(store)
    tenant_id = result["tenant"]["id"]
    member = store.create_user(tenant_id, "m@example.com", "M", "secret-pass-123")
    store.update_user(member["id"], tenant_id, is_active=False)
    with pytest.raises(AuthError) as exc:
        store.authenticate("m@example.com", "secret-pass-123")
    assert exc.value.code == "inactive"


# ---------- セッション ----------


def test_session_roundtrip_and_revoke(store: AuthStore) -> None:
    result = _setup(store)
    token = store.create_session(result["user"]["id"])
    session = store.resolve_session(token)
    assert session is not None
    assert session["user"]["email"] == "owner@example.com"
    assert session["tenant"]["slug"] == "qa-team"
    store.revoke_session(token)
    assert store.resolve_session(token) is None


def test_expired_session_is_rejected(store: AuthStore) -> None:
    result = _setup(store)
    token = store.create_session(result["user"]["id"])
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    with store._connect() as conn:
        conn.execute("UPDATE auth_sessions SET expires_at = ?", (past,))
    assert store.resolve_session(token) is None


def test_deactivating_user_revokes_sessions(store: AuthStore) -> None:
    result = _setup(store)
    tenant_id = result["tenant"]["id"]
    member = store.create_user(tenant_id, "m@example.com", "M", "secret-pass-123")
    token = store.create_session(member["id"])
    assert store.resolve_session(token) is not None
    store.update_user(member["id"], tenant_id, is_active=False)
    assert store.resolve_session(token) is None


def test_change_password_requires_current_and_revokes_sessions(store: AuthStore) -> None:
    result = _setup(store)
    user_id = result["user"]["id"]
    token = store.create_session(user_id)
    with pytest.raises(AuthError):
        store.change_password(user_id, "wrong-current", "new-secret-pass-1")
    store.change_password(user_id, "secret-pass-123", "new-secret-pass-1")
    assert store.resolve_session(token) is None
    assert store.authenticate("owner@example.com", "new-secret-pass-1")


# ---------- ロール・最後のオーナー保護 ----------


def test_last_owner_cannot_be_demoted_or_deactivated(store: AuthStore) -> None:
    result = _setup(store)
    tenant_id = result["tenant"]["id"]
    owner_id = result["user"]["id"]
    with pytest.raises(AuthError) as exc:
        store.update_user(owner_id, tenant_id, role="member")
    assert exc.value.code == "last_owner"
    with pytest.raises(AuthError) as exc:
        store.update_user(owner_id, tenant_id, is_active=False)
    assert exc.value.code == "last_owner"


def test_update_user_scoped_to_tenant(store: AuthStore) -> None:
    result = _setup(store)
    other = store.create_tenant("Other")
    with pytest.raises(AuthError) as exc:
        store.update_user(result["user"]["id"], other["id"], role="member")
    assert exc.value.code == "user_not_found"


# ---------- APIトークン ----------


def test_api_token_roundtrip(store: AuthStore) -> None:
    result = _setup(store)
    tenant_id = result["tenant"]["id"]
    created = store.create_api_token(tenant_id, "ci", created_by=result["user"]["id"])
    assert created["token"].startswith("ws2d_")
    tenant = store.resolve_api_token(created["token"])
    assert tenant is not None and tenant["id"] == tenant_id
    # 一覧には平文トークンは含まれない
    tokens = store.list_api_tokens(tenant_id)
    assert len(tokens) == 1 and "token" not in tokens[0]
    assert store.revoke_api_token(created["id"], tenant_id)
    assert store.resolve_api_token(created["token"]) is None


def test_invalid_api_token_returns_none(store: AuthStore) -> None:
    _setup(store)
    assert store.resolve_api_token("ws2d_bogus-token") is None
    assert store.resolve_api_token("") is None
