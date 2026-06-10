from __future__ import annotations

import dataclasses
import json
import logging
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, request

from web.config import OUTPUT_DIR

bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

# スナップショットファイル名の日時パターン: YYYYMMDD-HHMMSS
_SNAPSHOT_TS_RE = re.compile(r"(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})")


def _validate_domain(domain: str) -> bool:
    """ドメイン文字列にパストラバーサル文字が含まれていないか検証する。"""
    return ".." not in domain and "/" not in domain and len(domain) > 0


def _src_path() -> str:
    src = str(Path(__file__).resolve().parent.parent.parent / "src")
    return src


def _ensure_src_in_path() -> None:
    src = _src_path()
    if src not in sys.path:
        sys.path.insert(0, src)


def _snapshot_ts_to_iso(stem: str) -> str:
    """スナップショットファイル名 YYYYMMDD-HHMMSS から ISO 8601 文字列を返す。"""
    m = _SNAPSHOT_TS_RE.search(stem)
    if not m:
        return stem
    year, month, day, hour, minute, second = m.groups()
    try:
        dt = datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))
        return dt.isoformat()
    except ValueError:
        return stem


# ─────────────────────────── GET /api/v1/sites ───────────────────────────


@bp.get("/sites")
def api_sites() -> tuple[dict, int] | dict:
    """登録済みサイト一覧を返す。"""
    _ensure_src_in_path()
    try:
        from registry.site_registry import list_sites

        configs = list_sites(OUTPUT_DIR)
        sites = [dataclasses.asdict(c) for c in configs]
        for site in sites:
            for key in ("urls", "formats"):
                if isinstance(site.get(key), list | tuple):
                    site[key] = list(site[key])
    except Exception as exc:
        logger.exception("list_sites に失敗しました: %s", exc)
        return {"error": str(exc)}, 500
    return {"sites": sites}


# ─────────────────────────── GET /api/v1/sites/<domain>/report ───────────────────────────


@bp.get("/sites/<domain>/report")
def api_report(domain: str) -> tuple[dict, int] | dict:
    """指定ドメインの最新 report.json を返す。"""
    if not _validate_domain(domain):
        return {"error": "invalid domain"}, 400
    report_path = OUTPUT_DIR / domain / "report.json"
    if not report_path.is_file():
        return {"error": "report not found"}, 404
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("report.json の読み込みに失敗しました: %s", exc)
        return {"error": "failed to read report"}, 500
    return data


# ─────────────────────────── GET /api/v1/sites/<domain>/snapshots ───────────────────────────


@bp.get("/sites/<domain>/snapshots")
def api_snapshots(domain: str) -> tuple[dict, int] | dict:
    """スナップショット一覧（ファイル名・タイムスタンプ）を返す。"""
    if not _validate_domain(domain):
        return {"error": "invalid domain"}, 400
    snaps_dir = OUTPUT_DIR / domain / "snapshots"
    items: list[dict] = []
    if snaps_dir.is_dir():
        for f in sorted(snaps_dir.glob("*.json")):
            items.append({"name": f.name, "created_at": _snapshot_ts_to_iso(f.stem)})
    return {"domain": domain, "snapshots": items}


# ─────────────────────────── GET /api/v1/sites/<domain>/diff ───────────────────────────


@bp.get("/sites/<domain>/diff")
def api_diff(domain: str) -> tuple[dict, int] | dict:
    """最新 2 スナップショットの差分を返す。"""
    if not _validate_domain(domain):
        return {"error": "invalid domain"}, 400
    _ensure_src_in_path()
    domain_dir = OUTPUT_DIR / domain
    snaps_dir = domain_dir / "snapshots"
    if not snaps_dir.is_dir():
        return {"error": "need at least 2 snapshots"}, 404
    snap_files = sorted(snaps_dir.glob("*.json"))
    if len(snap_files) < 2:
        return {"error": "need at least 2 snapshots"}, 404
    try:
        from diff.differ import compute_diff
        from diff.snapshot import load_snapshot

        old_pages = load_snapshot(snap_files[-2])
        new_pages = load_snapshot(snap_files[-1])
        diff_result = compute_diff(old_pages, new_pages)
    except Exception as exc:
        logger.exception("差分計算に失敗しました: %s", exc)
        return {"error": str(exc)}, 500
    return dataclasses.asdict(diff_result)


# ─────────────────────────── POST /api/v1/sites/<domain>/crawl ───────────────────────────


@bp.post("/sites/<domain>/crawl")
def api_crawl(domain: str) -> tuple[dict, int] | dict:
    """非同期クロールをトリガーする（スタブ実装）。"""
    if not _validate_domain(domain):
        return {"error": "invalid domain"}, 400
    body = request.get_json(silent=True) or {}
    logger.info(
        "api_v1 crawl requested: domain=%s depth=%s max_pages=%s format=%s",
        domain,
        body.get("depth"),
        body.get("max_pages"),
        body.get("format"),
    )
    job_id = uuid.uuid4().hex
    return {"job_id": job_id, "status": "queued", "message": "not yet implemented"}, 501


# ─────────────────────────── GET /api/v1/sites/<domain>/test-cases ───────────────────────────


@bp.get("/sites/<domain>/test-cases")
def api_test_cases(domain: str) -> tuple[dict, int] | dict:
    """最新の playwright_candidates.json のテストケース一覧を返す。"""
    if not _validate_domain(domain):
        return {"error": "invalid domain"}, 400
    candidates_path = OUTPUT_DIR / domain / "playwright_candidates.json"
    if not candidates_path.is_file():
        return {"domain": domain, "total": 0, "candidates": []}
    try:
        data = json.loads(candidates_path.read_text(encoding="utf-8"))
        candidates: list = data.get("candidates", [])
    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("playwright_candidates.json の読み込みに失敗しました: %s", exc)
        return {"domain": domain, "total": 0, "candidates": []}
    return {"domain": domain, "total": len(candidates), "candidates": candidates}
