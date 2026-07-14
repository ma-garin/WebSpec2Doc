"""認証データの JSON リポジトリ（instance/auth 配下）。

イミュータブル更新（読み込み→新リスト生成→原子的書き込み）で保存する。
テナント別のデータ物理分離は本フェーズの対象外（docs/design 第5章 (A) 段階導入）。
"""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from web.auth.models import Membership, Tenant, User

# 境界バリデーション: 実務的なメール形式と長さ上限。
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_EMAIL_MAX_LEN = 254


def normalize_email(raw: str) -> str:
    """前後空白除去＋小文字化。識別キーの正規化に使う。"""
    return raw.strip().lower()


def is_valid_email(raw: str) -> bool:
    email = normalize_email(raw)
    return 0 < len(email) <= _EMAIL_MAX_LEN and bool(_EMAIL_RE.match(email))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuthStore:
    """users / tenants / memberships の JSON 永続化。"""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir
        self._users_path = base_dir / "users.json"
        self._tenants_path = base_dir / "tenants.json"
        self._memberships_path = base_dir / "memberships.json"
        self._base.mkdir(parents=True, exist_ok=True)

    # ---- 低レベル IO ----
    @staticmethod
    def _read(path: Path) -> list[dict]:
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return data if isinstance(data, list) else []

    @staticmethod
    def _write(path: Path, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(rows, handle, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    # ---- User ----
    def get_user(self, email: str) -> User | None:
        key = normalize_email(email)
        for row in self._read(self._users_path):
            if normalize_email(row.get("email", "")) == key:
                return User.from_dict(row)
        return None

    def upsert_login(self, email: str) -> User:
        """ユーザを取得（無ければ作成）し last_login_at を更新して返す。"""
        key = normalize_email(email)
        rows = self._read(self._users_path)
        now = _now_iso()
        out: list[dict] = []
        found: User | None = None
        for row in rows:
            if normalize_email(row.get("email", "")) == key:
                found = User.from_dict(row).with_last_login(now)
                out.append(found.to_dict())
            else:
                out.append(row)
        if found is None:
            found = User(email=key, created_at=now, last_login_at=now)
            out.append(found.to_dict())
        self._write(self._users_path, out)
        return found

    # ---- Tenant ----
    def get_tenant(self, tenant_id: str) -> Tenant | None:
        for row in self._read(self._tenants_path):
            if row.get("id") == tenant_id:
                return Tenant.from_dict(row)
        return None

    def create_tenant(self, name: str) -> Tenant:
        tenant = Tenant(id=uuid.uuid4().hex, name=name, created_at=_now_iso())
        rows = self._read(self._tenants_path)
        self._write(self._tenants_path, [*rows, tenant.to_dict()])
        return tenant

    # ---- Membership ----
    def memberships_for(self, email: str) -> list[Membership]:
        key = normalize_email(email)
        return [
            Membership.from_dict(row)
            for row in self._read(self._memberships_path)
            if normalize_email(row.get("user_email", "")) == key
        ]

    def has_membership(self, email: str, tenant_id: str) -> bool:
        key = normalize_email(email)
        return any(
            normalize_email(row.get("user_email", "")) == key
            and row.get("tenant_id") == tenant_id
            for row in self._read(self._memberships_path)
        )

    def add_membership(self, email: str, tenant_id: str, role: str = "member") -> Membership:
        membership = Membership(
            user_email=normalize_email(email), tenant_id=tenant_id, role=role
        )
        rows = self._read(self._memberships_path)
        self._write(self._memberships_path, [*rows, membership.to_dict()])
        return membership

    def tenants_for(self, email: str) -> list[tuple[Tenant, Membership]]:
        """ユーザが所属するテナントとメンバーシップの組を返す。"""
        result: list[tuple[Tenant, Membership]] = []
        for membership in self.memberships_for(email):
            tenant = self.get_tenant(membership.tenant_id)
            if tenant is not None:
                result.append((tenant, membership))
        return result

    def ensure_default_tenant(self, email: str, default_name: str) -> Tenant:
        """所属テナントが無ければ既定テナントを作成し owner を付与する。"""
        existing = self.tenants_for(email)
        if existing:
            return existing[0][0]
        tenant = self.create_tenant(default_name)
        self.add_membership(email, tenant.id, role="owner")
        return tenant


def load_or_create_secret_key(base_dir: Path) -> str:
    """Flask secret_key を環境変数優先、無ければ instance/auth/secret.key に永続化。"""
    from web.auth import SECRET_KEY_ENV

    env_key = os.environ.get(SECRET_KEY_ENV, "").strip()
    if env_key:
        return env_key
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / "secret.key"
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    key = secrets.token_urlsafe(48)
    path.write_text(key, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key
