"""アプリ利用者の認証・テナント管理ストア（SQLite）。

既存の「ログイン」（クロール対象サイトへの認証 = web/routes/login.py）とは別物で、
WebSpec2Doc 自体を使うユーザーのアカウント・セッション・テナントを管理する。

設計方針:
- 標準ライブラリ + werkzeug（Flask 同梱）のみ。パスワードは scrypt ハッシュ。
- セッション/APIトークンは平文を保存せず SHA-256 ハッシュのみ保存する。
- テナントはデータ分離の単位（output/tenants/{slug}/, instance/tenants/{slug}/）。
- ブルートフォース対策: 連続失敗でアカウントを一時ロックする。
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import sqlite3
import threading
import unicodedata
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

SCHEMA_VERSION = 2

ROLES = ("owner", "admin", "member")
_ADMIN_ROLES = frozenset({"owner", "admin"})

# ロックアウト: MAX_FAILED_ATTEMPTS 回連続で失敗すると LOCK_MINUTES 分ロック
MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15

# セッション有効期間（時間）。環境変数で上書き可能
SESSION_HOURS_ENV = "WEBSPEC2DOC_SESSION_HOURS"
DEFAULT_SESSION_HOURS = 12

MIN_PASSWORD_LENGTH = 10

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


class AuthError(Exception):
    """認証・アカウント操作の業務エラー。code はUI/新テストで分岐に使う。"""

    def __init__(self, message: str, code: str = "error") -> None:
        super().__init__(message)
        self.code = code


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def slugify_tenant_name(name: str) -> str:
    """テナント名からファイルシステム安全な slug を作る（英数とハイフンのみ）。"""
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")[:24]
    if not slug or not _SLUG_RE.match(slug):
        slug = "tenant"
    return slug


def validate_password(password: str, email: str = "") -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(
            f"パスワードは{MIN_PASSWORD_LENGTH}文字以上にしてください。", "weak_password"
        )
    if email and password.lower() == email.lower():
        raise AuthError("メールアドレスと同じパスワードは使用できません。", "weak_password")


def session_hours() -> int:
    try:
        value = int(os.environ.get(SESSION_HOURS_ENV, str(DEFAULT_SESSION_HOURS)))
    except (TypeError, ValueError):
        return DEFAULT_SESSION_HOURS
    return max(1, min(24 * 30, value))


class AuthStore:
    def __init__(self, db_path: Path) -> None:
        # 相対パスは生成時点の cwd で固定する（テスト等で後から chdir されても
        # 同じDBを指し続けるように）。
        self.db_path = Path(db_path).resolve()
        self._initialized = False
        self._lock = threading.Lock()

    # --- 基盤 ---------------------------------------------------------

    def initialize(self) -> None:
        with self._lock:
            if self._initialized:
                return
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                self._migrate(conn)
            self._initialized = True

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        self.initialize()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()

    def _migrate(self, conn: sqlite3.Connection) -> None:
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version > SCHEMA_VERSION:
            raise AuthError("認証DBのスキーマがこのアプリより新しいため起動できません。")
        if version < 1:
            conn.executescript(
                """
                BEGIN;
                CREATE TABLE IF NOT EXISTS tenants (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    email TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('owner','admin','member')),
                    is_active INTEGER NOT NULL DEFAULT 1,
                    failed_attempts INTEGER NOT NULL DEFAULT 0,
                    locked_until TEXT,
                    last_login_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_users_tenant ON users(tenant_id);
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    revoked_at TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_sessions_user ON auth_sessions(user_id);
                CREATE TABLE IF NOT EXISTS api_tokens (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    name TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_by TEXT REFERENCES users(id),
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    revoked_at TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_api_tokens_tenant ON api_tokens(tenant_id);
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    at TEXT NOT NULL,
                    event TEXT NOT NULL,
                    user_id TEXT,
                    tenant_id TEXT,
                    detail TEXT NOT NULL DEFAULT ''
                );
                PRAGMA user_version = 1;
                COMMIT;
                """
            )
        if version < 2:
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(users)").fetchall()}
            if "tour_completed_at" not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN tour_completed_at TEXT")
            conn.execute("PRAGMA user_version = 2")

    # --- 監査ログ -----------------------------------------------------

    def audit(
        self,
        event: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
        detail: str = "",
    ) -> None:
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO audit_log (at, event, user_id, tenant_id, detail)"
                " VALUES (?, ?, ?, ?, ?)",
                (_iso(_now()), event, user_id, tenant_id, detail[:500]),
            )

    # --- テナント -----------------------------------------------------

    def create_tenant(self, name: str) -> dict:
        name = name.strip()
        if not name:
            raise AuthError("テナント名を入力してください。", "invalid_input")
        base_slug = slugify_tenant_name(name)
        with self._transaction() as conn:
            slug = base_slug
            for i in range(2, 100):
                row = conn.execute("SELECT 1 FROM tenants WHERE slug = ?", (slug,)).fetchone()
                if row is None:
                    break
                slug = f"{base_slug}-{i}"
            else:
                raise AuthError("テナントslugを生成できませんでした。", "slug_conflict")
            now = _iso(_now())
            tenant_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO tenants (id, name, slug, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (tenant_id, name, slug, now, now),
            )
            return {"id": tenant_id, "name": name, "slug": slug}

    def get_tenant(self, tenant_id: str) -> dict | None:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
            return dict(row) if row else None

    # --- ユーザー -----------------------------------------------------

    def has_any_user(self) -> bool:
        self.initialize()
        with self._connect() as conn:
            return conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def create_user(
        self,
        tenant_id: str,
        email: str,
        name: str,
        password: str,
        role: str = "member",
    ) -> dict:
        email = email.strip().lower()
        name = name.strip()
        if not _EMAIL_RE.match(email):
            raise AuthError("メールアドレスの形式が正しくありません。", "invalid_email")
        if not name:
            raise AuthError("表示名を入力してください。", "invalid_input")
        if role not in ROLES:
            raise AuthError("不正なロールです。", "invalid_role")
        validate_password(password, email)
        with self._transaction() as conn:
            if conn.execute("SELECT 1 FROM tenants WHERE id = ?", (tenant_id,)).fetchone() is None:
                raise AuthError("テナントが存在しません。", "tenant_not_found")
            if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                raise AuthError("このメールアドレスは既に登録されています。", "email_taken")
            now = _iso(_now())
            user_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO users (id, tenant_id, email, name, password_hash, role,"
                " is_active, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (user_id, tenant_id, email, name, generate_password_hash(password), role, now, now),
            )
        self.audit("user.created", user_id=user_id, tenant_id=tenant_id, detail=email)
        return self.get_user(user_id) or {}

    def setup_initial(self, tenant_name: str, email: str, name: str, password: str) -> dict:
        """初期セットアップ: 最初のテナントとオーナーを作成する（ユーザーが1人でも居れば拒否）。"""
        if self.has_any_user():
            raise AuthError("初期セットアップは完了済みです。", "already_setup")
        tenant = self.create_tenant(tenant_name)
        user = self.create_user(tenant["id"], email, name, password, role="owner")
        self.audit("tenant.created", user_id=user["id"], tenant_id=tenant["id"], detail=tenant_name)
        return {"tenant": tenant, "user": user}

    def get_user(self, user_id: str) -> dict | None:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return self._public_user(row) if row else None

    def list_users(self, tenant_id: str) -> list[dict]:
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM users WHERE tenant_id = ? ORDER BY created_at", (tenant_id,)
            ).fetchall()
            return [self._public_user(r) for r in rows]

    def complete_tour(self, user_id: str) -> dict:
        """本人の初回ツアー完了時刻を冪等に記録する。"""
        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                raise AuthError("ユーザーが存在しません。", "user_not_found")
            completed_at = row["tour_completed_at"] or _iso(_now())
            conn.execute(
                "UPDATE users SET tour_completed_at = ?, updated_at = ? WHERE id = ?",
                (completed_at, _iso(_now()), user_id),
            )
        return self.get_user(user_id) or {}

    @staticmethod
    def _public_user(row: sqlite3.Row) -> dict:
        data = dict(row)
        data.pop("password_hash", None)
        data.pop("failed_attempts", None)
        data["is_active"] = bool(data.get("is_active"))
        return data

    def update_user(
        self,
        user_id: str,
        tenant_id: str,
        *,
        role: str | None = None,
        is_active: bool | None = None,
        actor_id: str = "",
    ) -> dict:
        """ロール変更・有効/無効化（同一テナント内のみ）。最後のownerの降格/無効化は拒否する。"""
        if role is not None and role not in ROLES:
            raise AuthError("不正なロールです。", "invalid_role")
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ? AND tenant_id = ?", (user_id, tenant_id)
            ).fetchone()
            if row is None:
                raise AuthError("ユーザーが存在しません。", "user_not_found")
            demoting = role is not None and role != "owner" and row["role"] == "owner"
            deactivating = is_active is False and bool(row["is_active"])
            if demoting or deactivating:
                owners = conn.execute(
                    "SELECT COUNT(*) FROM users"
                    " WHERE tenant_id = ? AND role = 'owner' AND is_active = 1",
                    (tenant_id,),
                ).fetchone()[0]
                if row["role"] == "owner" and owners <= 1:
                    raise AuthError(
                        "最後のオーナーを無効化・降格することはできません。", "last_owner"
                    )
            updates: list[str] = []
            params: list[object] = []
            if role is not None:
                updates.append("role = ?")
                params.append(role)
            if is_active is not None:
                updates.append("is_active = ?")
                params.append(1 if is_active else 0)
                if is_active:
                    updates.append("failed_attempts = 0")
                    updates.append("locked_until = NULL")
            if not updates:
                return self._public_user(row)
            updates.append("updated_at = ?")
            params.append(_iso(_now()))
            params.extend([user_id, tenant_id])
            # updates はこの関数内のリテラル断片のみ・値は全てプレースホルダ渡し
            conn.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = ? AND tenant_id = ?",  # nosec B608
                params,
            )
            if is_active is False:
                # 無効化したユーザーの既存セッションは即座に失効させる
                conn.execute(
                    "UPDATE auth_sessions SET revoked_at = ? WHERE user_id = ?",
                    (_iso(_now()), user_id),
                )
        self.audit(
            "user.updated",
            user_id=actor_id or None,
            tenant_id=tenant_id,
            detail=f"target={user_id} role={role} is_active={is_active}",
        )
        return self.get_user(user_id) or {}

    # --- 認証 ---------------------------------------------------------

    def authenticate(self, email: str, password: str) -> dict:
        """メール+パスワード認証。失敗理由は攻撃者にヒントを与えないよう code のみ区別する。

        注意: 失敗カウントの更新をコミットするため、例外はトランザクションの
        外で送出する（with 内で raise するとロールバックされロックが効かない）。
        """
        email = (email or "").strip().lower()
        password = password or ""
        self.initialize()
        now = _now()
        error: AuthError | None = None
        user: dict | None = None
        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            locked_until = row["locked_until"] if row is not None else None
            if row is None:
                # ユーザー有無でレスポンス時間差を作らないためダミー検証を行う
                check_password_hash(generate_password_hash("dummy-password"), password)
                error = AuthError(
                    "メールアドレスまたはパスワードが正しくありません。", "invalid_credentials"
                )
            elif not row["is_active"]:
                error = AuthError("このアカウントは無効化されています。", "inactive")
            elif locked_until and datetime.fromisoformat(locked_until) > now:
                error = AuthError(
                    "ログイン失敗が続いたため一時的にロックされています。"
                    "しばらく待ってから再試行してください。",
                    "locked",
                )
            elif not check_password_hash(row["password_hash"], password):
                failed = int(row["failed_attempts"]) + 1
                lock_expr = None
                if failed >= MAX_FAILED_ATTEMPTS:
                    lock_expr = _iso(now + timedelta(minutes=LOCK_MINUTES))
                    failed = 0
                conn.execute(
                    "UPDATE users SET failed_attempts = ?, locked_until = ?, updated_at = ?"
                    " WHERE id = ?",
                    (failed, lock_expr, _iso(now), row["id"]),
                )
                error = AuthError(
                    (
                        "ログイン失敗が続いたため一時的にロックされています。"
                        "しばらく待ってから再試行してください。"
                        if lock_expr
                        else "メールアドレスまたはパスワードが正しくありません。"
                    ),
                    "locked" if lock_expr else "invalid_credentials",
                )
            else:
                conn.execute(
                    "UPDATE users SET failed_attempts = 0, locked_until = NULL,"
                    " last_login_at = ?, updated_at = ? WHERE id = ?",
                    (_iso(now), _iso(now), row["id"]),
                )
                user = self._public_user(row)
        if error is not None or user is None:
            raise error or AuthError("認証に失敗しました。", "invalid_credentials")
        self.audit("user.login", user_id=user["id"], tenant_id=user["tenant_id"])
        return user

    def change_password(self, user_id: str, current: str, new: str) -> None:
        self.initialize()
        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                raise AuthError("ユーザーが存在しません。", "user_not_found")
            if not check_password_hash(row["password_hash"], current or ""):
                raise AuthError("現在のパスワードが正しくありません。", "invalid_credentials")
            validate_password(new, row["email"])
            now = _iso(_now())
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (generate_password_hash(new), now, user_id),
            )
            # パスワード変更時は本人の他セッションを失効させる（乗っ取り対策）
            conn.execute(
                "UPDATE auth_sessions SET revoked_at = ? WHERE user_id = ?", (now, user_id)
            )
        self.audit("user.password_changed", user_id=user_id, tenant_id=row["tenant_id"])

    # --- セッション ---------------------------------------------------

    def create_session(self, user_id: str) -> str:
        raw = secrets.token_urlsafe(32)
        now = _now()
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO auth_sessions (id, user_id, token_hash, created_at,"
                " expires_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    uuid.uuid4().hex,
                    user_id,
                    _hash_token(raw),
                    _iso(now),
                    _iso(now + timedelta(hours=session_hours())),
                    _iso(now),
                ),
            )
        return raw

    def resolve_session(self, raw_token: str) -> dict | None:
        """セッショントークンから user + tenant を返す。無効なら None。"""
        if not raw_token:
            return None
        self.initialize()
        now = _now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT s.id AS session_id, s.expires_at, s.revoked_at, u.*"
                " FROM auth_sessions s JOIN users u ON u.id = s.user_id"
                " WHERE s.token_hash = ?",
                (_hash_token(raw_token),),
            ).fetchone()
            if row is None or row["revoked_at"] or not row["is_active"]:
                return None
            if datetime.fromisoformat(row["expires_at"]) <= now:
                return None
            tenant = conn.execute(
                "SELECT * FROM tenants WHERE id = ?", (row["tenant_id"],)
            ).fetchone()
            if tenant is None:
                return None
            conn.execute(
                "UPDATE auth_sessions SET last_seen_at = ? WHERE id = ?",
                (_iso(now), row["session_id"]),
            )
            user = self._public_user(row)
            for extra in ("session_id", "expires_at", "revoked_at"):
                user.pop(extra, None)
            return {"user": user, "tenant": dict(tenant)}

    def revoke_session(self, raw_token: str) -> None:
        if not raw_token:
            return
        with self._transaction() as conn:
            conn.execute(
                "UPDATE auth_sessions SET revoked_at = ? WHERE token_hash = ?",
                (_iso(_now()), _hash_token(raw_token)),
            )

    # --- API トークン（/api/v1 用） ------------------------------------

    def create_api_token(self, tenant_id: str, name: str, created_by: str = "") -> dict:
        name = name.strip() or "api-token"
        raw = f"ws2d_{secrets.token_urlsafe(32)}"
        now = _iso(_now())
        token_id = uuid.uuid4().hex
        with self._transaction() as conn:
            if conn.execute("SELECT 1 FROM tenants WHERE id = ?", (tenant_id,)).fetchone() is None:
                raise AuthError("テナントが存在しません。", "tenant_not_found")
            conn.execute(
                "INSERT INTO api_tokens (id, tenant_id, name, token_hash, created_by, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (token_id, tenant_id, name, _hash_token(raw), created_by or None, now),
            )
        self.audit(
            "api_token.created", user_id=created_by or None, tenant_id=tenant_id, detail=name
        )
        # 平文トークンはこの戻り値でのみ返す（保存しない）
        return {"id": token_id, "name": name, "token": raw, "created_at": now}

    def resolve_api_token(self, raw_token: str) -> dict | None:
        if not raw_token:
            return None
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT t.id AS token_id, t.revoked_at, ten.*"
                " FROM api_tokens t JOIN tenants ten ON ten.id = t.tenant_id"
                " WHERE t.token_hash = ?",
                (_hash_token(raw_token),),
            ).fetchone()
            if row is None or row["revoked_at"]:
                return None
            conn.execute(
                "UPDATE api_tokens SET last_used_at = ? WHERE id = ?",
                (_iso(_now()), row["token_id"]),
            )
            tenant = dict(row)
            tenant.pop("token_id", None)
            tenant.pop("revoked_at", None)
            return tenant

    def list_api_tokens(self, tenant_id: str) -> list[dict]:
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, created_by, created_at, last_used_at, revoked_at"
                " FROM api_tokens WHERE tenant_id = ? ORDER BY created_at",
                (tenant_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def revoke_api_token(self, token_id: str, tenant_id: str, actor_id: str = "") -> bool:
        with self._transaction() as conn:
            cur = conn.execute(
                "UPDATE api_tokens SET revoked_at = ?"
                " WHERE id = ? AND tenant_id = ? AND revoked_at IS NULL",
                (_iso(_now()), token_id, tenant_id),
            )
            changed = cur.rowcount > 0
        if changed:
            self.audit(
                "api_token.revoked", user_id=actor_id or None, tenant_id=tenant_id, detail=token_id
            )
        return changed


def is_admin_role(role: str) -> bool:
    return role in _ADMIN_ROLES


_STORE: AuthStore | None = None
_STORE_KEY: str | None = None
_STORE_LOCK = threading.Lock()

AUTH_DB_ENV = "WEBSPEC2DOC_AUTH_DB"
DEFAULT_AUTH_DB = "instance/auth.db"


def get_auth_store() -> AuthStore:
    """認証DBストアのシングルトン。テストで環境変数を切り替えても追従する。"""
    global _STORE, _STORE_KEY
    key = os.environ.get(AUTH_DB_ENV, DEFAULT_AUTH_DB)
    if _STORE is not None and _STORE_KEY == key:
        return _STORE
    with _STORE_LOCK:
        if _STORE is None or _STORE_KEY != key:
            _STORE = AuthStore(Path(key))
            _STORE_KEY = key
        return _STORE
