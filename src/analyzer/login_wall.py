"""ログイン必要箇所（login wall）の検出。

ページ解析で集めた素性（最終URL・HTTPステータス・パスワード欄の有無等）から、
認証によりアクセスがブロックされる地点かを判定する純粋関数。検出は補助であり、
ユーザーが手動でスキップ／追加できる前提。
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

REASON_FORBIDDEN = "http_401_403"
REASON_REDIRECT_TO_LOGIN = "redirect_to_login"
REASON_PASSWORD_FIELD = "password_field"

FORBIDDEN_STATUSES = (401, 403)
LOGIN_URL_KEYWORDS = ("login", "signin", "sign-in", "auth", "sso", "ログイン")


def _looks_like_login_url(url: str) -> bool:
    parsed = urlparse(url)
    haystack = f"{parsed.path}?{parsed.query}".lower()
    return any(keyword in haystack for keyword in LOGIN_URL_KEYWORDS)


@dataclass(frozen=True)
class PageAuthSignals:
    requested_url: str
    final_url: str
    status: int
    has_password_field: bool


@dataclass(frozen=True)
class LoginWallVerdict:
    is_login_required: bool
    reasons: tuple[str, ...]


def detect_login_wall(signals: PageAuthSignals) -> LoginWallVerdict:
    reasons: list[str] = []
    if signals.status in FORBIDDEN_STATUSES:
        reasons.append(REASON_FORBIDDEN)
    if signals.final_url != signals.requested_url and _looks_like_login_url(signals.final_url):
        reasons.append(REASON_REDIRECT_TO_LOGIN)
    if signals.has_password_field:
        reasons.append(REASON_PASSWORD_FIELD)
    return LoginWallVerdict(is_login_required=bool(reasons), reasons=tuple(reasons))
