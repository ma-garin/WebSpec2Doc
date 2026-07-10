from __future__ import annotations

import dataclasses
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from flask import Blueprint, request

from web.config import MAX_DEPTH, MAX_PAGES_LIMIT, OUTPUT_DIR
from web.tenancy import scoped_output_dir
from web.validation import _clean_int, _valid_domain, _valid_url

bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


def _out() -> Path:
    """テナントスコープ済みの出力ディレクトリ（リクエスト毎に解決）。

    /api/v1 は Bearer APIトークンでもテナントが解決される（web/auth.py）。
    """
    return scoped_output_dir(OUTPUT_DIR)


# スナップショットファイル名の日時パターン: YYYYMMDD-HHMMSS
_SNAPSHOT_TS_RE = re.compile(r"(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})")

_DEFAULT_FORMATS = ["md", "html", "json"]


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


# ─────────────────────────── GET /api/v1/healthz ───────────────────────────


@bp.get("/healthz")
def api_healthz() -> dict:
    """システムヘルスチェック。スケジューラー稼働状態を返す。"""
    from web.services.scheduler import _scheduler_started, _stop_event

    scheduler_running = _scheduler_started and not _stop_event.is_set()
    return {
        "status": "ok",
        "scheduler": {"running": scheduler_running},
        "version": "1.0",
    }


# ─────────────────────────── GET /api/v1/sites ───────────────────────────


@bp.get("/sites")
def api_sites() -> tuple[dict, int] | dict:
    """登録済みサイト一覧を返す。"""
    _ensure_src_in_path()
    try:
        from registry.site_registry import list_sites

        configs = list_sites(_out())
        sites = [dataclasses.asdict(c) for c in configs]
        for site in sites:
            for key in ("urls", "formats"):
                if isinstance(site.get(key), list | tuple):
                    site[key] = list(site[key])
    except Exception as exc:
        logger.exception("list_sites に失敗しました: %s", exc)
        return {"error": "内部エラーが発生しました。ログを確認してください。"}, 500
    return {"sites": sites}


# ─────────────────────────── GET /api/v1/sites/<domain>/report ───────────────────────────


@bp.get("/sites/<domain>/report")
def api_report(domain: str) -> tuple[dict, int] | dict:
    """指定ドメインの最新 report.json を返す。"""
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    report_path = _out() / domain / "report.json"
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
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    snaps_dir = _out() / domain / "snapshots"
    items: list[dict] = []
    if snaps_dir.is_dir():
        for f in sorted(snaps_dir.glob("*.json")):
            items.append({"name": f.name, "created_at": _snapshot_ts_to_iso(f.stem)})
    return {"domain": domain, "snapshots": items}


# ─────────────────────────── GET /api/v1/sites/<domain>/diff ───────────────────────────


@bp.get("/sites/<domain>/diff")
def api_diff(domain: str) -> tuple[dict, int] | dict:
    """最新 2 スナップショットの差分を返す。"""
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    _ensure_src_in_path()
    domain_dir = _out() / domain
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
        return {"error": "内部エラーが発生しました。ログを確認してください。"}, 500
    return dataclasses.asdict(diff_result)


# ─────────────────────────── POST /api/v1/sites/<domain>/crawl ───────────────────────────


@bp.post("/sites/<domain>/crawl")
def api_crawl(domain: str) -> tuple[dict, int] | dict:
    """非同期クロールをトリガーする。job_id を返し、バックグラウンドで実行する。"""
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400

    body = request.get_json(silent=True) or {}

    # site_url: body 優先、なければ site.json から取得
    site_url = str(body.get("url", "")).strip()
    if not site_url:
        _ensure_src_in_path()
        try:
            from registry.site_registry import load_site

            config = load_site(domain, _out())
            if config and config.urls:
                site_url = config.urls[0]
        except Exception:
            pass
    if not site_url:
        return {"error": "url は必須です。body に url を指定してください。"}, 400
    if not _valid_url(site_url):
        return {"error": "invalid url: http/https のみ対応しています"}, 400

    depth = _clean_int(str(body.get("depth", 2)), default=2, lo=1, hi=MAX_DEPTH)
    max_pages = _clean_int(str(body.get("max_pages", 30)), default=30, lo=1, hi=MAX_PAGES_LIMIT)
    compare = bool(body.get("compare", True))

    from web.services.job_queue import start_crawl_job

    job_id = start_crawl_job(
        domain=domain,
        site_url=site_url,
        depth=depth,
        max_pages=max_pages,
        formats=_DEFAULT_FORMATS,
        compare=compare,
        output_dir=_out(),
    )
    logger.info("crawl job queued: domain=%s job_id=%s url=%s", domain, job_id, site_url)
    return {"job_id": job_id, "status": "queued", "domain": domain}, 202


# ─────────────────────────── GET /api/v1/jobs/<job_id> ───────────────────────────


@bp.get("/jobs/<job_id>")
def api_job_status(job_id: str) -> tuple[dict, int] | dict:
    """クロールジョブの現在の状態を返す。"""
    from web.services.job_queue import get_job

    job = get_job(job_id)
    if job is None:
        return {"error": "job not found"}, 404
    return dataclasses.asdict(job)


# ─────────────────────────── GET /api/v1/sites/<domain>/jobs ───────────────────────────


@bp.get("/sites/<domain>/jobs")
def api_domain_jobs(domain: str) -> tuple[dict, int] | dict:
    """ドメインのジョブ履歴一覧を返す（新しい順、最大20件）。"""
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    from web.services.job_queue import list_jobs_for_domain

    jobs = list_jobs_for_domain(domain)
    return {"domain": domain, "jobs": [dataclasses.asdict(j) for j in jobs]}


# ─────────────────────────── GET /api/v1/sites/<domain>/test-cases ───────────────────────────


@bp.get("/sites/<domain>/test-cases")
def api_test_cases(domain: str) -> tuple[dict, int] | dict:
    """最新の playwright_candidates.json のテストケース一覧を返す。"""
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    candidates_path = _out() / domain / "playwright_candidates.json"
    if not candidates_path.is_file():
        return {"domain": domain, "total": 0, "candidates": []}
    try:
        data = json.loads(candidates_path.read_text(encoding="utf-8"))
        candidates: list = data.get("candidates", [])
    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("playwright_candidates.json の読み込みに失敗しました: %s", exc)
        return {"domain": domain, "total": 0, "candidates": []}
    return {"domain": domain, "total": len(candidates), "candidates": candidates}
