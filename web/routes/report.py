from __future__ import annotations

import io
import subprocess
import tempfile
import zipfile
from pathlib import Path

from flask import Blueprint, Response, make_response, redirect, request, send_file, url_for

from web.config import _PREVIEW_MIME, OUTPUT_DIR
from web.services.spec_ts_generator import generate_spec_ts
from web.summary import _summary_for_domain
from web.validation import _safe_output_path, _valid_domain

bp = Blueprint("report", __name__)


@bp.get("/preview")
def preview() -> Response:
    target = _safe_output_path(request.args.get("path", ""))
    if target is None:
        return Response(status=404)
    mime = _PREVIEW_MIME.get(target.suffix.lower(), "text/plain; charset=utf-8")
    resp = send_file(target, mimetype=mime)
    resp.headers["Content-Disposition"] = "inline"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.get("/download")
def download() -> Response:
    target = _safe_output_path(request.args.get("path", ""))
    if target is None:
        return Response(status=404)
    return send_file(target, as_attachment=True, download_name=target.name)


@bp.get("/download-zip")
def download_zip() -> Response:
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return Response(status=404)
    base = (OUTPUT_DIR / domain).resolve()
    if OUTPUT_DIR.resolve() not in base.parents or not base.is_dir():
        return Response(status=404)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in base.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(base.parent))
    buf.seek(0)
    return send_file(
        buf, as_attachment=True, download_name=f"{domain}.zip", mimetype="application/zip"
    )


@bp.get("/api/report/<domain>/spec-ts")
def download_spec_ts(domain: str) -> Response | tuple[dict, int]:
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    candidates_path = OUTPUT_DIR / domain / "qa_process" / "playwright_candidates.json"
    if not candidates_path.exists():
        candidates_path = OUTPUT_DIR / domain / "qa" / "playwright_candidates.json"
    if not candidates_path.exists():
        return {"error": "playwright_candidates.json が見つかりません"}, 404
    filter_mode = request.args.get("filter", "all")
    if filter_mode not in {"all", "smoke", "transition", "form"}:
        filter_mode = "all"
    with tempfile.TemporaryDirectory() as tmp:
        output_path = Path(tmp) / f"{domain}.spec.ts"
        generate_spec_ts(domain, candidates_path, output_path, filter_mode=filter_mode)
        content = output_path.read_bytes()
    buffer = io.BytesIO(content)
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{domain}.spec.ts",
        mimetype="text/plain",
    )


@bp.get("/api/result")
def api_result() -> dict | tuple[dict, int]:
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    domain_dir = OUTPUT_DIR / domain
    if not domain_dir.is_dir():
        return {"error": "not found"}, 404

    def path_of(name: str) -> str:
        f = domain_dir / name
        return str(f.resolve()) if f.exists() else ""

    shots_dir = domain_dir / "screenshots"
    shots = sorted(shots_dir.glob("*.png")) if shots_dir.is_dir() else []
    snap_dir = domain_dir / "snapshots"
    snapshot_count = len(list(snap_dir.glob("*.json"))) if snap_dir.is_dir() else 0
    return {
        "summary": _summary_for_domain(domain),
        "snapshot_count": snapshot_count,
        "files": {
            "html": path_of("report.html"),
            "pdf": path_of("report.pdf"),
            "json": path_of("report.json"),
            "excel": path_of("spec.xlsx"),
            "screens_md": path_of("screens.md"),
            "forms_md": path_of("forms.md"),
            "techniques_md": path_of("techniques.md"),
            "transition_mmd": path_of("transition.mmd"),
            "diff": path_of("diff_report.html"),
        },
        "screenshots": [str(s.resolve()) for s in shots],
    }


@bp.get("/open")
def open_file() -> Response:
    target = _safe_output_path(request.args.get("path", ""))
    if target is not None:
        subprocess.Popen(["open", str(target)])
    return make_response(redirect(url_for("pages.index")))
