from __future__ import annotations

import io
import json
import logging
import subprocess
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from flask import Blueprint, Response, make_response, redirect, request, send_file, url_for

from web.config import _PREVIEW_MIME, OUTPUT_DIR
from web.services.admin_audit import append_admin_audit
from web.services.spec_ts_generator import generate_spec_ts
from web.summary import _summary_for_domain
from web.tenancy import current_auth_user, scoped_instance_path, scoped_output_dir
from web.validation import _safe_output_path, _valid_domain

bp = Blueprint("report", __name__)
INSTANCE_DIR = Path("instance")
logger = logging.getLogger(__name__)


def _out() -> Path:
    """テナントスコープ済みの出力ディレクトリ（リクエスト毎に解決）。"""
    return scoped_output_dir(OUTPUT_DIR)


def _record_export(target_id: str, detail: dict[str, object] | None = None) -> None:
    actor = current_auth_user() or {}
    try:
        append_admin_audit(
            scoped_instance_path(INSTANCE_DIR / "admin_audit.jsonl"),
            action="report.exported",
            actor_id=str(actor.get("id", "")),
            actor_email=str(actor.get("email", "local-admin")),
            target_type="report",
            target_id=target_id,
            detail=detail,
        )
    except OSError as exc:
        logger.warning("レポート出力の監査ログ保存に失敗しました: %s", exc)


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
    try:
        target_id = str(target.resolve().relative_to(_out().resolve()))
    except ValueError:
        target_id = target.name
    _record_export(target_id, {"format": target.suffix.lower().lstrip(".")})
    return send_file(target, as_attachment=True, download_name=target.name)


@bp.get("/download-zip")
def download_zip() -> Response:
    """ドメイン配下をZIP化する。`paths`（複数値・カンマ区切りいずれも可）を指定した場合は
    そのファイルのみをZIP化する（ギャラリー一括エクスポート等の選択ダウンロード用）。
    未指定時は従来通りドメイン配下全件。"""
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return Response(status=404)
    out_dir = _out()
    base = (out_dir / domain).resolve()
    if out_dir.resolve() not in base.parents or not base.is_dir():
        return Response(status=404)
    selected = _selected_zip_paths(base, request.args.getlist("paths"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        files = selected if selected is not None else (f for f in base.rglob("*") if f.is_file())
        for f in files:
            zf.write(f, f.relative_to(base.parent))
    buf.seek(0)
    _record_export(f"{domain}/{domain}.zip", {"format": "zip", "selected": selected is not None})
    return send_file(
        buf, as_attachment=True, download_name=f"{domain}.zip", mimetype="application/zip"
    )


def _selected_zip_paths(base: Path, raw_values: list[str]) -> list[Path] | None:
    """`paths` クエリ（配列またはカンマ区切り）を実在・ドメイン配下検証済みの絶対パスへ変換する。

    `paths` が一切指定されていない場合は None を返し、呼び出し側でドメイン全体の
    ZIP化にフォールバックさせる。指定された値のうち検証を通らないものは無視する
    （path traversal・他ドメインのファイル指定を許さない）。
    """
    if not raw_values:
        return None
    candidates = [part for value in raw_values for part in value.split(",") if part.strip()]
    resolved = (_safe_output_path(candidate) for candidate in candidates)
    return [path for path in resolved if path is not None and base in path.parents]


@bp.get("/api/report/<domain>/spec-ts")
def download_spec_ts(domain: str) -> Response | tuple[dict, int]:
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    out_dir = _out()
    candidates_path = out_dir / domain / "qa_process" / "playwright_candidates.json"
    if not candidates_path.exists():
        candidates_path = out_dir / domain / "qa" / "playwright_candidates.json"
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
    _record_export(f"{domain}/{domain}.spec.ts", {"format": "typescript"})
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{domain}.spec.ts",
        mimetype="text/plain",
    )


def _generate_features_md_if_missing(domain_dir: Path) -> None:
    """report.jsonから機能一覧（features.md）を導出し、未生成なら書き出す。

    新規クロールを要求せず既存 report.json のみから導出するため、過去に生成済みの
    ドメインでも初回アクセス時に自動生成される。生成失敗は結果表示を妨げない。
    """
    features_path = domain_dir / "features.md"
    if features_path.is_file():
        return
    report_json = domain_dir / "report.json"
    if not report_json.is_file():
        return
    try:
        data = json.loads(report_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    screens = [
        screen
        for screen in data.get("screens", [])
        if isinstance(screen, dict) and screen.get("is_canonical", True)
    ]
    from generator.feature_catalog import generate_features_markdown

    try:
        features_path.write_text(generate_features_markdown(screens), encoding="utf-8")
    except OSError:
        pass


@bp.get("/api/result")
def api_result() -> dict | tuple[dict, int]:
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    domain_dir = _out() / domain
    domain_root = domain_dir.resolve()
    if not domain_dir.is_dir() or domain_dir.is_symlink():
        return {"error": "not found"}, 404

    def path_of(name: str) -> str:
        candidate = domain_dir / name
        resolved = candidate.resolve()
        if (
            resolved == domain_root
            or domain_root not in resolved.parents
            or candidate.is_symlink()
            or not resolved.is_file()
        ):
            return ""
        return str(resolved)

    shots_dir = domain_dir / "screenshots"
    shots = sorted(shots_dir.glob("*.png")) if shots_dir.is_dir() else []
    snap_dir = domain_dir / "snapshots"
    snapshot_count = len(list(snap_dir.glob("*.json"))) if snap_dir.is_dir() else 0
    _generate_features_md_if_missing(domain_dir)

    # AutoRun / QAプロセスの成果物（qa_process/ 配下）。「テスト実行」タブのデータソース。
    pw_json = domain_dir / "qa_process" / "playwright_report.json"
    pw_html_native = domain_dir / "qa_process" / "playwright-report" / "index.html"
    pw_html_fallback = domain_dir / "qa_process" / "playwright_report.html"
    # 既定は日本語サマリ（playwright_report.html）。開発者向けの Playwright
    # ネイティブレポート（スクショ・トレース付き）は playwright_native_html で別途提供する。
    pw_html = pw_html_fallback if path_of("qa_process/playwright_report.html") else pw_html_native
    playwright_run_at = ""
    if path_of("qa_process/playwright_report.json"):
        playwright_run_at = (
            datetime.fromtimestamp(pw_json.stat().st_mtime, tz=UTC)
            .isoformat()
            .replace("+00:00", "Z")
        )
    return {
        "summary": _summary_for_domain(domain, _out()),
        "snapshot_count": snapshot_count,
        "files": {
            "html": path_of("report.html"),
            "pdf": path_of("report.pdf"),
            "json": path_of("report.json"),
            "excel": path_of("spec.xlsx"),
            "screens_md": path_of("screens.md"),
            "forms_md": path_of("forms.md"),
            "features_md": path_of("features.md"),
            "transition_mmd": path_of("transition.mmd"),
            "diff": path_of("diff_report.html"),
            "playwright_json": path_of("qa_process/playwright_report.json"),
            "playwright_html": path_of(str(pw_html.relative_to(domain_dir))),
            "playwright_native_html": path_of("qa_process/playwright-report/index.html"),
            "spec_ts": path_of("qa_process/autorun.spec.ts"),
            "qa_process_report": path_of("qa_process/qa_process_report.html"),
            "exploration_heatmap": path_of("exploration_heatmap.html"),
            "exploration_json": path_of("exploration_coverage.json"),
        },
        "playwright_run_at": playwright_run_at,
        "screenshots": [path for s in shots if (path := path_of(str(s.relative_to(domain_dir))))],
    }


def _analysis_coverage_screens(shots_dir: Path, screens_meta: list[dict]) -> list[dict]:
    """report.json の画面 + スクショ実在から解析カバレッジ用の画面 dict を組む。"""
    result: list[dict] = []
    for sc in screens_meta:
        pid = str(sc.get("page_id") or "")
        captured = bool(pid) and (shots_dir / f"{pid}.png").is_file()
        result.append(
            {
                "page_id": pid,
                "title": sc.get("title") or "",
                "url": sc.get("url") or "",
                "captured": captured,
                "requires_login": bool(sc.get("requires_login") or sc.get("is_login_required")),
            }
        )
    return result


def _autorun_coverage_screens(domain_dir: Path, screens_meta: list[dict]) -> list[dict]:
    """playwright_report.json のテスト結果を画面へ決定的にマッピングする（捏造しない）。

    テスト title/name/file に page_id またはタイトルが含まれる場合のみ計上する。
    対応が取れない画面は runs=0（未実行）として正直に扱う。
    """
    pw_path = domain_dir / "qa_process" / "playwright_report.json"
    tests: list[dict] = []
    if pw_path.is_file():
        try:
            data = json.loads(pw_path.read_text(encoding="utf-8"))
            tests = data.get("tests") or []
        except (OSError, json.JSONDecodeError):
            tests = []
    result: list[dict] = []
    for sc in screens_meta:
        pid = str(sc.get("page_id") or "")
        title = str(sc.get("title") or "")
        runs = passed = failed = 0
        for t in tests:
            hay = f"{t.get('title', '')} {t.get('name', '')} {t.get('file', '')}"
            if (pid and pid in hay) or (len(title) >= 4 and title in hay):
                runs += 1
                status = str(t.get("status") or t.get("outcome") or "").lower()
                if status in ("passed", "expected", "ok"):
                    passed += 1
                elif status:
                    failed += 1
        result.append(
            {
                "page_id": pid,
                "title": title,
                "url": sc.get("url") or "",
                "runs": runs,
                "passed": passed,
                "failed": failed,
            }
        )
    return result


@bp.get("/api/coverage-heatmap")
def api_coverage_heatmap() -> Response:
    """カバレッジヒートマップ（kind=analysis: 取得状況3色 / kind=autorun: 実行回数×成否）をHTMLで返す。"""
    domain = request.args.get("domain", "")
    kind = request.args.get("kind", "analysis")
    if not _valid_domain(domain):
        return Response(status=404)
    domain_dir = _out() / domain
    if not domain_dir.is_dir() or domain_dir.is_symlink():
        return Response(status=404)
    report_path = domain_dir / "report.json"
    if not report_path.is_file():
        return Response(
            "<p style='font-family:sans-serif;padding:16px'>レポートが見つかりません。クロールを実行してください。</p>",
            mimetype="text/html",
        )
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Response(status=500)
    screens_meta = report.get("screens") or []
    if kind == "autorun":
        from generator.heatmap_reporter import generate_autorun_coverage_html

        html_out = generate_autorun_coverage_html(
            _autorun_coverage_screens(domain_dir, screens_meta)
        )
    else:
        from generator.heatmap_reporter import generate_analysis_coverage_html

        html_out = generate_analysis_coverage_html(
            _analysis_coverage_screens(domain_dir / "screenshots", screens_meta)
        )
    resp = Response(html_out, mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.get("/open")
def open_file() -> Response:
    target = _safe_output_path(request.args.get("path", ""))
    if target is not None:
        subprocess.Popen(["open", str(target)])
    return make_response(redirect(url_for("pages.index")))
