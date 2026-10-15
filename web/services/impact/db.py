"""System 09 影響度分析の保存先（テナント別 SQLite）。DD-001。"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from web import config
from web.tenancy import scoped_output_dir

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS systems(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT DEFAULT '',
  policy TEXT CHECK(policy IN('none','local','external')) DEFAULT 'none',
  p1_min INT DEFAULT 10, p2_min INT DEFAULT 6, depth_default INT DEFAULT 2,
  degraded_recall REAL, degraded_precision REAL, created_by TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS members(
  system_id TEXT REFERENCES systems(id) ON DELETE CASCADE, actor TEXT NOT NULL,
  role TEXT CHECK(role IN('admin','analyst','approver','viewer')), PRIMARY KEY(system_id, actor));
CREATE TABLE IF NOT EXISTS documents(
  id TEXT PRIMARY KEY, system_id TEXT REFERENCES systems(id) ON DELETE CASCADE, name TEXT NOT NULL,
  kind TEXT CHECK(kind IN('requirement','design','screen','testcase','other')),
  size INT, item_count INT, sha256 TEXT, created_by TEXT, created_at TEXT, UNIQUE(system_id, name));
CREATE TABLE IF NOT EXISTS items(
  id TEXT PRIMARY KEY, system_id TEXT REFERENCES systems(id) ON DELETE CASCADE,
  document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
  code TEXT, text TEXT, location TEXT, section TEXT, ord INT);
CREATE INDEX IF NOT EXISTS ix_items_doc ON items(document_id);
CREATE TABLE IF NOT EXISTS baselines(
  id TEXT PRIMARY KEY, system_id TEXT REFERENCES systems(id) ON DELETE CASCADE, name TEXT NOT NULL,
  note TEXT, created_by TEXT, created_at TEXT, UNIQUE(system_id, name));
CREATE TABLE IF NOT EXISTS baseline_items(
  baseline_id TEXT REFERENCES baselines(id) ON DELETE CASCADE, item_id TEXT, document_name TEXT,
  kind TEXT, code TEXT, text TEXT, location TEXT, section TEXT, ord INT);
CREATE TABLE IF NOT EXISTS links(
  id TEXT PRIMARY KEY, system_id TEXT REFERENCES systems(id) ON DELETE CASCADE,
  a_item TEXT REFERENCES items(id) ON DELETE CASCADE, b_item TEXT REFERENCES items(id) ON DELETE CASCADE,
  origin TEXT CHECK(origin IN('manual','suggested')), created_by TEXT, created_at TEXT,
  UNIQUE(system_id, a_item, b_item));
CREATE TABLE IF NOT EXISTS link_suggestions(
  id TEXT PRIMARY KEY, system_id TEXT REFERENCES systems(id) ON DELETE CASCADE, a_item TEXT, b_item TEXT,
  score REAL, reason TEXT, state TEXT CHECK(state IN('open','accepted','rejected')) DEFAULT 'open',
  decided_by TEXT, decided_at TEXT);
CREATE TABLE IF NOT EXISTS change_requests(
  id TEXT PRIMARY KEY, system_id TEXT REFERENCES systems(id) ON DELETE CASCADE, code TEXT, title TEXT,
  reason TEXT, status TEXT, base_baseline TEXT REFERENCES baselines(id) ON DELETE SET NULL,
  target_baseline TEXT REFERENCES baselines(id) ON DELETE SET NULL, change_text TEXT, depth INT,
  created_by TEXT, created_at TEXT, updated_at TEXT, UNIQUE(system_id, code));
CREATE TABLE IF NOT EXISTS changes(
  id TEXT PRIMARY KEY, cr_id TEXT REFERENCES change_requests(id) ON DELETE CASCADE, code TEXT,
  kind TEXT CHECK(kind IN('add','modify','delete','text')), location TEXT, before TEXT, after TEXT,
  wording_only INT);
CREATE TABLE IF NOT EXISTS impacts(
  id TEXT PRIMARY KEY, cr_id TEXT REFERENCES change_requests(id) ON DELETE CASCADE, change_ids TEXT,
  item_id TEXT, item_code TEXT, document_name TEXT, doc_kind TEXT, location TEXT, section TEXT, text TEXT,
  depth INT, evidence TEXT, confidence REAL, impact_level INT, impact_reason TEXT, likelihood INT,
  likelihood_reason TEXT, risk INT, priority INT, override_impact INT, override_likelihood INT,
  override_reason TEXT, override_by TEXT, override_at TEXT,
  state TEXT CHECK(state IN('open','required','not_required')) DEFAULT 'open',
  resolve_reason TEXT, resolved_by TEXT, resolved_at TEXT, tests TEXT, test_gap INT, test_idea TEXT,
  method TEXT CHECK(method IN('llm','rule')));
CREATE INDEX IF NOT EXISTS ix_impacts_cr ON impacts(cr_id);
CREATE TABLE IF NOT EXISTS jobs(
  id TEXT PRIMARY KEY, cr_id TEXT REFERENCES change_requests(id) ON DELETE CASCADE,
  status TEXT CHECK(status IN('queued','running','done','failed','cancelled','interrupted')),
  stage TEXT, progress INT, message TEXT, cancel INT DEFAULT 0, started_at TEXT, finished_at TEXT,
  engine TEXT);
CREATE TABLE IF NOT EXISTS actuals(
  id TEXT PRIMARY KEY, cr_id TEXT REFERENCES change_requests(id) ON DELETE CASCADE, item_id TEXT,
  item_code TEXT, note TEXT, recorded_by TEXT, recorded_at TEXT);
CREATE TABLE IF NOT EXISTS approvals(
  id TEXT PRIMARY KEY, cr_id TEXT REFERENCES change_requests(id) ON DELETE CASCADE,
  decision TEXT CHECK(decision IN('approved','returned')), reason TEXT, actor TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT, system_id TEXT, cr_id TEXT, actor TEXT, action TEXT,
  target TEXT, before TEXT, after TEXT, at TEXT);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
  BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
  BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def db_path() -> Path:
    """テナント別の impact.db の場所。"""
    return scoped_output_dir(config.DATA_DIR) / "impact" / "impact.db"


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    if row[0] is None:
        conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
    conn.commit()


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = Path(path) if path else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    migrate(conn)
    return conn


def row(r) -> dict | None:
    return dict(r) if r is not None else None


def rows(rs) -> list[dict]:
    return [dict(r) for r in rs]


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(text, default=None):
    if text in (None, ""):
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default
