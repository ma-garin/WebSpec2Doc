from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from flask import Blueprint, Response, request

from web.config import OUTPUT_DIR
from web.summary import _fmt_snap_ts, _summary_for_domain
from web.validation import _safe_output_path, _valid_domain

bp = Blueprint("history", __name__)


@bp.get("/api/history")
def api_history() -> dict:
    items: list[dict] = []
    if OUTPUT_DIR.is_dir():
        domains = [d for d in OUTPUT_DIR.iterdir() if d.is_dir()]
        for d in sorted(domains, key=lambda p: p.stat().st_mtime, reverse=True):
            summary = _summary_for_domain(d.name)
            formats = [
                name
                for name, fname in (
                    ("HTML", "report.html"),
                    ("PDF", "report.pdf"),
                    ("Excel", "spec.xlsx"),
                    ("JSON", "report.json"),
                    ("MD", "screens.md"),
                    ("差分", "diff_report.html"),
                )
                if (d / fname).exists()
            ]
            snap_dir = d / "snapshots"
            snapshot_count = len(list(snap_dir.glob("*.json"))) if snap_dir.is_dir() else 0
            mtime = d.stat().st_mtime
            items.append(
                {
                    "domain": d.name,
                    "screens": summary.get("screens", 0),
                    "fields": summary.get("fields", 0),
                    "updated": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
                    "updated_ts": int(mtime),
                    "formats": formats,
                    "snapshot_count": snapshot_count,
                    "has_diff": (d / "diff_report.html").exists(),
                }
            )
    return {"items": items}


@bp.delete("/api/site/<domain>")
def api_delete_site(domain: str) -> dict | tuple[dict, int]:
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    target_dir = OUTPUT_DIR / domain
    # OUTPUT_DIR の外に出ないことをローカル参照で確認（_safe_output_path はモジュールレベルの定数を使うため）
    try:
        resolved = target_dir.resolve()
        base = OUTPUT_DIR.resolve()
    except (OSError, ValueError):
        return {"error": "invalid path"}, 400
    if base not in resolved.parents:
        return {"error": "invalid path"}, 400
    if not target_dir.is_dir():
        return {"error": "not found"}, 404
    try:
        shutil.rmtree(str(target_dir))
    except Exception as e:
        return {"error": str(e)}, 500
    return {"ok": True, "domain": domain}


@bp.get("/api/snapshots")
def api_snapshots() -> dict | tuple[dict, int]:
    """サイトのクロール履歴（スナップショット）一覧。新しい順。"""
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    snaps_dir = OUTPUT_DIR / domain / "snapshots"
    items: list[dict] = []
    if snaps_dir.is_dir():
        for f in sorted(snaps_dir.glob("*.json"), reverse=True):
            try:
                pages = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            forms = sum(len(p.get("forms", [])) for p in pages)
            fields = sum(len(fm.get("fields", [])) for p in pages for fm in p.get("forms", []))
            items.append(
                {
                    "id": f.stem,
                    "label": _fmt_snap_ts(f.stem),
                    "screens": len(pages),
                    "forms": forms,
                    "fields": fields,
                }
            )
    return {"snapshots": items}


@bp.get("/api/snapshot-diff")
def api_snapshot_diff() -> Response:
    """2つのスナップショット間の仕様ドリフト差分をHTMLで返す。"""
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return Response(status=404)
    snaps_dir = OUTPUT_DIR / domain / "snapshots"
    from_path = _safe_output_path(str(snaps_dir / (request.args.get("from", "") + ".json")))
    to_path = _safe_output_path(str(snaps_dir / (request.args.get("to", "") + ".json")))
    if from_path is None or to_path is None:
        return Response(
            "<p style='font-family:sans-serif;padding:16px'>指定されたスナップショットが見つかりません。</p>",
            mimetype="text/html",
        )
    if str(Path("src").resolve()) not in sys.path:
        sys.path.insert(0, str(Path("src").resolve()))
    try:
        from diff.differ import compute_diff
        from diff.snapshot import load_snapshot
        from generator.diff_reporter import generate_diff_report
    except ImportError:
        return Response(status=500)
    old_pages = load_snapshot(from_path)
    new_pages = load_snapshot(to_path)
    diff = compute_diff(old_pages, new_pages)
    report_html = generate_diff_report(
        diff=diff,
        old_label=_fmt_snap_ts(from_path.stem),
        new_label=_fmt_snap_ts(to_path.stem),
        target_url=f"https://{domain}/",
    )
    resp = Response(report_html, mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store"
    return resp
