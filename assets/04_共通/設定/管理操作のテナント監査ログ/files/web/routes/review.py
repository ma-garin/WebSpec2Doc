from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path

from flask import Blueprint, request

from web.audit_context import record_admin_event
from web.config import OUTPUT_DIR
from web.tenancy import scoped_output_dir
from web.validation import _valid_domain

logger = logging.getLogger(__name__)

bp = Blueprint("review", __name__)
INSTANCE_DIR = Path("instance")


def _out() -> Path:
    """テナントスコープ済みの出力ディレクトリ（リクエスト毎に解決）。"""
    return scoped_output_dir(OUTPUT_DIR)


_REVIEW_LOCKS: dict[str, threading.Lock] = {}
_REVIEW_LOCKS_GUARD = threading.Lock()


def _get_review_lock(domain: str) -> threading.Lock:
    with _REVIEW_LOCKS_GUARD:
        if domain not in _REVIEW_LOCKS:
            _REVIEW_LOCKS[domain] = threading.Lock()
        return _REVIEW_LOCKS[domain]


_VALID_STATUSES = frozenset({"draft", "reviewing", "approved", "frozen"})


def _review_state_path(domain: str) -> Path:
    return _out() / domain / "review_state.json"


def _candidates_path(domain: str) -> Path:
    return _out() / domain / "playwright_candidates.json"


def _load_review_state(domain: str) -> dict:
    path = _review_state_path(domain)
    if not path.is_file():
        return {"domain": domain, "cases": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("review_state.json の読み込みに失敗: %s", domain)
        return {"domain": domain, "cases": {}}


def _save_review_state(domain: str, state: dict) -> None:
    path = _review_state_path(domain)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)  # atomic on POSIX


def _merge_candidates_with_state(candidates: list[dict], state: dict) -> list[dict]:
    """playwright_candidates.json の各ケースに review_state を重ねて返す。"""
    cases_state: dict = state.get("cases", {})
    merged = []
    for tc in candidates:
        case_id = tc.get("id", "")
        saved = cases_state.get(case_id, {})
        merged.append(
            {
                "id": case_id,
                "title": tc.get("title", tc.get("name", "")),
                "status": saved.get("status", "draft"),
                "comment": saved.get("comment", ""),
                "version": saved.get("version", 1),
            }
        )
    return merged


@bp.get("/review/cases")
def api_review_cases() -> tuple[dict, int] | dict:
    domain = request.args.get("domain", "").strip()
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400

    candidates_path = _candidates_path(domain)
    if not candidates_path.is_file():
        return {"domain": domain, "cases": []}

    try:
        candidates: list[dict] = json.loads(candidates_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("playwright_candidates.json の読み込みに失敗: %s", domain)
        return {"domain": domain, "cases": []}

    state = _load_review_state(domain)
    return {"domain": domain, "cases": _merge_candidates_with_state(candidates, state)}


@bp.post("/review/update")
def api_review_update() -> tuple[dict, int] | dict:
    body = request.get_json(silent=True) or {}
    domain = str(body.get("domain", "")).strip()
    case_id = str(body.get("case_id", "")).strip()
    new_status = str(body.get("status", "")).strip()
    comment = str(body.get("comment", "")).strip()

    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    if new_status not in _VALID_STATUSES:
        return {"error": f"invalid status: {new_status}"}, 400
    if not case_id:
        return {"error": "case_id is required"}, 400

    lock = _get_review_lock(domain)
    with lock:
        state = _load_review_state(domain)
        cases: dict = state.setdefault("cases", {})
        existing = cases.get(case_id, {})

        # frozen への遷移でバージョンをインクリメントする
        prev_version: int = existing.get("version", 1)
        new_version = prev_version + 1 if new_status == "frozen" else prev_version

        cases[case_id] = {
            "status": new_status,
            "comment": comment,
            "version": new_version,
            "reviewed_at": datetime.now().isoformat(timespec="seconds"),
        }
        state["domain"] = domain
        state["updated_at"] = datetime.now().isoformat(timespec="seconds")

        _save_review_state(domain, state)
    return {"ok": True, "case_id": case_id, "status": new_status, "version": new_version}


@bp.get("/review/export")
def api_review_export() -> tuple[dict, int] | dict:
    domain = request.args.get("domain", "").strip()
    filter_mode = request.args.get("filter", "all").strip()

    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400

    candidates_path = _candidates_path(domain)
    if not candidates_path.is_file():
        record_admin_event(
            INSTANCE_DIR,
            action="review.exported",
            target_type="review",
            target_id=domain,
            detail={"filter": filter_mode, "exported_count": 0},
        )
        return {"domain": domain, "exported_count": 0, "cases": []}

    try:
        candidates: list[dict] = json.loads(candidates_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("playwright_candidates.json の読み込みに失敗 (export): %s", domain)
        return {"domain": domain, "exported_count": 0, "cases": []}

    state = _load_review_state(domain)
    all_cases = _merge_candidates_with_state(candidates, state)

    if filter_mode == "approved":
        # approved と frozen のみを対象とする
        filtered = [c for c in all_cases if c["status"] in ("approved", "frozen")]
    else:
        filtered = all_cases

    record_admin_event(
        INSTANCE_DIR,
        action="review.exported",
        target_type="review",
        target_id=domain,
        detail={"filter": filter_mode, "exported_count": len(filtered)},
    )
    return {"domain": domain, "exported_count": len(filtered), "cases": filtered}
