-- ===== auth.db =====
CREATE TABLE api_tokens (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    name TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_by TEXT REFERENCES users(id),
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    revoked_at TEXT
                , scope TEXT NOT NULL DEFAULT 'full');
CREATE TABLE audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    at TEXT NOT NULL,
                    event TEXT NOT NULL,
                    user_id TEXT,
                    tenant_id TEXT,
                    detail TEXT NOT NULL DEFAULT ''
                );
CREATE TABLE auth_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    revoked_at TEXT
                , tenant_id TEXT);
CREATE TABLE memberships (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    role TEXT NOT NULL CHECK(role IN ('member','admin')),
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, tenant_id)
                );
CREATE TABLE tenants (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
CREATE TABLE "users" (
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
CREATE INDEX ix_api_tokens_tenant ON api_tokens(tenant_id);
CREATE INDEX ix_memberships_tenant ON memberships(tenant_id);
CREATE INDEX ix_memberships_user ON memberships(user_id);
CREATE INDEX ix_sessions_user ON auth_sessions(user_id);

-- ===== viewpoints.db =====
CREATE TABLE viewpoint_assignments (
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
CREATE TABLE viewpoint_items (
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
                    node_type TEXT NOT NULL DEFAULT 'viewpoint',
                    parent_key TEXT DEFAULT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    revision INTEGER NOT NULL DEFAULT 1,
                    deleted_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, expected_result TEXT NOT NULL DEFAULT '', evidence TEXT NOT NULL DEFAULT '', technique TEXT NOT NULL DEFAULT '', test_level TEXT NOT NULL DEFAULT '',
                    UNIQUE(version_id, persistent_key)
                );
CREATE TABLE viewpoint_proposals (
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
CREATE TABLE viewpoint_sets (
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
                , applicability TEXT NOT NULL DEFAULT '{}');
CREATE TABLE viewpoint_versions (
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
CREATE INDEX ix_viewpoint_items_version ON viewpoint_items(version_id);
CREATE INDEX ix_viewpoint_versions_set ON viewpoint_versions(set_id, version_number DESC);
CREATE UNIQUE INDEX uq_viewpoint_draft
                    ON viewpoint_versions(set_id) WHERE status = 'draft';
CREATE UNIQUE INDEX uq_viewpoint_set_name_active
                    ON viewpoint_sets(lower(name)) WHERE deleted_at IS NULL;

