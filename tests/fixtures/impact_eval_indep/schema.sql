-- DD-001 の DDL（engine の単体テスト・評価用。本番は web/services/impact/db.py の migrate）
CREATE TABLE systems(id TEXT PRIMARY KEY, name TEXT, description TEXT,
  policy TEXT CHECK(policy IN('none','local','external')) DEFAULT 'none',
  p1_min INT DEFAULT 8, p2_min INT DEFAULT 4, depth_default INT DEFAULT 2,
  degraded_recall REAL, degraded_precision REAL, created_by TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE members(system_id TEXT REFERENCES systems(id), actor TEXT,
  role TEXT CHECK(role IN('admin','analyst','approver','viewer')), PRIMARY KEY(system_id, actor));
CREATE TABLE documents(id TEXT PRIMARY KEY, system_id TEXT REFERENCES systems(id), name TEXT,
  kind TEXT CHECK(kind IN('requirement','design','screen','testcase','other')), size INT, item_count INT, sha256 TEXT,
  created_by TEXT, created_at TEXT, UNIQUE(system_id, name));
CREATE TABLE items(id TEXT PRIMARY KEY, system_id TEXT REFERENCES systems(id), document_id TEXT REFERENCES documents(id),
  code TEXT, text TEXT, location TEXT, section TEXT, ord INT);
CREATE TABLE baselines(id TEXT PRIMARY KEY, system_id TEXT REFERENCES systems(id), name TEXT, note TEXT,
  created_by TEXT, created_at TEXT, UNIQUE(system_id, name));
CREATE TABLE baseline_items(baseline_id TEXT REFERENCES baselines(id), item_id TEXT, document_name TEXT, kind TEXT,
  code TEXT, text TEXT, location TEXT, section TEXT, ord INT);
CREATE TABLE links(id TEXT PRIMARY KEY, system_id TEXT REFERENCES systems(id), a_item TEXT REFERENCES items(id),
  b_item TEXT REFERENCES items(id), origin TEXT CHECK(origin IN('manual','suggested')), created_by TEXT, created_at TEXT,
  UNIQUE(system_id, a_item, b_item));
CREATE TABLE link_suggestions(id TEXT PRIMARY KEY, system_id TEXT REFERENCES systems(id), a_item TEXT, b_item TEXT,
  score REAL, reason TEXT, state TEXT CHECK(state IN('open','accepted','rejected')), decided_by TEXT, decided_at TEXT);
CREATE TABLE change_requests(id TEXT PRIMARY KEY, system_id TEXT REFERENCES systems(id), code TEXT, title TEXT,
  reason TEXT, status TEXT, base_baseline TEXT REFERENCES baselines(id), target_baseline TEXT REFERENCES baselines(id),
  change_text TEXT, depth INT, created_by TEXT, created_at TEXT, updated_at TEXT, UNIQUE(system_id, code));
CREATE TABLE changes(id TEXT PRIMARY KEY, cr_id TEXT REFERENCES change_requests(id), code TEXT,
  kind TEXT CHECK(kind IN('add','modify','delete','text')), location TEXT, before TEXT, after TEXT, wording_only INT);
CREATE TABLE impacts(id TEXT PRIMARY KEY, cr_id TEXT REFERENCES change_requests(id), change_ids TEXT, item_id TEXT,
  item_code TEXT, document_name TEXT, doc_kind TEXT, location TEXT, section TEXT, text TEXT, depth INT, evidence TEXT,
  confidence REAL, impact_level INT, impact_reason TEXT, likelihood INT, likelihood_reason TEXT, risk INT, priority INT,
  override_impact INT, override_likelihood INT, override_reason TEXT, override_by TEXT, override_at TEXT,
  state TEXT CHECK(state IN('open','required','not_required')) DEFAULT 'open', resolve_reason TEXT, resolved_by TEXT,
  resolved_at TEXT, tests TEXT, test_gap INT, test_idea TEXT, method TEXT CHECK(method IN('llm','rule')));
CREATE TABLE jobs(id TEXT PRIMARY KEY, cr_id TEXT REFERENCES change_requests(id),
  status TEXT CHECK(status IN('queued','running','done','failed','cancelled','interrupted')),
  stage TEXT, progress INT, message TEXT, cancel INT DEFAULT 0, started_at TEXT, finished_at TEXT, engine TEXT);
