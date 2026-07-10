"""テナントコンテキストとデータ分離のヘルパー。

認証が有効なリクエストでは web/auth.py の auth_guard が g.tenant / g.auth_user を
設定する。ここではその有無に応じてデータの保存先を切り替える:

- テナントあり: output/tenants/{slug}/…  ・ instance/tenants/{slug}/…
- テナントなし（ローカル単独利用・認証オフ・テスト）: 従来どおり output/… ・ instance/…

既存テストがルートモジュールの OUTPUT_DIR を monkeypatch する運用と互換にするため、
各ルートは `scoped_output_dir(OUTPUT_DIR)` の形で毎リクエスト解決する。
"""

from __future__ import annotations

import re
from pathlib import Path

from flask import g, has_request_context

TENANTS_DIR_NAME = "tenants"
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


def current_tenant() -> dict | None:
    """リクエストコンテキストのテナント（auth_guard が設定）。無ければ None。"""
    if not has_request_context():
        return None
    tenant = getattr(g, "tenant", None)
    return tenant if isinstance(tenant, dict) else None


def current_auth_user() -> dict | None:
    """ログイン中のアプリユーザー。認証オフ・未ログインでは None。"""
    if not has_request_context():
        return None
    user = getattr(g, "auth_user", None)
    return user if isinstance(user, dict) else None


def _tenant_slug() -> str | None:
    tenant = current_tenant()
    if not tenant:
        return None
    slug = str(tenant.get("slug", ""))
    # slug はパス構築に使うため、DB値であっても必ず再検証する（パストラバーサル防止）
    if not _SLUG_RE.match(slug):
        raise ValueError(f"不正なテナントslugです: {slug!r}")
    return slug


def scoped_output_dir(base: Path) -> Path:
    """テナントコンテキストがあれば base/tenants/{slug}、なければ base を返す。"""
    slug = _tenant_slug()
    if slug is None:
        return base
    return base / TENANTS_DIR_NAME / slug


def scoped_instance_path(base: Path) -> Path:
    """instance 配下のファイル（例: viewpoints.db）をテナント別パスに写像する。

    instance/viewpoints.db → instance/tenants/{slug}/viewpoints.db
    """
    slug = _tenant_slug()
    if slug is None:
        return base
    return base.parent / TENANTS_DIR_NAME / slug / base.name
