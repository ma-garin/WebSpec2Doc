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
import logging
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

from web.services.admin_audit import append_admin_audit

SCHEMA_VERSION = 4

# ロールはユーザーではなく所属（memberships）が持つ。値は「一般」「管理者」の2つ。
# 同じ人がテナントAでは一般、テナントBでは管理者、という持ち方を可能にするため。
ROLE_MEMBER = "member"
ROLE_ADMIN = "admin"
ROLES = (ROLE_MEMBER, ROLE_ADMIN)
ROLE_LABELS = {ROLE_MEMBER: "一般", ROLE_ADMIN: "管理者"}
# v3以前の owner は admin に統合した。旧APIからの入力は読み替えて受け付ける。
_LEGACY_ROLE_ALIASES = {"owner": ROLE_ADMIN}
_ADMIN_ROLES = frozenset({ROLE_ADMIN})

# ロックアウト: MAX_FAILED_ATTEMPTS 回連続で失敗すると LOCK_MINUTES 分ロック
MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15

# セッション有効期間（時間）。環境変数で上書き可能
SESSION_HOURS_ENV = "WEBSPEC2DOC_SESSION_HOURS"
DEFAULT_SESSION_HOURS = 12

MIN_PASSWORD_LENGTH = 10

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# ログインIDはメールアドレスに限らない。初期管理者の "admin" のような
# 短い識別子も受け付ける（社内モックで配る資格情報のため）。
_LOGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")

# テナント行に添えるメンバー数。相関サブクエリなので外側の別名 t に依存する。
_MEMBER_COUNT_SUBQUERY = "(SELECT COUNT(*) FROM memberships mc WHERE mc.tenant_id = t.id)"

# 初期管理者。ユーザーが1人も居ないサーバーを起動したときに作られる。
INITIAL_ADMIN_LOGIN_ID = "admin"
INITIAL_ADMIN_PASSWORD = "password"  # nosec B105 - 社内モック用の既定資格情報
INITIAL_ADMIN_NAME = "管理者"
INITIAL_TENANT_NAME = "既定のテナント"
INITIAL_TENANT_SLUG = "default"

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """認証・アカウント操作の業務エラー。code はUI/新テストで分岐に使う。"""

    def __init__(self, message: str, code: str = "error") -> None:
        super().__init__(message)
        self.code = code


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


SCOPE_READ = "read"
SCOPE_FULL = "full"
API_TOKEN_SCOPES = (SCOPE_READ, SCOPE_FULL)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def slugify_tenant_name(name: str) -> str:
    """テナント名からファイルシステム安全な slug を作る（英数とハイフンのみ）。"""
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")[:24]
    if not slug or not _SLUG_RE.match(slug):
        slug = "tenant"
    return slug


def valid_login_id(value: str) -> bool:
    """ログインIDとして使えるか。メールアドレス、または英数字の識別子を許可する。"""
    return bool(_EMAIL_RE.match(value) or _LOGIN_ID_RE.match(value))


def normalize_role(role: str) -> str:
    """旧ロール名（owner）を現行の2ロールへ畳む。未知の値は例外にする。"""
    value = (role or "").strip().lower()
    value = _LEGACY_ROLE_ALIASES.get(value, value)
    if value not in ROLES:
        raise AuthError("不正なロールです。", "invalid_role")
    return value


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
            conn.executescript("""
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
                """)
        if version < 2:
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(users)").fetchall()}
            if "tour_completed_at" not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN tour_completed_at TEXT")
            conn.execute("PRAGMA user_version = 2")
        if version < 3:
            columns = {
                str(row[1]) for row in conn.execute("PRAGMA table_info(api_tokens)").fetchall()
            }
            if "scope" not in columns:
                # 既存トークンは従来どおり全操作可（後方互換）。新規は明示指定させる。
                conn.execute(
                    f"ALTER TABLE api_tokens ADD COLUMN scope TEXT NOT NULL DEFAULT '{SCOPE_FULL}'"
                )
            conn.execute("PRAGMA user_version = 3")
        if version < 4:
            self._migrate_v4(conn)

    @staticmethod
    def _migrate_v4(conn: sqlite3.Connection) -> None:
        """1ユーザー=1テナントを解き、所属を memberships テーブルへ移す。

        users から tenant_id / role を落とし、password_hash を空文字許容にする
        （パスワード未設定 = モック認証で使うユーザー）。SQLite は列を削除できない
        ため、テーブルを作り直して移し替える。
        """
        session_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(auth_sessions)").fetchall()
        }
        if "tenant_id" not in session_columns:
            conn.execute("ALTER TABLE auth_sessions ADD COLUMN tenant_id TEXT")
        # users を差し替える間、参照している auth_sessions が壊れないよう外部キーを外す。
        # PRAGMA foreign_keys はトランザクション内では変更できないため、外側で切り替える。
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            conn.executescript("""
                BEGIN;
                CREATE TABLE IF NOT EXISTS memberships (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    role TEXT NOT NULL CHECK(role IN ('member','admin')),
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, tenant_id)
                );
                INSERT OR IGNORE INTO memberships (id, user_id, tenant_id, role, created_at)
                    SELECT lower(hex(randomblob(16))), id, tenant_id,
                           CASE WHEN role IN ('owner','admin') THEN 'admin' ELSE 'member' END,
                           created_at
                    FROM users;
                CREATE TABLE users_v4 (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL DEFAULT '',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    failed_attempts INTEGER NOT NULL DEFAULT 0,
                    locked_until TEXT,
                    last_login_at TEXT,
                    tour_completed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                INSERT INTO users_v4 (id, email, name, password_hash, is_active,
                                      failed_attempts, locked_until, last_login_at,
                                      tour_completed_at, created_at, updated_at)
                    SELECT id, email, name, password_hash, is_active,
                           failed_attempts, locked_until, last_login_at,
                           tour_completed_at, created_at, updated_at
                    FROM users;
                DROP TABLE users;
                ALTER TABLE users_v4 RENAME TO users;
                CREATE INDEX IF NOT EXISTS ix_memberships_user ON memberships(user_id);
                CREATE INDEX IF NOT EXISTS ix_memberships_tenant ON memberships(tenant_id);
                PRAGMA user_version = 4;
                COMMIT;
                """)
        finally:
            conn.execute("PRAGMA foreign_keys = ON")

    # --- 監査ログ -----------------------------------------------------

    def audit(
        self,
        event: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
        detail: str = "",
        *,
        actor_email: str = "",
        tenant_slug: str = "",
        target_type: str = "",
        target_id: str = "",
        outcome: str = "success",
    ) -> None:
        """監査ログを1件残す。

        tenant_slug / actor_email は呼び出し元が既に持っていれば渡す。渡されない
        ときだけ追加のクエリで引く（監査は全更新操作で走るため、既知の値を
        毎回引き直さない）。
        """
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO audit_log (at, event, user_id, tenant_id, detail)"
                " VALUES (?, ?, ?, ?, ?)",
                (_iso(_now()), event, user_id, tenant_id, detail[:500]),
            )
        slug = tenant_slug
        if not slug and tenant_id:
            tenant = self.get_tenant(tenant_id)
            slug = str(tenant["slug"]) if tenant else ""
        email = actor_email
        if not email and user_id:
            actor = self.get_user(user_id)
            email = str((actor or {}).get("email", ""))
        path = self.db_path.parent / "admin_audit.jsonl"
        if slug:
            path = self.db_path.parent / "tenants" / slug / "admin_audit.jsonl"
        try:
            append_admin_audit(
                path,
                action=event,
                actor_id=user_id or "",
                actor_email=email,
                target_type=target_type,
                target_id=target_id,
                outcome=outcome,
                detail={"summary": detail[:500]} if detail else {},
            )
        except OSError as exc:
            logger.warning("管理監査ログの保存に失敗しました: event=%s error=%s", event, exc)

    # --- テナント -----------------------------------------------------

    def create_tenant(self, name: str, slug: str = "", *, actor_id: str = "") -> dict:
        name = name.strip()
        if not name:
            raise AuthError("テナント名を入力してください。", "invalid_input")
        requested = (slug or "").strip().lower()
        if requested and not _SLUG_RE.match(requested):
            raise AuthError(
                "slug は英小文字・数字・ハイフンで、32文字以内にしてください。", "invalid_slug"
            )
        base_slug = requested or slugify_tenant_name(name)
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
            created = {"id": tenant_id, "name": name, "slug": slug}
        if actor_id:
            self.audit(
                "tenant.created",
                user_id=actor_id,
                tenant_id=tenant_id,
                tenant_slug=slug,
                detail=name,
                target_type="tenant",
                target_id=tenant_id,
            )
        return created

    def get_tenant(self, tenant_id: str) -> dict | None:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
            return dict(row) if row else None

    def list_tenants(self) -> list[dict]:
        """全テナントとメンバー数（管理画面用）。"""
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT t.*, {_MEMBER_COUNT_SUBQUERY} AS member_count"  # nosec B608
                " FROM tenants t ORDER BY t.created_at"
            ).fetchall()
        return [dict(row) for row in rows]

    def rename_tenant(self, tenant_id: str, name: str, *, actor_id: str = "") -> dict:
        name = name.strip()
        if not name:
            raise AuthError("テナント名を入力してください。", "invalid_input")
        with self._transaction() as conn:
            cursor = conn.execute(
                "UPDATE tenants SET name = ?, updated_at = ? WHERE id = ?",
                (name, _iso(_now()), tenant_id),
            )
            if cursor.rowcount == 0:
                raise AuthError("テナントが存在しません。", "tenant_not_found")
        renamed = self.get_tenant(tenant_id) or {}
        self.audit(
            "tenant.renamed",
            user_id=actor_id or None,
            tenant_id=tenant_id,
            tenant_slug=str(renamed.get("slug", "")),
            detail=name,
            target_type="tenant",
            target_id=tenant_id,
        )
        return renamed

    def delete_tenant(self, tenant_id: str, *, actor_id: str = "") -> dict:
        """テナントと、その所属・APIトークンを削除する。

        出力ディレクトリ（output/tenants/{slug}）は削除しない。生成物を
        DB操作の巻き添えで失わせないため、ファイルの後始末は運用側に残す。
        """
        tenant = self.get_tenant(tenant_id)
        if tenant is None:
            raise AuthError("テナントが存在しません。", "tenant_not_found")
        with self._transaction() as conn:
            remaining = int(conn.execute("SELECT COUNT(*) FROM tenants").fetchone()[0])
            if remaining <= 1:
                raise AuthError(
                    "最後のテナントは削除できません。先に別のテナントを作成してください。",
                    "last_tenant",
                )
            conn.execute("DELETE FROM memberships WHERE tenant_id = ?", (tenant_id,))
            conn.execute("DELETE FROM api_tokens WHERE tenant_id = ?", (tenant_id,))
            conn.execute(
                "UPDATE auth_sessions SET tenant_id = NULL WHERE tenant_id = ?", (tenant_id,)
            )
            conn.execute("DELETE FROM tenants WHERE id = ?", (tenant_id,))
        self.audit(
            "tenant.deleted",
            user_id=actor_id or None,
            # 削除済みなので tenant_id で引き直せない。slug は手元の行から渡す
            tenant_slug=str(tenant["slug"]),
            detail=f"{tenant['name']} (slug={tenant['slug']})",
            target_type="tenant",
            target_id=tenant_id,
        )
        return tenant

    # --- ユーザー -----------------------------------------------------

    def has_any_user(self) -> bool:
        self.initialize()
        with self._connect() as conn:
            return conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def create_user(
        self,
        tenant_id: str | None = None,
        email: str = "",
        name: str = "",
        password: str = "",
        role: str = ROLE_MEMBER,
        *,
        actor_id: str = "",
        enforce_password_policy: bool = True,
    ) -> dict:
        """ユーザーを作る。

        tenant_id を渡すとその所属も同時に作る。None なら所属なしで作成し、
        管理者が割り当てるまで待機状態になる（本人によるサインアップの経路）。
        password が空文字ならパスワード未設定として作る（モック認証で使う）。
        email はメールアドレスのほか、"admin" のような識別子も受け付ける。
        """
        email = email.strip().lower()
        name = name.strip()
        if not valid_login_id(email):
            raise AuthError(
                "ログインIDはメールアドレス、または英数字（2文字以上）で指定してください。",
                "invalid_email",
            )
        if not name:
            raise AuthError("表示名を入力してください。", "invalid_input")
        role = normalize_role(role)
        password_hash = ""
        if password:
            if enforce_password_policy:
                validate_password(password, email)
            password_hash = generate_password_hash(password)
        with self._transaction() as conn:
            if (
                tenant_id
                and conn.execute("SELECT 1 FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
                is None
            ):
                raise AuthError("テナントが存在しません。", "tenant_not_found")
            if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                raise AuthError("このメールアドレスは既に登録されています。", "email_taken")
            now = _iso(_now())
            user_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO users (id, email, name, password_hash, is_active,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
                (user_id, email, name, password_hash, now, now),
            )
            if tenant_id:
                conn.execute(
                    "INSERT INTO memberships (id, user_id, tenant_id, role, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (uuid.uuid4().hex, user_id, tenant_id, role, now),
                )
        user = self.get_user(user_id) or {}
        if tenant_id:
            user["role"] = role
        self.audit(
            "user.created",
            user_id=actor_id or user_id,
            tenant_id=tenant_id,
            detail=email,
            target_type="user",
            target_id=user_id,
        )
        return user

    def setup_initial(
        self,
        tenant_name: str,
        email: str,
        name: str,
        password: str = "",
        *,
        enforce_password_policy: bool = True,
    ) -> dict:
        """初期セットアップ: 最初のテナントと管理者を作る（ユーザーが1人でも居れば拒否）。"""
        if self.has_any_user():
            raise AuthError("初期セットアップは完了済みです。", "already_setup")
        tenant = self.create_tenant(tenant_name)
        user = self.create_user(
            tenant["id"],
            email,
            name,
            password,
            role=ROLE_ADMIN,
            enforce_password_policy=enforce_password_policy,
        )
        self.audit("tenant.created", user_id=user["id"], tenant_id=tenant["id"], detail=tenant_name)
        return {"tenant": tenant, "user": user}

    def ensure_initial_admin(self) -> dict | None:
        """ユーザーが1人も居なければ初期管理者と既定テナントを作る。

        既にユーザーが居れば何もしない（既存環境のパスワードを上書きしない）。
        サーバー起動時にだけ呼ぶ。import しただけのテストでは走らせない。
        """
        if self.has_any_user():
            return None
        tenant = self.create_tenant(INITIAL_TENANT_NAME, INITIAL_TENANT_SLUG)
        user = self.create_user(
            tenant["id"],
            INITIAL_ADMIN_LOGIN_ID,
            INITIAL_ADMIN_NAME,
            INITIAL_ADMIN_PASSWORD,
            role=ROLE_ADMIN,
            # 既定資格情報は配布用の短い文字列なので、長さ要件は課さない
            enforce_password_policy=False,
        )
        self.audit(
            "tenant.created",
            user_id=user["id"],
            tenant_id=tenant["id"],
            detail=f"{INITIAL_TENANT_NAME}（初期セットアップ）",
        )
        logger.info(
            "初期管理者を作成しました: ログインID=%s / 既定テナント=%s",
            INITIAL_ADMIN_LOGIN_ID,
            tenant["slug"],
        )
        return {"tenant": tenant, "user": user}

    def get_user(self, user_id: str) -> dict | None:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return self._public_user(row) if row else None

    def list_users(self, tenant_id: str) -> list[dict]:
        """指定テナントに所属するユーザー（role はそのテナントでのロール）。"""
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT u.*, m.role AS role FROM users u"
                " JOIN memberships m ON m.user_id = u.id"
                " WHERE m.tenant_id = ? ORDER BY u.created_at",
                (tenant_id,),
            ).fetchall()
            return [self._public_user(r) for r in rows]

    def list_all_users(self) -> list[dict]:
        """全ユーザーと所属テナント一覧（管理画面用）。所属なしのユーザーも含む。"""
        self.initialize()
        with self._connect() as conn:
            users = conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
            membership_rows = conn.execute(
                "SELECT m.user_id, t.id AS tenant_id, t.name, t.slug, m.role"
                " FROM memberships m JOIN tenants t ON t.id = m.tenant_id"
                " ORDER BY t.name"
            ).fetchall()
        grouped: dict[str, list[dict]] = {}
        for row in membership_rows:
            grouped.setdefault(str(row["user_id"]), []).append(
                {
                    "tenant_id": row["tenant_id"],
                    "name": row["name"],
                    "slug": row["slug"],
                    "role": row["role"],
                }
            )
        result = []
        for row in users:
            public = self._public_user(row)
            public["memberships"] = grouped.get(str(row["id"]), [])
            public["has_password"] = bool(row["password_hash"])
            result.append(public)
        return result

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
        """テナント内のロール変更と、アカウントの有効/無効化。

        role は「そのテナントでの所属ロール」を変える。is_active はユーザー本体の
        有効/無効で全テナントに効く。最後の管理者の降格・無効化は拒否する。
        """
        if role is not None:
            role = normalize_role(role)
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT u.*, m.role AS role FROM users u"
                " JOIN memberships m ON m.user_id = u.id"
                " WHERE u.id = ? AND m.tenant_id = ?",
                (user_id, tenant_id),
            ).fetchone()
            if row is None:
                raise AuthError("ユーザーが存在しません。", "user_not_found")
            current_role = str(row["role"])
            demoting = role is not None and role != ROLE_ADMIN and current_role == ROLE_ADMIN
            deactivating = is_active is False and bool(row["is_active"])
            if current_role == ROLE_ADMIN and (demoting or deactivating):
                self._assert_admin_remains(conn, tenant_id, user_id)
            now = _iso(_now())
            if role is not None:
                conn.execute(
                    "UPDATE memberships SET role = ? WHERE user_id = ? AND tenant_id = ?",
                    (role, user_id, tenant_id),
                )
            if is_active is not None:
                conn.execute(
                    "UPDATE users SET is_active = ?, failed_attempts = 0, locked_until = NULL,"
                    " updated_at = ? WHERE id = ?",
                    (1 if is_active else 0, now, user_id),
                )
                if not is_active:
                    # 無効化したユーザーの既存セッションは即座に失効させる
                    conn.execute(
                        "UPDATE auth_sessions SET revoked_at = ? WHERE user_id = ?", (now, user_id)
                    )
        updated_user = self.get_user(user_id) or {}
        updated_user["role"] = role or current_role
        self.audit(
            "user.updated",
            user_id=actor_id or None,
            tenant_id=tenant_id,
            detail=(
                f"target={user_id} email={updated_user.get('email', '')} "
                f"role={role} is_active={is_active}"
            ),
            target_type="user",
            target_id=user_id,
        )
        return updated_user

    def set_user_active(self, user_id: str, is_active: bool, *, actor_id: str = "") -> dict:
        """アカウントの有効/無効を切り替える（全テナントに効く）。

        is_active は users 本体の列なので、所属テナントごとに繰り返し更新しない。
        無効化するときだけ、管理者が0人になるテナントが出ないか確かめる。
        """
        with self._transaction() as conn:
            row = conn.execute("SELECT is_active FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                raise AuthError("ユーザーが存在しません。", "user_not_found")
            if not is_active and bool(row["is_active"]):
                self._guard_last_admin_removal(conn, user_id, keeping_admin=set())
            now = _iso(_now())
            conn.execute(
                "UPDATE users SET is_active = ?, failed_attempts = 0, locked_until = NULL,"
                " updated_at = ? WHERE id = ?",
                (1 if is_active else 0, now, user_id),
            )
            if not is_active:
                # 無効化したユーザーの既存セッションは即座に失効させる
                conn.execute(
                    "UPDATE auth_sessions SET revoked_at = ? WHERE user_id = ?", (now, user_id)
                )
        updated_user = self.get_user(user_id) or {}
        self.audit(
            "user.updated",
            user_id=actor_id or None,
            detail=f"target={user_id} email={updated_user.get('email', '')} is_active={is_active}",
            target_type="user",
            target_id=user_id,
        )
        return updated_user

    def delete_user(self, user_id: str, *, actor_id: str = "") -> None:
        """ユーザーを削除する。所属とセッションも併せて消す。"""
        with self._transaction() as conn:
            row = conn.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                raise AuthError("ユーザーが存在しません。", "user_not_found")
            self._guard_last_admin_removal(conn, user_id, set())
            conn.execute("DELETE FROM memberships WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            email = str(row["email"])
        self.audit(
            "user.deleted",
            user_id=actor_id or None,
            detail=email,
            target_type="user",
            target_id=user_id,
        )

    # --- 所属（memberships） -------------------------------------------

    def list_memberships(self, user_id: str) -> list[dict]:
        """このユーザーが所属するテナントと、そこでのロール。"""
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT t.id AS tenant_id, t.name, t.slug, m.role,"  # nosec B608
                f" {_MEMBER_COUNT_SUBQUERY} AS member_count"
                " FROM memberships m JOIN tenants t ON t.id = m.tenant_id"
                " WHERE m.user_id = ? ORDER BY t.name",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def membership_role(self, user_id: str, tenant_id: str) -> str | None:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT role FROM memberships WHERE user_id = ? AND tenant_id = ?",
                (user_id, tenant_id),
            ).fetchone()
        return str(row["role"]) if row is not None else None

    def set_memberships(
        self, user_id: str, entries: list[dict], *, actor_id: str = ""
    ) -> list[dict]:
        """所属を一括置換する（管理画面の「所属を編集」）。空リストなら所属なしにする。"""
        normalized: list[tuple[str, str]] = []
        seen: set[str] = set()
        for entry in entries:
            tenant_id = str(entry.get("tenant_id", "")).strip()
            if not tenant_id or tenant_id in seen:
                continue
            seen.add(tenant_id)
            normalized.append((tenant_id, normalize_role(str(entry.get("role", ROLE_MEMBER)))))
        with self._transaction() as conn:
            if conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None:
                raise AuthError("ユーザーが存在しません。", "user_not_found")
            for tenant_id, _role in normalized:
                if (
                    conn.execute("SELECT 1 FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
                    is None
                ):
                    raise AuthError("テナントが存在しません。", "tenant_not_found")
            keeping_admin = {t for t, role in normalized if role == ROLE_ADMIN}
            self._guard_last_admin_removal(conn, user_id, keeping_admin)
            conn.execute("DELETE FROM memberships WHERE user_id = ?", (user_id,))
            now = _iso(_now())
            for tenant_id, role in normalized:
                conn.execute(
                    "INSERT INTO memberships (id, user_id, tenant_id, role, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (uuid.uuid4().hex, user_id, tenant_id, role, now),
                )
            # 所属から外れたテナントを選択中のセッションは、選択を解除して選び直させる
            conn.execute(
                "UPDATE auth_sessions SET tenant_id = NULL"
                " WHERE user_id = ? AND tenant_id IS NOT NULL AND tenant_id NOT IN"
                " (SELECT tenant_id FROM memberships WHERE user_id = ?)",
                (user_id, user_id),
            )
        self.audit(
            "membership.updated",
            user_id=actor_id or None,
            detail=f"target={user_id} tenants={len(normalized)}",
            target_type="user",
            target_id=user_id,
        )
        return self.list_memberships(user_id)

    @staticmethod
    def _assert_admin_remains(
        conn: sqlite3.Connection, tenant_id: str, excluding_user_id: str
    ) -> None:
        """「テナントの管理者を0人にしない」という不変条件。

        降格・無効化・所属解除・削除のいずれも、対象ユーザーを除いた残りに
        有効な管理者が居るかどうかで判定できるので、ここに一本化する。
        """
        others = int(
            conn.execute(
                "SELECT COUNT(*) FROM memberships m JOIN users u ON u.id = m.user_id"
                " WHERE m.tenant_id = ? AND m.role = ? AND m.user_id != ? AND u.is_active = 1",
                (tenant_id, ROLE_ADMIN, excluding_user_id),
            ).fetchone()[0]
        )
        if others == 0:
            raise AuthError(
                "テナントの管理者が0人になるため、この操作はできません。"
                "先に別のユーザーを管理者にしてください。",
                "last_admin",
            )

    @classmethod
    def _guard_last_admin_removal(
        cls, conn: sqlite3.Connection, user_id: str, keeping_admin: set[str]
    ) -> None:
        """このユーザーが管理者を降りるテナントすべてで、管理者が残るか確かめる。"""
        rows = conn.execute(
            "SELECT tenant_id FROM memberships WHERE user_id = ? AND role = ?",
            (user_id, ROLE_ADMIN),
        ).fetchall()
        for row in rows:
            tenant_id = str(row["tenant_id"])
            if tenant_id not in keeping_admin:
                cls._assert_admin_remains(conn, tenant_id, user_id)

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
        failed_user_id: str | None = None
        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if row is not None:
                failed_user_id = str(row["id"])
            locked_until = row["locked_until"] if row is not None else None
            if row is None:
                # ユーザー有無でレスポンス時間差を作らないためダミー検証を行う
                check_password_hash(generate_password_hash("dummy-password"), password)
                error = AuthError(
                    "メールアドレスまたはパスワードが正しくありません。", "invalid_credentials"
                )
            elif not row["is_active"]:
                error = AuthError("このアカウントは無効化されています。", "inactive")
            elif not row["password_hash"]:
                error = AuthError(
                    "このアカウントはパスワードが設定されていません。"
                    "メールアドレスだけでログインしてください。",
                    "no_password",
                )
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
            self.audit(
                "user.login",
                user_id=failed_user_id,
                tenant_id=self._sole_tenant_id(failed_user_id),
                actor_email=email,
                target_type="user",
                target_id=failed_user_id or "unknown",
                outcome="failure",
            )
            raise error or AuthError("認証に失敗しました。", "invalid_credentials")
        self.audit(
            "user.login",
            user_id=user["id"],
            tenant_id=self._sole_tenant_id(user["id"]),
            target_type="user",
            target_id=user["id"],
        )
        return user

    def _sole_tenant_id(self, user_id: str | None) -> str | None:
        """所属が1件だけならその ID。0件・複数件は None。

        ログインはテナントを選ぶ前の出来事なので、テナント別の監査ログに落とせるのは
        所属が一意に決まるときだけ。複数所属の場合はテナント選択時に別途記録する。
        """
        if not user_id:
            return None
        memberships = self.list_memberships(user_id)
        return str(memberships[0]["tenant_id"]) if len(memberships) == 1 else None

    def authenticate_passwordless(self, email: str) -> dict:
        """モック認証: メールアドレスだけでログインする（社内モック用）。

        パスワードを設定済みのユーザーはこの経路では通さない。モックを有効にした
        だけで、パスワードで守っていたアカウントが素通りになるのを防ぐため。
        """
        email = (email or "").strip().lower()
        self.initialize()
        now = _iso(_now())
        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if row is None:
                raise AuthError(
                    "このメールアドレスのユーザーは登録されていません。", "unknown_user"
                )
            if not row["is_active"]:
                raise AuthError("このアカウントは無効化されています。", "inactive")
            if row["password_hash"]:
                raise AuthError(
                    "このアカウントはパスワードが必要です。", "password_required"
                )
            conn.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = NULL,"
                " last_login_at = ?, updated_at = ? WHERE id = ?",
                (now, now, row["id"]),
            )
            user = self._public_user(row)
        self.audit(
            "user.login",
            user_id=user["id"],
            tenant_id=self._sole_tenant_id(user["id"]),
            detail="passwordless",
            target_type="user",
            target_id=user["id"],
        )
        return user

    def switch_session_user(self, raw_token: str, user_id: str) -> str | None:
        """セッションを別ユーザーへ切り替える（モックのユーザー選択画面）。

        切り替え先はパスワード未設定の有効ユーザーに限る。パスワードで守られた
        アカウントを、選ぶだけで乗っ取れないようにするため。
        戻り値は新しいセッショントークン。切り替え不可なら None。
        """
        if not raw_token or not user_id:
            return None
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, password_hash, is_active FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        if row is None or not row["is_active"] or row["password_hash"]:
            return None
        self.revoke_session(raw_token)
        token = self.create_session(user_id)
        self.audit(
            "user.switched",
            user_id=user_id,
            detail="mock user selection",
            target_type="user",
            target_id=user_id,
        )
        return token

    def list_login_candidates(self, limit: int = 20) -> list[dict]:
        """モックのユーザー選択画面に並べる、パスワード未設定の有効ユーザー。"""
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT u.id, u.email, u.name,"
                " (SELECT COUNT(*) FROM memberships m WHERE m.user_id = u.id) AS tenant_count,"
                " (SELECT COUNT(*) FROM memberships m WHERE m.user_id = u.id AND m.role = ?)"
                "   AS admin_count"
                " FROM users u WHERE u.is_active = 1 AND u.password_hash = ''"
                " ORDER BY u.created_at LIMIT ?",
                (ROLE_ADMIN, max(1, min(limit, 50))),
            ).fetchall()
        return [dict(row) for row in rows]

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
        self.audit("user.password_changed", user_id=user_id)

    # --- セッション ---------------------------------------------------

    def find_active_user_by_email(self, email: str) -> dict | None:
        """SSOログイン用の利用者照合。無効化済みの利用者は返さない。"""
        self.initialize()
        normalized = email.strip().lower()
        if not normalized:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE lower(email) = ? AND is_active = 1",
                (normalized,),
            ).fetchone()
        return self._public_user(row) if row is not None else None

    def create_session(self, user_id: str, tenant_id: str | None = None) -> str:
        """セッションを発行する。tenant_id は未選択なら None（テナント選択画面へ送る）。"""
        raw = secrets.token_urlsafe(32)
        now = _now()
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO auth_sessions (id, user_id, token_hash, created_at,"
                " expires_at, last_seen_at, tenant_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    uuid.uuid4().hex,
                    user_id,
                    _hash_token(raw),
                    _iso(now),
                    _iso(now + timedelta(hours=session_hours())),
                    _iso(now),
                    tenant_id,
                ),
            )
        return raw

    def bind_session_tenant(self, raw_token: str, tenant_id: str) -> bool:
        """テナント選択の結果をセッションへ結び付ける。所属していなければ False。"""
        if not raw_token or not tenant_id:
            return False
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT id AS session_id, user_id FROM auth_sessions"
                " WHERE token_hash = ? AND revoked_at IS NULL",
                (_hash_token(raw_token),),
            ).fetchone()
            if row is None:
                return False
            member = conn.execute(
                "SELECT 1 FROM memberships WHERE user_id = ? AND tenant_id = ?",
                (row["user_id"], tenant_id),
            ).fetchone()
            if member is None:
                return False
            conn.execute(
                "UPDATE auth_sessions SET tenant_id = ? WHERE id = ?",
                (tenant_id, row["session_id"]),
            )
        return True

    def resolve_session(self, raw_token: str) -> dict | None:
        """セッショントークンから user + tenant を返す。無効なら None。

        テナント未選択のセッションは tenant=None で返す。ログイン済みかどうかと、
        作業するテナントが決まっているかどうかは別の状態なので分けて扱う。
        """
        if not raw_token:
            return None
        self.initialize()
        now = _now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT s.id AS session_id, s.expires_at, s.revoked_at,"
                " s.tenant_id AS session_tenant_id, u.*"
                " FROM auth_sessions s JOIN users u ON u.id = s.user_id"
                " WHERE s.token_hash = ?",
                (_hash_token(raw_token),),
            ).fetchone()
            if row is None or row["revoked_at"] or not row["is_active"]:
                return None
            if datetime.fromisoformat(row["expires_at"]) <= now:
                return None
            tenant: dict | None = None
            role: str | None = None
            session_tenant_id = row["session_tenant_id"]
            if session_tenant_id:
                # テナントと所属ロールを1クエリで取る。auth_guard から毎リクエスト
                # 呼ばれるため、同じ条件のクエリを2回に分けない。
                # JOIN が空 = テナント削除済み、または所属解除済み。未選択として扱い、
                # 選び直させる。
                tenant_row = conn.execute(
                    "SELECT t.*, m.role AS membership_role FROM tenants t"
                    " JOIN memberships m ON m.tenant_id = t.id AND m.user_id = ?"
                    " WHERE t.id = ?",
                    (row["id"], session_tenant_id),
                ).fetchone()
                if tenant_row is not None:
                    tenant = dict(tenant_row)
                    role = str(tenant.pop("membership_role"))
            conn.execute(
                "UPDATE auth_sessions SET last_seen_at = ? WHERE id = ?",
                (_iso(now), row["session_id"]),
            )
            user = self._public_user(row)
            for extra in ("session_id", "expires_at", "revoked_at", "session_tenant_id"):
                user.pop(extra, None)
            user["role"] = role
            return {"user": user, "tenant": tenant}

    def revoke_session(self, raw_token: str) -> None:
        if not raw_token:
            return
        with self._transaction() as conn:
            conn.execute(
                "UPDATE auth_sessions SET revoked_at = ? WHERE token_hash = ?",
                (_iso(_now()), _hash_token(raw_token)),
            )

    # --- API トークン（/api/v1 用） ------------------------------------

    def create_api_token(
        self, tenant_id: str, name: str, created_by: str = "", scope: str = SCOPE_FULL
    ) -> dict:
        name = name.strip() or "api-token"
        if scope not in API_TOKEN_SCOPES:
            raise AuthError(
                f"不正なスコープです: {scope}（利用可能: {', '.join(API_TOKEN_SCOPES)}）",
                "invalid_scope",
            )
        raw = f"ws2d_{secrets.token_urlsafe(32)}"
        now = _iso(_now())
        token_id = uuid.uuid4().hex
        with self._transaction() as conn:
            if conn.execute("SELECT 1 FROM tenants WHERE id = ?", (tenant_id,)).fetchone() is None:
                raise AuthError("テナントが存在しません。", "tenant_not_found")
            conn.execute(
                "INSERT INTO api_tokens"
                " (id, tenant_id, name, token_hash, created_by, created_at, scope)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (token_id, tenant_id, name, _hash_token(raw), created_by or None, now, scope),
            )
        self.audit(
            "api_token.created", user_id=created_by or None, tenant_id=tenant_id, detail=name
        )
        # 平文トークンはこの戻り値でのみ返す（保存しない）
        return {"id": token_id, "name": name, "token": raw, "created_at": now, "scope": scope}

    def resolve_api_token(self, raw_token: str) -> dict | None:
        if not raw_token:
            return None
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT t.id AS token_id, t.revoked_at, t.scope AS token_scope, ten.*"
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
            tenant["token_scope"] = str(tenant.pop("token_scope", SCOPE_FULL) or SCOPE_FULL)
            return tenant

    def list_api_tokens(self, tenant_id: str) -> list[dict]:
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, created_by, created_at, last_used_at, revoked_at, scope"
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
