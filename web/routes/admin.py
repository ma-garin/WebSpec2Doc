from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from flask import Blueprint, Response, request

from web.auth import require_admin
from web.services.admin_audit import append_admin_audit, read_admin_audit
from web.services.retention import (
    RetentionPolicyError,
    collect_storage_usage,
    load_retention_policy,
    save_retention_policy,
)
from web.tenancy import current_auth_user, scoped_instance_path, scoped_output_dir

bp = Blueprint("admin", __name__, url_prefix="/api/admin")

OUTPUT_DIR = Path("output")
INSTANCE_DIR = Path("instance")
BACKUP_GUIDE_PATH = Path(__file__).resolve().parents[2] / "docs" / "OPERATIONS_BACKUP.md"


@bp.before_request
def _admin_guard():
    return require_admin()


def _retention_path() -> Path:
    return scoped_instance_path(INSTANCE_DIR / "retention.json")


def _audit_path() -> Path:
    return scoped_instance_path(INSTANCE_DIR / "admin_audit.jsonl")


def _instance_scope_dir() -> Path:
    return scoped_instance_path(INSTANCE_DIR / ".scope").parent


@bp.get("/storage")
def get_storage() -> dict:
    usage = collect_storage_usage(scoped_output_dir(OUTPUT_DIR), _instance_scope_dir())
    return {"storage": asdict(usage)}


@bp.get("/backup-guide")
def get_backup_guide() -> Response:
    try:
        content = BACKUP_GUIDE_PATH.read_text(encoding="utf-8")
    except OSError:
        return Response("バックアップ手順書が見つかりません。", status=404, mimetype="text/plain")
    return Response(content, mimetype="text/markdown")


@bp.get("/audit")
def get_audit() -> dict:
    try:
        limit = int(request.args.get("limit", "100"))
    except ValueError:
        limit = 100
    events = read_admin_audit(
        _audit_path(),
        limit=limit,
        action=request.args.get("action", ""),
        outcome=request.args.get("outcome", ""),
        query=request.args.get("query", ""),
    )
    return {"events": [asdict(event) for event in events]}


@bp.get("/retention")
def get_retention() -> dict:
    return {"policy": asdict(load_retention_policy(_retention_path()))}


@bp.put("/retention")
def put_retention() -> tuple[dict, int] | dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return {"error": "リクエスト形式が不正です。", "code": "invalid_request"}, 400
    user = current_auth_user() or {}
    try:
        policy = save_retention_policy(
            _retention_path(),
            payload,
            updated_by=str(user.get("email", "local-admin")),
        )
    except RetentionPolicyError as exc:
        return {"error": str(exc), "code": "invalid_retention_policy"}, 400
    append_admin_audit(
        _audit_path(),
        action="retention.settings_updated",
        actor_id=str(user.get("id", "")),
        actor_email=str(user.get("email", "local-admin")),
        target_type="workspace",
        target_id="current",
        detail={"changed_fields": sorted(payload)},
    )
    return {"ok": True, "policy": asdict(policy)}
