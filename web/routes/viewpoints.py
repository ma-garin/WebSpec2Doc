from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, request

from web.services.openai_qa import OpenAIQAError, has_openai_api_key
from web.services.viewpoint_proposals import generate_viewpoint_proposals
from web.services.viewpoint_store import ViewpointStoreError, get_viewpoint_store

bp = Blueprint("viewpoints", __name__)


@bp.errorhandler(ViewpointStoreError)
def handle_viewpoint_error(exc: ViewpointStoreError) -> tuple[dict[str, Any], int]:
    body: dict[str, Any] = {"error": str(exc)}
    if exc.details is not None:
        body["details"] = exc.details
    return body, exc.status_code


def _body() -> dict[str, Any]:
    value = request.get_json(silent=True)
    return value if isinstance(value, dict) else {}


@bp.get("/api/viewpoint-sets")
def api_viewpoint_sets() -> dict[str, Any]:
    return {
        "sets": get_viewpoint_store().list_sets(
            include_deleted=request.args.get("include_deleted") == "1"
        ),
        "ai_available": has_openai_api_key(),
    }


@bp.post("/api/viewpoint-sets")
def api_create_viewpoint_set() -> tuple[dict[str, Any], int]:
    return {"set": get_viewpoint_store().create_set(_body())}, 201


@bp.get("/api/viewpoint-sets/<set_id>")
def api_get_viewpoint_set(set_id: str) -> dict[str, Any]:
    store = get_viewpoint_store()
    return {
        "set": store.get_set(set_id),
        "versions": store.list_versions(set_id),
        "assignments": store.list_assignments(set_id),
    }


@bp.patch("/api/viewpoint-sets/<set_id>")
def api_update_viewpoint_set(set_id: str) -> dict[str, Any]:
    return {"set": get_viewpoint_store().update_set(set_id, _body())}


@bp.delete("/api/viewpoint-sets/<set_id>")
def api_delete_viewpoint_set(set_id: str) -> dict[str, Any]:
    return {"set": get_viewpoint_store().delete_set(set_id), "undo_available": True}


@bp.post("/api/viewpoint-sets/<set_id>/restore")
def api_restore_viewpoint_set(set_id: str) -> dict[str, Any]:
    return {"set": get_viewpoint_store().restore_set(set_id)}


@bp.get("/api/viewpoint-sets/<set_id>/versions")
def api_viewpoint_versions(set_id: str) -> dict[str, Any]:
    return {"versions": get_viewpoint_store().list_versions(set_id)}


@bp.post("/api/viewpoint-sets/<set_id>/versions")
def api_create_viewpoint_draft(set_id: str) -> tuple[dict[str, Any], int]:
    return {"version": get_viewpoint_store().ensure_draft(set_id)}, 201


@bp.get("/api/viewpoint-sets/<set_id>/versions/<int:version>/items")
def api_viewpoint_items(set_id: str, version: int) -> dict[str, Any]:
    store = get_viewpoint_store()
    return {
        "version": store.get_version(set_id, version),
        "items": store.list_items(
            set_id,
            version,
            include_deleted=request.args.get("include_deleted") == "1",
            resolved=request.args.get("resolved", "1") != "0",
        ),
    }


@bp.post("/api/viewpoint-sets/<set_id>/versions/<int:version>/items")
def api_create_viewpoint_item(set_id: str, version: int) -> tuple[dict[str, Any], int]:
    item = get_viewpoint_store().create_item(set_id, _body(), version_number=version)
    return {"item": item}, 201


@bp.patch("/api/viewpoint-items/<item_id>")
def api_update_viewpoint_item(item_id: str) -> dict[str, Any]:
    return {"item": get_viewpoint_store().update_item(item_id, _body())}


@bp.delete("/api/viewpoint-items/<item_id>")
def api_delete_viewpoint_item(item_id: str) -> dict[str, Any]:
    return {
        "item": get_viewpoint_store().delete_item(item_id),
        "undo_available": True,
    }


@bp.post("/api/viewpoint-items/<item_id>/restore")
def api_restore_viewpoint_item(item_id: str) -> dict[str, Any]:
    return {"item": get_viewpoint_store().restore_item(item_id)}


@bp.post("/api/viewpoint-items/bulk")
def api_bulk_update_viewpoint_items() -> dict[str, Any]:
    body = _body()
    return {
        "items": get_viewpoint_store().bulk_update(
            [str(value) for value in body.get("item_ids", [])],
            body.get("changes", {}) if isinstance(body.get("changes"), dict) else {},
        )
    }


@bp.post("/api/viewpoint-sets/<set_id>/versions/<int:version>/publish")
def api_publish_viewpoint_version(set_id: str, version: int) -> dict[str, Any]:
    body = _body()
    published = get_viewpoint_store().publish(
        set_id,
        version,
        revision=body.get("revision"),
        change_reason=str(body.get("change_reason", "")),
    )
    return {"version": published}


@bp.post("/api/viewpoint-sets/<set_id>/versions/<int:version>/rollback")
def api_rollback_viewpoint_version(set_id: str, version: int) -> dict[str, Any]:
    return {
        "version": get_viewpoint_store().rollback(set_id, version, str(_body().get("reason", "")))
    }


@bp.get("/api/viewpoint-sets/<set_id>/versions/diff")
def api_diff_viewpoint_versions(set_id: str) -> dict[str, Any]:
    return {
        "diff": get_viewpoint_store().version_diff(
            set_id, int(request.args["from"]), int(request.args["to"])
        )
    }


@bp.get("/api/viewpoint-sets/<set_id>/assignments")
def api_viewpoint_assignments(set_id: str) -> dict[str, Any]:
    return {"assignments": get_viewpoint_store().list_assignments(set_id)}


@bp.post("/api/viewpoint-sets/<set_id>/assignments")
def api_create_viewpoint_assignment(set_id: str) -> tuple[dict[str, Any], int]:
    return {"assignment": get_viewpoint_store().create_assignment(set_id, _body())}, 201


@bp.patch("/api/viewpoint-assignments/<assignment_id>")
def api_update_viewpoint_assignment(assignment_id: str) -> dict[str, Any]:
    return {"assignment": get_viewpoint_store().update_assignment(assignment_id, _body())}


@bp.delete("/api/viewpoint-assignments/<assignment_id>")
def api_delete_viewpoint_assignment(assignment_id: str) -> dict[str, bool]:
    get_viewpoint_store().delete_assignment(assignment_id)
    return {"ok": True}


@bp.get("/api/viewpoint-sets/<set_id>/proposals")
def api_viewpoint_proposals(set_id: str) -> dict[str, Any]:
    return {
        "proposals": get_viewpoint_store().list_proposals(set_id),
        "ai_available": has_openai_api_key(),
    }


@bp.post("/api/viewpoint-sets/<set_id>/proposals")
def api_generate_viewpoint_proposals(set_id: str) -> tuple[dict[str, Any], int] | dict[str, Any]:
    store = get_viewpoint_store()
    body = _body()
    if not has_openai_api_key():
        return {"error": "OpenAI設定がないためAI提案は利用できません。"}, 503
    try:
        proposals = generate_viewpoint_proposals(body, store.list_items(set_id))
    except OpenAIQAError as exc:
        return {"error": str(exc)}, 502
    return {"proposals": store.save_proposals(set_id, proposals)}


@bp.post("/api/viewpoint-proposals/<proposal_id>/decision")
def api_decide_viewpoint_proposal(proposal_id: str) -> dict[str, Any]:
    return {
        "proposal": get_viewpoint_store().decide_proposal(
            proposal_id, str(_body().get("decision", ""))
        )
    }


@bp.get("/api/viewpoint-sets/<set_id>/export")
def api_export_viewpoint_set(set_id: str) -> Response:
    version_value = request.args.get("version")
    text = get_viewpoint_store().export_csv(set_id, int(version_value) if version_value else None)
    response = Response(text, content_type="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = 'attachment; filename="viewpoints.csv"'
    return response


@bp.post("/api/viewpoint-sets/<set_id>/import")
def api_import_viewpoint_set(set_id: str) -> dict[str, Any]:
    uploaded = request.files.get("file")
    if uploaded:
        text = uploaded.read().decode("utf-8-sig")
    else:
        text = str(_body().get("csv", ""))
    return {"result": get_viewpoint_store().import_csv(set_id, text)}


@bp.get("/api/viewpoint-sets/<set_id>/tree")
def api_viewpoint_tree(set_id: str) -> dict[str, Any]:
    store = get_viewpoint_store()
    version_arg = request.args.get("version")
    return {
        "nodes": store.get_tree(
            set_id,
            int(version_arg) if version_arg else None,
            include_deleted=request.args.get("include_deleted") == "1",
        ),
        "version": store._preferred_version(set_id),
    }


@bp.post("/api/viewpoint-sets/<set_id>/folders")
def api_create_viewpoint_folder(set_id: str) -> tuple[dict[str, Any], int]:
    body = _body()
    return {"item": get_viewpoint_store().create_folder(set_id, body)}, 201


@bp.patch("/api/viewpoint-items/<item_id>/move")
def api_move_viewpoint_item(item_id: str) -> dict[str, Any]:
    body = _body()
    parent_key = body.get("parent_key")
    return {"item": get_viewpoint_store().move_item(item_id, parent_key)}


@bp.patch("/api/viewpoint-sets/<set_id>/items/reorder")
def api_reorder_viewpoint_items(set_id: str) -> dict[str, Any]:
    body = _body()
    orders = body.get("orders", [])
    if not isinstance(orders, list):
        orders = []
    return get_viewpoint_store().reorder_items(set_id, orders)


@bp.delete("/api/viewpoint-folders/<item_id>")
def api_delete_viewpoint_folder(item_id: str) -> dict[str, Any]:
    return {"item": get_viewpoint_store().delete_folder(item_id), "undo_available": True}


@bp.get("/api/viewpoint-selection")
def api_viewpoint_selection() -> dict[str, Any]:
    store = get_viewpoint_store()
    url = request.args.get("url", "")
    snapshot = store.select_snapshot({"url": url})
    summary = {key: value for key, value in snapshot.items() if key != "items"}
    return {
        "recommended": summary,
        "sets": [row for row in store.list_sets() if row.get("published_version")],
    }
