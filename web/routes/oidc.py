"""SSO（OIDC）のログイン開始とコールバック。

IdP との通信は `token_exchanger` / `userinfo_fetcher` を差し替え可能にしてある
（実IdPが無い環境でも分岐を検証するため）。
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from flask import Blueprint, redirect, request, session
from werkzeug.wrappers import Response as BaseResponse

from web.auth import set_session_cookie
from web.services.oidc import (
    OidcConfig,
    OidcError,
    build_authorization_url,
    extract_identity,
    load_config,
    new_state,
    oidc_enabled,
    verify_state,
)

bp = Blueprint("oidc", __name__, url_prefix="/auth/oidc")
logger = logging.getLogger(__name__)

STATE_KEY = "oidc_state"
NONCE_KEY = "oidc_nonce"
HTTP_TIMEOUT_SEC = 15


@bp.get("/login")
def oidc_login() -> BaseResponse:
    """IdP の認可画面へ送る。"""
    if not oidc_enabled():
        return _error_redirect("SSOは有効化されていません。")
    try:
        config = load_config()
    except OidcError as exc:
        return _error_redirect(str(exc))

    state, nonce = new_state(), new_state()
    session[STATE_KEY] = state
    session[NONCE_KEY] = nonce
    return redirect(build_authorization_url(config, state, nonce))


@bp.get("/callback")
def oidc_callback() -> BaseResponse:
    """IdP からの戻り。state 照合 → トークン交換 → 利用者解決 → セッション発行。"""
    if not oidc_enabled():
        return _error_redirect("SSOは有効化されていません。")

    if error := request.args.get("error", ""):
        logger.warning("IdPがエラーを返しました: %s", error)
        return _error_redirect("IdPでの認証に失敗しました。")

    try:
        config = load_config()
        verify_state(session.pop(STATE_KEY, ""), request.args.get("state", ""))
        code = request.args.get("code", "").strip()
        if not code:
            raise OidcError("認可コードがありません。")

        token_response = exchange_code(config, code)
        userinfo = fetch_userinfo(config, str(token_response.get("access_token", "")))
        identity = extract_identity(config, token_response, userinfo, session.pop(NONCE_KEY, ""))
        token = _issue_session(config, identity)
    except OidcError as exc:
        return _error_redirect(str(exc))
    except Exception:
        logger.exception("SSOコールバックで予期しないエラー")
        return _error_redirect("SSOログインに失敗しました。")

    return set_session_cookie(redirect("/"), token)


def exchange_code(config: OidcConfig, code: str) -> dict[str, Any]:
    """認可コードをトークンへ交換し、IDトークンのクレームを添えて返す。"""
    response = requests.post(
        config.token_endpoint,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "redirect_uri": config.redirect_uri,
        },
        timeout=HTTP_TIMEOUT_SEC,
    )
    if not response.ok:
        raise OidcError("IdPとのトークン交換に失敗しました。")
    payload = response.json()
    payload["id_token_claims"] = _decode_id_token(config, str(payload.get("id_token", "")))
    return payload


def fetch_userinfo(config: OidcConfig, access_token: str) -> dict[str, Any]:
    if not access_token:
        return {}
    response = requests.get(
        config.userinfo_endpoint,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=HTTP_TIMEOUT_SEC,
    )
    if not response.ok:
        return {}
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _decode_id_token(config: OidcConfig, id_token: str) -> dict[str, Any]:
    """IDトークンを IdP の公開鍵で検証して復号する。署名検証は省略しない。"""
    if not id_token:
        raise OidcError("IDトークンが返されませんでした。")
    from authlib.jose import JsonWebKey, jwt

    metadata = requests.get(
        f"{config.issuer.rstrip('/')}/.well-known/openid-configuration",
        timeout=HTTP_TIMEOUT_SEC,
    )
    if not metadata.ok:
        raise OidcError("IdPのメタデータを取得できませんでした。")
    jwks_uri = str(metadata.json().get("jwks_uri", ""))
    jwks_response = requests.get(jwks_uri, timeout=HTTP_TIMEOUT_SEC)
    if not jwks_response.ok:
        raise OidcError("IdPの公開鍵を取得できませんでした。")

    try:
        claims = jwt.decode(id_token, JsonWebKey.import_key_set(jwks_response.json()))
        claims.validate()
    except Exception as exc:  # noqa: BLE001 - 検証失敗は利用者向け文言へ畳む
        logger.warning("IDトークンの検証に失敗: %s", exc)
        raise OidcError("IDトークンの検証に失敗しました。") from exc
    return dict(claims)


def _issue_session(config: OidcConfig, identity: dict[str, str]) -> str:
    """SSO で認証できた利用者のセッションを発行する。

    未登録ユーザーの自動作成は既定で無効。IdPにアカウントがあるだけで
    テナントへ入れてしまうのを防ぐ。
    """
    from web.services.auth_store import get_auth_store

    store = get_auth_store()
    user = store.find_active_user_by_email(identity["email"])
    if user is None:
        # 自動作成は意図的に未対応。IdPにアカウントがあるだけで
        # テナントへ入れてしまうため、招待済みの利用者だけを通す。
        raise OidcError("このアカウントは登録されていません。管理者に招待を依頼してください。")
    return store.create_session(str(user["id"]))


def _error_redirect(message: str) -> BaseResponse:
    from urllib.parse import quote

    return redirect(f"/auth/login?sso_error={quote(message)}")
