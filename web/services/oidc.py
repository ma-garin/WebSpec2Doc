"""OIDC による SSO（Microsoft Entra ID / Google Workspace 先行）。

企業導入では「自社のIdPでログインできること」が入場条件になる。ここでは
Authlib を RP として使い、既存の利用者・メンバーシップモデルへ載せる。

設計方針:
- IdP との通信部（メタデータ取得・トークン交換・ユーザー情報取得）は差し替え可能に
  してある。実IdPが無い環境でも、フローの分岐を検証できるようにするため。
- **IDトークンの検証を省略しない**。issuer / audience / 有効期限を必ず確認する。
- 未登録ユーザーの自動作成は既定で無効。許可制にしないと、IdPにアカウントがある
  だけで社外の人間がテナントへ入れてしまう。
"""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

PROVIDER_ENTRA = "entra"
PROVIDER_GOOGLE = "google"
SUPPORTED_PROVIDERS = (PROVIDER_ENTRA, PROVIDER_GOOGLE)

DEFAULT_SCOPES = "openid email profile"

_ISSUER_TEMPLATES = {
    PROVIDER_ENTRA: "https://login.microsoftonline.com/{tenant}/v2.0",
    PROVIDER_GOOGLE: "https://accounts.google.com",
}


class OidcError(Exception):
    """SSO の設定不備・検証失敗。利用者に見せる文言をそのまま持つ。"""


@dataclass(frozen=True)
class OidcConfig:
    provider: str
    client_id: str
    client_secret: str
    issuer: str
    redirect_uri: str
    scopes: str = DEFAULT_SCOPES
    allowed_domains: tuple[str, ...] = ()
    auto_provision: bool = False

    @property
    def authorization_endpoint(self) -> str:
        if self.provider == PROVIDER_GOOGLE:
            return "https://accounts.google.com/o/oauth2/v2/auth"
        return f"{self.issuer}/authorize"

    @property
    def token_endpoint(self) -> str:
        if self.provider == PROVIDER_GOOGLE:
            return "https://oauth2.googleapis.com/token"
        return f"{self.issuer}/token"

    @property
    def userinfo_endpoint(self) -> str:
        if self.provider == PROVIDER_GOOGLE:
            return "https://openidconnect.googleapis.com/v1/userinfo"
        return "https://graph.microsoft.com/oidc/userinfo"


class TokenExchanger(Protocol):
    """認可コードを ID トークン等へ交換する処理（テストで差し替える）。"""

    def __call__(self, config: OidcConfig, code: str) -> dict[str, Any]: ...


class UserInfoFetcher(Protocol):
    def __call__(self, config: OidcConfig, access_token: str) -> dict[str, Any]: ...


def oidc_enabled() -> bool:
    return bool(os.environ.get("WEBSPEC2DOC_OIDC_PROVIDER", "").strip())


def load_config() -> OidcConfig:
    """環境変数から設定を読む。不足はその場で明示的に失敗させる。"""
    provider = os.environ.get("WEBSPEC2DOC_OIDC_PROVIDER", "").strip()
    if provider not in SUPPORTED_PROVIDERS:
        raise OidcError(
            f"未対応のSSOプロバイダです: {provider or '(未設定)'}"
            f"（利用可能: {', '.join(SUPPORTED_PROVIDERS)}）"
        )
    client_id = os.environ.get("WEBSPEC2DOC_OIDC_CLIENT_ID", "").strip()
    client_secret = os.environ.get("WEBSPEC2DOC_OIDC_CLIENT_SECRET", "").strip()
    redirect_uri = os.environ.get("WEBSPEC2DOC_OIDC_REDIRECT_URI", "").strip()
    missing = [
        name
        for name, value in (
            ("WEBSPEC2DOC_OIDC_CLIENT_ID", client_id),
            ("WEBSPEC2DOC_OIDC_CLIENT_SECRET", client_secret),
            ("WEBSPEC2DOC_OIDC_REDIRECT_URI", redirect_uri),
        )
        if not value
    ]
    if missing:
        raise OidcError(f"SSOの設定が不足しています: {', '.join(missing)}")

    issuer = os.environ.get("WEBSPEC2DOC_OIDC_ISSUER", "").strip()
    if not issuer:
        tenant = os.environ.get("WEBSPEC2DOC_OIDC_TENANT", "common").strip() or "common"
        issuer = _ISSUER_TEMPLATES[provider].format(tenant=tenant)

    domains = tuple(
        part.strip().lower()
        for part in os.environ.get("WEBSPEC2DOC_OIDC_ALLOWED_DOMAINS", "").split(",")
        if part.strip()
    )
    auto = os.environ.get("WEBSPEC2DOC_OIDC_AUTO_PROVISION", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return OidcConfig(
        provider=provider,
        client_id=client_id,
        client_secret=client_secret,
        issuer=issuer,
        redirect_uri=redirect_uri,
        allowed_domains=domains,
        auto_provision=auto,
    )


def build_authorization_url(config: OidcConfig, state: str, nonce: str) -> str:
    """IdP の認可エンドポイントへのURLを組み立てる。"""
    params = {
        "client_id": config.client_id,
        "response_type": "code",
        "redirect_uri": config.redirect_uri,
        "scope": config.scopes,
        "state": state,
        "nonce": nonce,
        "response_mode": "query",
    }
    return f"{config.authorization_endpoint}?{urlencode(params)}"


def new_state() -> str:
    return secrets.token_urlsafe(24)


def verify_state(expected: str, received: str) -> None:
    """CSRF 対策の state 照合。定数時間で比較する。"""
    if not expected or not received or not secrets.compare_digest(expected, received):
        raise OidcError("ログイン要求の照合に失敗しました。最初からやり直してください。")


def extract_identity(
    config: OidcConfig,
    token_response: dict[str, Any],
    userinfo: dict[str, Any],
    expected_nonce: str,
) -> dict[str, str]:
    """トークン応答とユーザー情報から、検証済みの利用者identityを取り出す。"""
    claims = token_response.get("id_token_claims") or {}
    if not isinstance(claims, dict) or not claims:
        raise OidcError("IDトークンを検証できませんでした。")

    issuer = str(claims.get("iss", ""))
    if issuer.rstrip("/") != config.issuer.rstrip("/"):
        raise OidcError("IDトークンの発行者が想定と異なります。")

    audience = claims.get("aud", "")
    audiences = audience if isinstance(audience, list) else [audience]
    if config.client_id not in [str(item) for item in audiences]:
        raise OidcError("IDトークンの宛先が想定と異なります。")

    nonce = str(claims.get("nonce", ""))
    if expected_nonce and nonce != expected_nonce:
        raise OidcError("IDトークンの nonce が一致しません。")

    email = str(userinfo.get("email") or claims.get("email") or "").strip().lower()
    if not email:
        raise OidcError("IdPからメールアドレスを取得できませんでした。")
    if not _domain_allowed(config, email):
        raise OidcError("このメールアドレスのドメインはSSOで許可されていません。")

    return {
        "email": email,
        "name": str(userinfo.get("name") or claims.get("name") or email.split("@")[0]),
        "subject": str(claims.get("sub", "")),
    }


def _domain_allowed(config: OidcConfig, email: str) -> bool:
    if not config.allowed_domains:
        return True
    domain = email.rsplit("@", 1)[-1].lower()
    return domain in config.allowed_domains
