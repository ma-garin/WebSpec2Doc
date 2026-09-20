from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

from flask import Blueprint, Response, request, send_file

from web.config import MAX_DEPTH, MAX_PAGES_LIMIT, MAX_PARALLELISM, OUTPUT_DIR
from web.process import _RUNNING_PROCS, _terminate_proc
from web.services import app_mock
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

# 解析範囲プリセットの許可リスト。表示名は usage_tracker._SCOPE_PRESET_LABELS が持つ。
# ここでは値の検証だけを行い、外れた値は空へ丸める（実行を止めるほどの入力ではない）。
_SCOPE_PRESETS = frozenset({"one-page", "standard", "wide", "custom"})

# 実行条件として利用実績へ渡すキー。想定外のキーで record_crawl_from_report が
# TypeError にならないよう、このリストで絞ってから渡す。
_SCOPE_RECORD_KEYS = (
    "scope_preset",
    "scope_depth",
    "scope_max_pages",
    "crawl_mode",
    "target_url_count",
    "skipped_count",
)

_CRAWL_EVENT_PREFIX = "CRAWL_EVENT:"


def _skipped_delta(line: str) -> int:
    """クロール出力の1行から「解析できずスキップした画面数」を読み取る。

    ログインウォールは検出のたびに 1 件、robots による除外は crawl_started が
    持つ URL 配列の長さでまとめて分かる。JSON として読めない行（進捗テキスト等）は
    0 を返して無視する。解釈できないことは異常ではないため例外にしない。
    """
    text = line.strip()
    if not text.startswith(_CRAWL_EVENT_PREFIX):
        return 0
    try:
        payload = json.loads(text[len(_CRAWL_EVENT_PREFIX) :])
    except (ValueError, TypeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    event = payload.get("event")
    if event == "login_wall_detected":
        return 1
    if event == "crawl_started":
        skipped = payload.get("robots_skipped_urls")
        return len(skipped) if isinstance(skipped, list) else 0
    return 0


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
    parallelism = str(_clean_int(request.form.get("parallelism", "4"), 4, 1, MAX_PARALLELISM))
    # 既存サイトの再解析では、呼び出し側が既にディレクトリ名を知っている。
    # それを渡してもらい、URL のホストから作り直して別サイトを増やすのを防ぐ。
    domain_name = request.form.get("domain_name", "").strip()
    if domain_name in {".", ".."} or "/" in domain_name or "\\" in domain_name:
        domain_name = ""
    domain = domain_name or (_domain_of(urls.split(",")[0]) if urls else "")
    reference_docs = _safe_reference_doc_paths(request.form.get("reference_docs", ""), domain)

    # 実行条件（解析範囲）。実行履歴に「どの範囲を解析した結果か」を残すためだけの値で、
    # クロール自体の引数には使わない（depth/max_pages は既存フィールドが持つ）。
    # 未送信のフィールドは 0 / 空のままにし、記録側でキーごと落とす。
    scope_preset = request.form.get("scope_preset", "").strip()
    if scope_preset not in _SCOPE_PRESETS:
        scope_preset = ""
    raw_scope_depth = request.form.get("scope_depth", "").strip()
    raw_scope_max_pages = request.form.get("scope_max_pages", "").strip()
    scope_record = {
        "scope_preset": scope_preset,
        "scope_depth": (_clean_int(raw_scope_depth, 2, 1, MAX_DEPTH) if raw_scope_depth else 0),
        "scope_max_pages": (
            _clean_int(raw_scope_max_pages, 30, 1, MAX_PAGES_LIMIT) if raw_scope_max_pages else 0
        ),
        # 実行時にどちらのモードだったかは site.json ではなく履歴側でも要る
        # （後から site.json を書き換えても、過去の実行の条件は変わらないため）。
        "crawl_mode": "auto" if crawl_mode == "auto" else "selected",
        "target_url_count": len([u for u in urls.split(",") if u]),
    }

    run_id = uuid.uuid4().hex
    # ストリーミング応答のジェネレータはリクエストコンテキスト外で実行されるため、
    # テナントスコープ済みの出力先はここ（リクエスト処理中）で解決して閉じ込める。
    out_dir = _out()
    if app_mock.is_app_target(urls.split(",")[0] if urls else ""):
        # ドキュメント作成(app) のモック。成果物は実物と同じ場所に置くので、以降の
        # /api/result・/api/live-screenshot・レポート画面はそのまま動く。
        return Response(
            app_mock.run_stream(run_id, domain, out_dir, urls, _summary_for_domain),
            mimetype="text/plain",
        )

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
        if domain_name:
            cmd += ["--domain-name", domain_name]
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
        skipped_count = 0
        try:
            yield f"RUN_ID:{run_id}\n"
            # 行は一切加工せずそのまま流す（クライアントの表示・パースを壊さないため）。
            # 横でスキップ件数だけ数え、実行条件と一緒に履歴へ残す。
            for line in proc.stdout:
                skipped_count += _skipped_delta(line)
                yield line
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
                _record_usage_safely(
                    domain,
                    compare,
                    out_dir,
                    scope={**scope_record, "skipped_count": skipped_count},
                )
            if proc.returncode != 0:
                yield "\nエラーが発生しました。\n"
        finally:
            _RUNNING_PROCS.pop(run_id, None)
            _terminate_proc(proc)

    return Response(generate(), mimetype="text/plain")


def _record_usage_safely(
    domain: str,
    compare: bool,
    out_dir: Path | None = None,
    *,
    scope: dict | None = None,
) -> None:
    """成果物を実行回ごとに退避し、利用実績を記録する。

    どちらもベストエフォート。失敗してもクロール成功の応答は返す
    （成果物そのものは従来どおり output/<domain>/ に残っているため）。

    scope は実行条件（解析範囲）。キーは record_crawl_from_report の
    キーワード引数名に対応し、渡された分だけ usage_log の行に載る。
    """
    root = out_dir if out_dir is not None else OUTPUT_DIR
    scope_kwargs = {k: scope[k] for k in _SCOPE_RECORD_KEYS if scope and k in scope}
    try:
        from web.services.run_store import snapshot_run
        from web.services.usage_tracker import record_crawl_from_report

        # 生成側には手を入れず、終わった時点の成果物をこの実行回として写し取る。
        # これをしないと成果物はサイト単位で上書きされ、履歴の全行が同じ中身を指す。
        run_id = snapshot_run(
            root,
            domain,
            event="crawl",
            summary=_summary_for_domain(domain, root),
        )
        record_crawl_from_report(
            root, domain, diff_run=compare, run_id=run_id or "", **scope_kwargs
        )
    except Exception:  # noqa: BLE001
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
