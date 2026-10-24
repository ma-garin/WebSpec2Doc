from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from flask import Blueprint, Response, request

from web.auth import require_admin
from web.services.admin_audit import (
    append_admin_audit,
    audit_case_of,
    audit_events_csv,
    read_admin_audit,
)
from web.services.approval_policy import (
    ApprovalPolicyConflict,
    ApprovalPolicyError,
    changed_fields,
    load_approval_policy,
    save_approval_policy,
)
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
BACKUP_GUIDE_PATH = Path(__file__).resolve().parents[2] / "docs" / "process" / "OPERATIONS_BACKUP.md"


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


_AUDIT_FILTERS = ("action", "outcome", "query", "actor", "case", "since", "until")


def _audit_filters() -> dict[str, str]:
    return {key: request.args.get(key, "").strip()[:200] for key in _AUDIT_FILTERS}


def _event_view(event) -> dict:
    data = asdict(event)
    data["case"] = audit_case_of(event)
    reason = event.detail.get("reason", "")
    data["reason"] = reason if isinstance(reason, str) else ""
    return data


@bp.get("/audit")
def get_audit() -> dict:
    try:
        limit = max(1, min(int(request.args.get("limit", "100")), 100))
        offset = max(0, int(request.args.get("offset", "0")))
    except ValueError:
        limit = 100
        offset = 0
    events = read_admin_audit(_audit_path(), limit=limit + 1, offset=offset, **_audit_filters())
    has_more = len(events) > limit
    page = events[:limit]
    return {
        "events": [_event_view(event) for event in page],
        "has_more": has_more,
        "next_offset": offset + limit if has_more else None,
    }


@bp.get("/audit.csv")
def get_audit_csv() -> Response:
    events: list = []
    offset = 0
    while len(events) < 1000:
        page = read_admin_audit(_audit_path(), limit=101, offset=offset, **_audit_filters())
        events.extend(page[:100])
        if len(page) <= 100:
            break
        offset += 100
    user = current_auth_user() or {}
    append_admin_audit(
        _audit_path(),
        action="audit.exported",
        actor_id=str(user.get("id", "")),
        actor_email=str(user.get("email", "local-admin")),
        target_type="audit",
        target_id="current",
        detail={"rows": len(events), "filters": _audit_filters()},
    )
    return Response(
        "\ufeff" + audit_events_csv(events),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit.csv"},
    )


def _approval_policy_path() -> Path:
    return scoped_instance_path(INSTANCE_DIR / "approval_policy.json")


@bp.get("/approval-policy")
def get_approval_policy() -> dict:
    return {"policy": asdict(load_approval_policy(_approval_policy_path()))}


@bp.put("/approval-policy")
def put_approval_policy() -> tuple[dict, int] | dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return {"error": "リクエスト形式が不正です。画面を再読み込みしてください。", "code": "invalid_request"}, 400
    user = current_auth_user() or {}
    actor_email = str(user.get("email", "local-admin"))
    try:
        before, after = save_approval_policy(
            _approval_policy_path(), payload, updated_by=actor_email
        )
    except ApprovalPolicyConflict as exc:
        return {
            "error": "他の管理者が先に保存しました。最新の値を確認してから保存し直してください。",
            "code": "conflict",
            "policy": asdict(exc.current),
        }, 409
    except ApprovalPolicyError as exc:
        return {"error": str(exc), "code": "invalid_approval_policy", "field": exc.field}, 400
    except OSError:
        return {"error": "保存できませんでした。時間をおいて再度保存してください。", "code": "write_failed"}, 500
    append_admin_audit(
        _audit_path(),
        action="policy.approval_updated",
        actor_id=str(user.get("id", "")),
        actor_email=actor_email,
        target_type="approval_policy",
        target_id="current",
        detail={
            "changed_fields": changed_fields(before, after),
            "rev_before": before.rev,
            "rev_after": after.rev,
            "reason": after.exception_reason if after.small_tenant_exception else "",
        },
    )
    return {"ok": True, "policy": asdict(after)}


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
