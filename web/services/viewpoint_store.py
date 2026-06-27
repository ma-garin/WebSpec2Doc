from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
STANDARD_SET_NAME = "WebSpec2Doc標準観点"
ALLOWED_RULE_FIELDS = {
    "url",
    "industry",
    "screen_type",
    "input_type",
    "method",
    "tag",
    "has_forms",
}
ALLOWED_RULE_OPERATORS = {"eq", "ne", "contains", "starts_with", "in", "present"}
AUTOMATION_VALUES = {"automated", "semi_automated", "manual"}
VERSION_STATES = {"draft", "published", "archived"}
PROPOSAL_STATES = {"pending", "adopted", "rejected"}


class ViewpointStoreError(RuntimeError):
    status_code = 400

    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.details = details


class NotFoundError(ViewpointStoreError):
    status_code = 404


class ConflictError(ViewpointStoreError):
    status_code = 409


class ImmutableVersionError(ConflictError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _checksum(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _key_for(name: str, salt: str = "") -> str:
    digest = hashlib.sha1(f"{salt}:{name}".encode()).hexdigest()[:12]  # nosec B324
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:28]
    return f"{base or 'viewpoint'}-{digest}"


def _json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, dict | list | bool | int | float):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return default


def validate_rule(rule: Any, *, _depth: int = 0) -> dict[str, Any]:
    """許可済みフィールド・演算子だけで構成された条件式を返す。"""
    if rule in (None, "", {}):
        return {}
    if _depth > 4 or not isinstance(rule, dict) or len(rule) != 1:
        raise ViewpointStoreError("条件式は all/any または単一条件で指定してください。")
    key, value = next(iter(rule.items()))
    if key in {"all", "any"}:
        if not isinstance(value, list) or not value or len(value) > 50:
            raise ViewpointStoreError(f"{key} は1〜50件の条件配列で指定してください。")
        return {key: [validate_rule(item, _depth=_depth + 1) for item in value]}
    if key != "condition" or not isinstance(value, dict):
        raise ViewpointStoreError("任意コードは使用できません。condition を指定してください。")
    field = str(value.get("field", ""))
    operator = str(value.get("operator", ""))
    if field not in ALLOWED_RULE_FIELDS:
        raise ViewpointStoreError(f"許可されていない条件フィールドです: {field}")
    if operator not in ALLOWED_RULE_OPERATORS:
        raise ViewpointStoreError(f"許可されていない条件演算子です: {operator}")
    if operator != "present" and "value" not in value:
        raise ViewpointStoreError("条件値が必要です。")
    normalized: dict[str, Any] = {"field": field, "operator": operator}
    if operator != "present":
        normalized["value"] = value.get("value")
    return {"condition": normalized}


def rule_matches(rule: Any, context: dict[str, Any]) -> bool:
    normalized = validate_rule(rule)
    if not normalized:
        return True
    if "all" in normalized:
        return all(rule_matches(item, context) for item in normalized["all"])
    if "any" in normalized:
        return any(rule_matches(item, context) for item in normalized["any"])
    condition = normalized["condition"]
    actual = context.get(condition["field"])
    operator = condition["operator"]
    expected = condition.get("value")
    if operator == "present":
        return actual not in (None, "", [], {})
    if operator == "eq":
        return actual == expected
    if operator == "ne":
        return actual != expected
    if operator == "contains":
        if isinstance(actual, list | tuple | set):
            return expected in actual
        return str(expected).lower() in str(actual or "").lower()
    if operator == "starts_with":
        return str(actual or "").lower().startswith(str(expected).lower())
    if operator == "in":
        return isinstance(expected, list) and actual in expected
    return False


class ViewpointStoreBase:
    def __init__(self, db_path: Path, seed_csv: Path) -> None:
        self.db_path = Path(db_path)
        self.seed_csv = Path(seed_csv)
        self._init_lock = threading.Lock()
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._backup_before_migration()
            with self._connect() as conn:
                self._migrate(conn)
            self._initialized = True
            try:
                self._seed_standard_set()
            except Exception:
                self._initialized = False
                raise

    def _backup_before_migration(self) -> None:
        if not self.db_path.exists() or self.db_path.stat().st_size == 0:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        except sqlite3.DatabaseError:
            version = 0
        if version >= SCHEMA_VERSION:
            return
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        shutil.copy2(self.db_path, self.db_path.with_suffix(f".db.bak-{stamp}"))

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
            raise ViewpointStoreError("観点DBのスキーマがこのアプリより新しいため起動できません。")
        if version < 1:
            conn.executescript(
                """
                BEGIN;
                CREATE TABLE IF NOT EXISTS viewpoint_sets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    parent_set_id TEXT REFERENCES viewpoint_sets(id),
                    state TEXT NOT NULL DEFAULT 'active',
                    is_default INTEGER NOT NULL DEFAULT 0,
                    priority INTEGER NOT NULL DEFAULT 0,
                    revision INTEGER NOT NULL DEFAULT 1,
                    deleted_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS uq_viewpoint_set_name_active
                    ON viewpoint_sets(lower(name)) WHERE deleted_at IS NULL;
                CREATE TABLE IF NOT EXISTS viewpoint_versions (
                    id TEXT PRIMARY KEY,
                    set_id TEXT NOT NULL REFERENCES viewpoint_sets(id),
                    version_number INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('draft','published','archived')),
                    change_reason TEXT NOT NULL DEFAULT '',
                    checksum TEXT NOT NULL DEFAULT '',
                    based_on_version_id TEXT REFERENCES viewpoint_versions(id),
                    published_at TEXT,
                    revision INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(set_id, version_number)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS uq_viewpoint_draft
                    ON viewpoint_versions(set_id) WHERE status = 'draft';
                CREATE TABLE IF NOT EXISTS viewpoint_items (
                    id TEXT PRIMARY KEY,
                    version_id TEXT NOT NULL REFERENCES viewpoint_versions(id) ON DELETE CASCADE,
                    persistent_key TEXT NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    purpose TEXT NOT NULL DEFAULT '',
                    trigger_rule TEXT NOT NULL DEFAULT '{}',
                    recommended_checks TEXT NOT NULL DEFAULT '',
                    risk_weight INTEGER NOT NULL DEFAULT 3 CHECK(risk_weight BETWEEN 1 AND 5),
                    automation TEXT NOT NULL DEFAULT 'manual',
                    standards TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '[]',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    revision INTEGER NOT NULL DEFAULT 1,
                    deleted_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(version_id, persistent_key)
                );
                CREATE TABLE IF NOT EXISTS viewpoint_assignments (
                    id TEXT PRIMARY KEY,
                    set_id TEXT NOT NULL REFERENCES viewpoint_sets(id),
                    rule TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    revision INTEGER NOT NULL DEFAULT 1,
                    deleted_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS viewpoint_proposals (
                    id TEXT PRIMARY KEY,
                    set_id TEXT NOT NULL REFERENCES viewpoint_sets(id),
                    version_id TEXT REFERENCES viewpoint_versions(id),
                    payload TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
                    duplicate_key TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK(status IN ('pending','adopted','rejected')),
                    revision INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_viewpoint_items_version ON viewpoint_items(version_id);
                CREATE INDEX IF NOT EXISTS ix_viewpoint_versions_set ON viewpoint_versions(set_id, version_number DESC);
                PRAGMA user_version = 1;
                COMMIT;
                """
            )

    def _seed_standard_set(self) -> None:
        with self._transaction() as conn:
            exists = conn.execute(
                "SELECT 1 FROM viewpoint_sets WHERE name = ? LIMIT 1", (STANDARD_SET_NAME,)
            ).fetchone()
            if exists:
                return
            rows = self._read_seed_rows()
            if not rows:
                raise ViewpointStoreError("標準観点CSVが空か、読み込めません。")
            now = _now()
            set_id = uuid.uuid4().hex
            version_id = uuid.uuid4().hex
            conn.execute(
                """INSERT INTO viewpoint_sets
                   (id,name,description,state,is_default,priority,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    set_id,
                    STANDARD_SET_NAME,
                    "既存CSVから移行したWebSpec2Docの既定観点セット",
                    "active",
                    1,
                    100,
                    now,
                    now,
                ),
            )
            conn.execute(
                """INSERT INTO viewpoint_versions
                   (id,set_id,version_number,status,change_reason,checksum,published_at,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    version_id,
                    set_id,
                    1,
                    "published",
                    "初回CSV移行",
                    "",
                    now,
                    now,
                    now,
                ),
            )
            items: list[dict[str, Any]] = []
            for index, row in enumerate(rows, 1):
                item = self._normalize_import_row(row, index=index)
                items.append(item)
                self._insert_item(conn, version_id, item, now)
            checksum = self._items_checksum(items)
            conn.execute(
                "UPDATE viewpoint_versions SET checksum=? WHERE id=?",
                (checksum, version_id),
            )

    def _read_seed_rows(self) -> list[dict[str, str]]:
        try:
            with self.seed_csv.open("r", encoding="utf-8-sig", newline="") as handle:
                return list(csv.DictReader(handle))
        except OSError:
            return []

    def list_sets(self, *, include_deleted: bool = False) -> list[dict[str, Any]]:
        self.initialize()
        where = "" if include_deleted else "WHERE s.deleted_at IS NULL"
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT s.*,
                    (SELECT version_number FROM viewpoint_versions v
                     WHERE v.set_id=s.id AND v.status='published'
                     ORDER BY version_number DESC LIMIT 1) AS published_version,
                    (SELECT version_number FROM viewpoint_versions v
                     WHERE v.set_id=s.id AND v.status='draft' LIMIT 1) AS draft_version,
                    (SELECT COUNT(*) FROM viewpoint_items i JOIN viewpoint_versions v ON v.id=i.version_id
                     WHERE v.set_id=s.id AND v.status='published' AND i.deleted_at IS NULL AND i.enabled=1) AS item_count,
                    (SELECT COUNT(*) FROM viewpoint_assignments a
                     WHERE a.set_id=s.id AND a.deleted_at IS NULL AND a.enabled=1) AS assignment_count
                    FROM viewpoint_sets s {where}
                    ORDER BY s.is_default DESC, s.priority DESC, lower(s.name)"""
            ).fetchall()
        return [dict(row) for row in rows]

    def get_set(self, set_id: str, *, include_deleted: bool = False) -> dict[str, Any]:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM viewpoint_sets WHERE id=?", (set_id,)).fetchone()
        if row is None or (row["deleted_at"] and not include_deleted):
            raise NotFoundError("観点セットが見つかりません。")
        return dict(row)

    def create_set(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ViewpointStoreError("セット名は必須です。")
        parent_id = str(payload.get("parent_set_id") or "") or None
        if parent_id:
            self.get_set(parent_id)
        now = _now()
        set_id = uuid.uuid4().hex
        with self._transaction() as conn:
            try:
                conn.execute(
                    """INSERT INTO viewpoint_sets
                       (id,name,description,parent_set_id,state,is_default,priority,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        set_id,
                        name,
                        str(payload.get("description", "")).strip(),
                        parent_id,
                        "active",
                        int(bool(payload.get("is_default"))),
                        int(payload.get("priority", 0)),
                        now,
                        now,
                    ),
                )
                if payload.get("is_default"):
                    conn.execute("UPDATE viewpoint_sets SET is_default=0 WHERE id<>?", (set_id,))
                self._create_empty_draft(conn, set_id, 1, now)
            except sqlite3.IntegrityError as exc:
                raise ConflictError("同名の観点セットが既にあります。") from exc
        return self.get_set(set_id)

    def update_set(self, set_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get_set(set_id)
        self._check_revision(current, payload)
        parent_id = payload.get("parent_set_id", current["parent_set_id"])
        parent_id = str(parent_id or "") or None
        if parent_id == set_id:
            raise ViewpointStoreError("自分自身を親セットにはできません。")
        if parent_id:
            self.get_set(parent_id)
        now = _now()
        with self._transaction() as conn:
            conn.execute(
                """UPDATE viewpoint_sets SET name=?,description=?,parent_set_id=?,state=?,
                   is_default=?,priority=?,revision=revision+1,updated_at=? WHERE id=?""",
                (
                    str(payload.get("name", current["name"])).strip(),
                    str(payload.get("description", current["description"])).strip(),
                    parent_id,
                    str(payload.get("state", current["state"])),
                    int(bool(payload.get("is_default", current["is_default"]))),
                    int(payload.get("priority", current["priority"])),
                    now,
                    set_id,
                ),
            )
            if payload.get("is_default"):
                conn.execute("UPDATE viewpoint_sets SET is_default=0 WHERE id<>?", (set_id,))
            self._assert_no_cycle(conn, set_id)
        return self.get_set(set_id)

    def delete_set(self, set_id: str) -> dict[str, Any]:
        self.get_set(set_id)
        with self._transaction() as conn:
            conn.execute(
                "UPDATE viewpoint_sets SET deleted_at=?,revision=revision+1,updated_at=? WHERE id=?",
                (_now(), _now(), set_id),
            )
        return self.get_set(set_id, include_deleted=True)

    def restore_set(self, set_id: str) -> dict[str, Any]:
        self.get_set(set_id, include_deleted=True)
        with self._transaction() as conn:
            conn.execute(
                "UPDATE viewpoint_sets SET deleted_at=NULL,revision=revision+1,updated_at=? WHERE id=?",
                (_now(), set_id),
            )
        return self.get_set(set_id)

    def list_versions(self, set_id: str) -> list[dict[str, Any]]:
        self.get_set(set_id)
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT v.*,
                   (SELECT COUNT(*) FROM viewpoint_items i WHERE i.version_id=v.id AND i.deleted_at IS NULL) AS item_count
                   FROM viewpoint_versions v WHERE set_id=? ORDER BY version_number DESC""",
                (set_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_version(
        self, set_id: str, version_number: int | None = None, *, status: str | None = None
    ) -> dict[str, Any]:
        self.get_set(set_id)
        clauses = ["set_id=?"]
        params: list[Any] = [set_id]
        if version_number is not None:
            clauses.append("version_number=?")
            params.append(int(version_number))
        if status:
            clauses.append("status=?")
            params.append(status)
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM viewpoint_versions WHERE {' AND '.join(clauses)} ORDER BY version_number DESC LIMIT 1",
                params,
            ).fetchone()
        if row is None:
            raise NotFoundError("指定したセット版が見つかりません。")
        return dict(row)

    def ensure_draft(self, set_id: str) -> dict[str, Any]:
        self.get_set(set_id)
        try:
            return self.get_version(set_id, status="draft")
        except NotFoundError:
            pass
        now = _now()
        with self._transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM viewpoint_versions WHERE set_id=? AND status='draft'", (set_id,)
            ).fetchone()
            if existing:
                return dict(existing)
            source = conn.execute(
                "SELECT * FROM viewpoint_versions WHERE set_id=? AND status='published' ORDER BY version_number DESC LIMIT 1",
                (set_id,),
            ).fetchone()
            next_number = int(
                conn.execute(
                    "SELECT COALESCE(MAX(version_number),0)+1 FROM viewpoint_versions WHERE set_id=?",
                    (set_id,),
                ).fetchone()[0]
            )
            version_id = uuid.uuid4().hex
            conn.execute(
                """INSERT INTO viewpoint_versions
                   (id,set_id,version_number,status,based_on_version_id,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    version_id,
                    set_id,
                    next_number,
                    "draft",
                    source["id"] if source else None,
                    now,
                    now,
                ),
            )
            if source:
                conn.execute(
                    """INSERT INTO viewpoint_items
                       (id,version_id,persistent_key,name,category,purpose,trigger_rule,recommended_checks,
                        risk_weight,automation,standards,tags,enabled,revision,deleted_at,created_at,updated_at)
                       SELECT lower(hex(randomblob(16))), ?, persistent_key,name,category,purpose,trigger_rule,
                        recommended_checks,risk_weight,automation,standards,tags,enabled,1,deleted_at,?,?
                       FROM viewpoint_items WHERE version_id=?""",
                    (version_id, now, now, source["id"]),
                )
        return self.get_version(set_id, next_number)

    def _create_empty_draft(
        self, conn: sqlite3.Connection, set_id: str, version_number: int, now: str
    ) -> str:
        version_id = uuid.uuid4().hex
        conn.execute(
            """INSERT INTO viewpoint_versions
               (id,set_id,version_number,status,created_at,updated_at) VALUES (?,?,?,?,?,?)""",
            (version_id, set_id, version_number, "draft", now, now),
        )
        return version_id

    def list_items(
        self,
        set_id: str,
        version_number: int | None = None,
        *,
        include_deleted: bool = False,
        resolved: bool = True,
    ) -> list[dict[str, Any]]:
        version = (
            self.get_version(set_id, version_number)
            if version_number is not None
            else self._preferred_version(set_id)
        )
        if resolved:
            return self._resolve_items(set_id, version, include_deleted=include_deleted)
        with self._connect() as conn:
            where = "" if include_deleted else "AND deleted_at IS NULL"
            rows = conn.execute(
                f"SELECT * FROM viewpoint_items WHERE version_id=? {where} ORDER BY category,name",
                (version["id"],),
            ).fetchall()
        return [self._item_dict(row, source_set_id=set_id, inherited=False) for row in rows]

    def _preferred_version(self, set_id: str) -> dict[str, Any]:
        try:
            return self.get_version(set_id, status="draft")
        except NotFoundError:
            return self.get_version(set_id, status="published")

    def _resolve_items(
        self, set_id: str, version: dict[str, Any], *, include_deleted: bool = False
    ) -> list[dict[str, Any]]:
        chain: list[tuple[str, dict[str, Any]]] = []
        seen: set[str] = set()
        current_set_id: str | None = set_id
        first = True
        while current_set_id:
            if current_set_id in seen:
                raise ConflictError("観点セットの継承が循環しています。")
            seen.add(current_set_id)
            current_set = self.get_set(current_set_id)
            current_version = (
                version if first else self.get_version(current_set_id, status="published")
            )
            chain.append((current_set_id, current_version))
            current_set_id = current_set.get("parent_set_id")
            first = False
        merged: dict[str, dict[str, Any]] = {}
        with self._connect() as conn:
            for source_set_id, source_version in reversed(chain):
                rows = conn.execute(
                    "SELECT * FROM viewpoint_items WHERE version_id=? ORDER BY category,name",
                    (source_version["id"],),
                ).fetchall()
                for row in rows:
                    if row["deleted_at"] and not include_deleted:
                        merged.pop(row["persistent_key"], None)
                        continue
                    merged[row["persistent_key"]] = self._item_dict(
                        row, source_set_id=source_set_id, inherited=source_set_id != set_id
                    )
        return sorted(merged.values(), key=lambda item: (item["category"], item["name"]))

    def create_item(
        self, set_id: str, payload: dict[str, Any], *, version_number: int | None = None
    ) -> dict[str, Any]:
        version = (
            self.get_version(set_id, version_number)
            if version_number
            else self.ensure_draft(set_id)
        )
        self._assert_mutable(version)
        item = self._normalize_item(payload)
        now = _now()
        with self._transaction() as conn:
            try:
                item_id = self._insert_item(conn, version["id"], item, now)
                conn.execute(
                    "UPDATE viewpoint_versions SET revision=revision+1,updated_at=? WHERE id=?",
                    (now, version["id"]),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError("同じ永続キーの観点がこの版に既にあります。") from exc
        return self.get_item(item_id)

    def get_item(self, item_id: str, *, include_deleted: bool = False) -> dict[str, Any]:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                """SELECT i.*,v.set_id,v.version_number,v.status AS version_status
                   FROM viewpoint_items i JOIN viewpoint_versions v ON v.id=i.version_id WHERE i.id=?""",
                (item_id,),
            ).fetchone()
        if row is None or (row["deleted_at"] and not include_deleted):
            raise NotFoundError("観点が見つかりません。")
        result = self._item_dict(row, source_set_id=row["set_id"], inherited=False)
        result |= {
            "set_id": row["set_id"],
            "version_number": row["version_number"],
            "version_status": row["version_status"],
        }
        return result

    def update_item(self, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get_item(item_id, include_deleted=True)
        self._check_revision(current, payload)
        version = self.get_version(current["set_id"], current["version_number"])
        self._assert_mutable(version)
        merged = current | payload
        item = self._normalize_item(merged, persistent_key=current["persistent_key"])
        now = _now()
        with self._transaction() as conn:
            conn.execute(
                """UPDATE viewpoint_items SET name=?,category=?,purpose=?,trigger_rule=?,recommended_checks=?,
                   risk_weight=?,automation=?,standards=?,tags=?,enabled=?,revision=revision+1,updated_at=?
                   WHERE id=?""",
                (
                    item["name"],
                    item["category"],
                    item["purpose"],
                    _canonical(item["trigger_rule"]),
                    item["recommended_checks"],
                    item["risk_weight"],
                    item["automation"],
                    item["standards"],
                    _canonical(item["tags"]),
                    int(item["enabled"]),
                    now,
                    item_id,
                ),
            )
            conn.execute(
                "UPDATE viewpoint_versions SET revision=revision+1,updated_at=? WHERE id=?",
                (now, version["id"]),
            )
        return self.get_item(item_id, include_deleted=True)

    def delete_item(self, item_id: str) -> dict[str, Any]:
        current = self.get_item(item_id)
        version = self.get_version(current["set_id"], current["version_number"])
        self._assert_mutable(version)
        now = _now()
        with self._transaction() as conn:
            conn.execute(
                "UPDATE viewpoint_items SET deleted_at=?,revision=revision+1,updated_at=? WHERE id=?",
                (now, now, item_id),
            )
        return self.get_item(item_id, include_deleted=True)

    def restore_item(self, item_id: str) -> dict[str, Any]:
        current = self.get_item(item_id, include_deleted=True)
        version = self.get_version(current["set_id"], current["version_number"])
        self._assert_mutable(version)
        with self._transaction() as conn:
            conn.execute(
                "UPDATE viewpoint_items SET deleted_at=NULL,revision=revision+1,updated_at=? WHERE id=?",
                (_now(), item_id),
            )
        return self.get_item(item_id)

    def _normalize_import_row(self, row: dict[str, Any], *, index: int) -> dict[str, Any]:
        raise NotImplementedError

    def _normalize_item(
        self, payload: dict[str, Any], *, persistent_key: str | None = None
    ) -> dict[str, Any]:
        raise NotImplementedError

    def _insert_item(
        self, conn: sqlite3.Connection, version_id: str, item: dict[str, Any], now: str
    ) -> str:
        raise NotImplementedError

    def _item_dict(
        self, row: sqlite3.Row, *, source_set_id: str, inherited: bool
    ) -> dict[str, Any]:
        raise NotImplementedError

    def _check_revision(self, current: dict[str, Any], payload: dict[str, Any]) -> None:
        raise NotImplementedError

    def _assert_mutable(self, version: dict[str, Any]) -> None:
        raise NotImplementedError

    def _assert_no_cycle(self, conn: sqlite3.Connection, start_set_id: str) -> None:
        raise NotImplementedError

    def _items_checksum(self, items: list[dict[str, Any]]) -> str:
        raise NotImplementedError


from web.services.viewpoint_store_operations import ViewpointStoreOperations  # noqa: E402

ViewpointStore = ViewpointStoreOperations

_STORE: ViewpointStore | None = None
_STORE_KEY: tuple[str, str] | None = None
_STORE_LOCK = threading.Lock()


def get_viewpoint_store() -> ViewpointStore:
    from web.config import QA_VIEWPOINTS_CSV, VIEWPOINTS_DB

    global _STORE, _STORE_KEY
    key = (str(VIEWPOINTS_DB), str(QA_VIEWPOINTS_CSV))
    if _STORE is not None and _STORE_KEY == key:
        return _STORE
    with _STORE_LOCK:
        if _STORE is None or _STORE_KEY != key:
            _STORE = ViewpointStore(VIEWPOINTS_DB, QA_VIEWPOINTS_CSV)
            _STORE.initialize()
            _STORE_KEY = key
    return _STORE
