from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

from flask import Blueprint, Response, request, send_file

from web.config import MAX_DEPTH, MAX_PAGES_LIMIT, OUTPUT_DIR
from web.process import _RUNNING_PROCS, _terminate_proc
from web.summary import _summary_for_domain
from web.tenancy import scoped_output_dir
from web.validation import (
    _clean_formats,
    _clean_int,
    _domain_of,
    _safe_auth_path,
    _safe_reference_doc_paths,
    _valid_domain,
)

bp = Blueprint("crawl", __name__)

_REFERENCE_DIR_NAME = "reference_docs"
_MAX_REFERENCE_DOC_BYTES = 20 * 1024 * 1024  # 20MB/ファイル


def _out() -> Path:
    """テナントスコープ済みの出力ディレクトリ（リクエスト毎に解決）。"""
    return scoped_output_dir(OUTPUT_DIR)


@bp.post("/run")
def run() -> Response:
    from web.routes.site import save_site_config

    urls = request.form.get("urls", "").strip()
    # 認証が必要と判定された画面（urls の部分集合）。再クロール時にログイン必須の
    # バナー・フォームを復元するため site.json に持ち回る（save_site_config 参照）。
    url_set = {u for u in urls.split(",") if u}
    login_urls = ",".join(
        u for u in (request.form.get("login_urls", "").strip().split(",")) if u and u in url_set
    )
    login_landing_url = request.form.get("login_landing_url", "").strip()
    depth = str(_clean_int(request.form.get("depth", "2"), 2, 1, MAX_DEPTH))
    max_pages = str(_clean_int(request.form.get("max_pages", "30"), 30, 1, MAX_PAGES_LIMIT))
    # 出力形式は許可リストで検証。report.json は結果ページのデータ源なので常に生成する
    selected = _clean_formats(request.form.get("format", "md,html")) or ["md", "html"]
    if "json" not in selected:
        selected.append("json")
    fmt = ",".join(selected)
    compare = request.form.get("compare", "false") == "true"
    auth = _safe_auth_path(request.form.get("auth", "").strip())
    crawl_mode = request.form.get("crawl_mode", "").strip()
    parallelism = str(_clean_int(request.form.get("parallelism", "2"), 2, 1, 4))
    domain = _domain_of(urls.split(",")[0]) if urls else ""
    reference_docs = _safe_reference_doc_paths(request.form.get("reference_docs", ""), domain)

    run_id = uuid.uuid4().hex
    # ストリーミング応答のジェネレータはリクエストコンテキスト外で実行されるため、
    # テナントスコープ済みの出力先はここ（リクエスト処理中）で解決して閉じ込める。
    out_dir = _out()

    def generate():
        # crawl_mode == "auto": 起点URLからリンクを辿って自動探索する（--url + depth）。
        # それ以外（既定）: 画面分析で選択された固定URL一覧のみをクロールする（--urls）。
        # 選択したURLのみモードでは depth/max_pages はリンク追跡をしないため無関係。
        if crawl_mode == "auto":
            root_url = urls.split(",")[0] if urls else ""
            target_args = ["--url", root_url, "--depth", depth, "--max-pages", max_pages]
        else:
            target_args = ["--urls", urls]
        cmd = [
            sys.executable,
            "src/main.py",
            *target_args,
            "--parallelism",
            parallelism,
            "--format",
            fmt,
            "--output",
            str(out_dir),
        ]
        if compare:
            cmd.append("--compare")
        if auth:
            cmd += ["--auth", auth]
        for doc_path in reference_docs:
            cmd += ["--reference-doc", doc_path]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        _RUNNING_PROCS[run_id] = proc
        try:
            yield f"RUN_ID:{run_id}\n"
            yield from proc.stdout
            proc.wait()
            if proc.returncode is not None and proc.returncode < 0:
                yield "\n停止しました。\n"
                return
            domain_dir = out_dir / domain
            report = domain_dir / "report.html"
            pdf = domain_dir / "report.pdf"
            if report.exists():
                yield f"REPORT_PATH:{report.resolve()}\n"
            if pdf.exists():
                yield f"PDF_PATH:{pdf.resolve()}\n"
            yield f"SUMMARY:{json.dumps(_summary_for_domain(domain, out_dir))}\n"
            if proc.returncode == 0 and domain:
                save_site_config(
                    domain,
                    urls,
                    crawl_mode,
                    depth,
                    max_pages,
                    selected,
                    auth,
                    login_urls,
                    login_landing_url,
                    base_dir=out_dir,
                )
                _record_usage_safely(domain, compare, out_dir)
            if proc.returncode != 0:
                yield "\nエラーが発生しました。\n"
        finally:
            _RUNNING_PROCS.pop(run_id, None)
            _terminate_proc(proc)

    return Response(generate(), mimetype="text/plain")


def _record_usage_safely(domain: str, compare: bool, out_dir: Path | None = None) -> None:
    """利用実績の記録を行う。記録失敗はクロール結果配信を妨げない。"""
    try:
        from web.services.usage_tracker import record_crawl_from_report

        record_crawl_from_report(
            out_dir if out_dir is not None else OUTPUT_DIR, domain, diff_run=compare
        )
    except Exception:  # noqa: BLE001
        # 実績記録はベストエフォート。失敗してもクロール成功の応答は返す
        pass


@bp.post("/api/cancel")
def api_cancel() -> dict:
    proc = _RUNNING_PROCS.get(request.form.get("run_id", ""))
    if proc is None:
        return {"ok": False}
    _terminate_proc(proc)
    return {"ok": True}


@bp.get("/api/live-screenshot")
def live_screenshot() -> Response:
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return Response(status=404)
    shots_dir = _out() / domain / "screenshots"
    if not shots_dir.is_dir():
        return Response(status=404)
    pngs = sorted(shots_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not pngs:
        return Response(status=404)
    resp = send_file(pngs[0].resolve(), mimetype="image/png")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.post("/api/reference-docs")
def upload_reference_docs() -> tuple[dict, int] | dict:
    """参考文書のアップロード（multipart）。output/{domain}/reference_docs/ へ保存する。"""
    from ingest.loader import _LEGACY_SUFFIXES, SUPPORTED_SUFFIXES

    domain = request.form.get("domain", "")
    if not _valid_domain(domain):
        return {"ok": False, "error": "不正なドメインです"}, 400
    uploaded = request.files.getlist("files")
    if not uploaded:
        return {"ok": False, "error": "ファイルが指定されていません"}, 400

    target_dir = (_out() / domain / _REFERENCE_DIR_NAME).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    saved: list[dict[str, str]] = []
    for file_storage in uploaded:
        # secure_filename は非ASCIIを全て落とすため使わない。
        # Path(...).name でディレクトリ部のみ剥がし、拡張子 allowlist で安全性を担保する。
        name = Path(file_storage.filename or "").name
        suffix = Path(name).suffix.lower()
        if suffix in _LEGACY_SUFFIXES:
            return {
                "ok": False,
                "error": f"旧バイナリ形式（{suffix}）は未対応です。{suffix}x 形式に変換してから指定してください: {name}",
            }, 400
        if suffix not in SUPPORTED_SUFFIXES:
            return {
                "ok": False,
                "error": f"未対応の文書形式です: {name}（対応形式: {', '.join(SUPPORTED_SUFFIXES)}）",
            }, 400
        data = file_storage.read()
        if len(data) > _MAX_REFERENCE_DOC_BYTES:
            return {
                "ok": False,
                "error": f"ファイルサイズが上限（{_MAX_REFERENCE_DOC_BYTES // (1024 * 1024)}MB）を超えています: {name}",
            }, 400
        dest = target_dir / name
        dest.write_bytes(data)
        saved.append({"name": name, "path": str(dest.resolve())})
    return {"ok": True, "saved": saved}


@bp.get("/api/doc-fusion")
def api_doc_fusion() -> tuple[dict, int]:
    """output/{domain}/doc_fusion.json をそのまま返す（無ければ 404）。"""
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    path = _out() / domain / "doc_fusion.json"
    if not path.is_file():
        return {"error": "doc_fusion.json not found"}, 404
    try:
        return json.loads(path.read_text(encoding="utf-8")), 200
    except (OSError, json.JSONDecodeError):
        return {"error": "doc_fusion.json を読み込めませんでした"}, 500
