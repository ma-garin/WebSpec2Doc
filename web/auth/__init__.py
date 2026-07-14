"""アプリ利用者の認証（メール自己申告）とテナント選択。

注意: ここでの認証はパスワード・到達確認を伴わない「自己申告メール識別」であり、
暗号的な認証ではなく、利用者の識別と作業ワークスペースの選択を目的とする。
クロール対象サイトへのログイン（web.routes.login / src.main --login）とは別物。

設計: docs/design/auth-tenant-integration.md
"""

from __future__ import annotations

AUTH_ENV = "WEBSPEC2DOC_AUTH"
SECRET_KEY_ENV = "WEBSPEC2DOC_SECRET_KEY"
DEFAULT_TENANT_NAME = "My Workspace"


def auth_enabled() -> bool:
    """利用者認証を有効化するか。既定 OFF（現行の無認証ローカル運用を維持）。"""
    import os

    return os.environ.get(AUTH_ENV, "").strip().lower() in ("1", "true", "yes", "on")
