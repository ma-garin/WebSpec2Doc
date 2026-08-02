"""実行回ごとの成果物を返すルート（案A: 実行結果ページ = 実行回のハブ）。

実行履歴の 1 行 = 1 実行回で、そこから開く実行結果ページは
**その回の成果物**を出す。従来はサイト単位の最新 1 件しか無く、7 月の行を
開いても今日の数字が出ていた。

3 つの成果物（利用者の呼び方）と実体:

    1 実行結果         report.json         SPA のレポート画面
    2 解析結果         report.html         静的なテスト分析インプット
    3 実行結果レポート  qa_process/        AutoRun の 8 セクション

保存されていない実行回（この仕組みを入れる前のもの）は「無い」と返す。
最新の成果物で代替しない — 別の実行の中身を、その回のものとして見せないため。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Blueprint, abort, render_template, request

from web.config import OUTPUT_DIR
from web.services.run_store import (
    artifact_file,
    list_runs,
    load_meta,
    run_dir,
    valid_run_id,
)
from web.tenancy import scoped_output_dir
from web.validation import _valid_domain

bp = Blueprint("runs", __name__)
logger = logging.getLogger(__name__)

# 3 つの成果物と、その有無を決める代表ファイル。
# 画面のタブ（1/2/3）と 1 対 1 で対応させる。
_ARTIFACT_FILES: dict[str, tuple[str, ...]] = {
    "result": ("report.json",),
    "analysis": ("report.html",),
    "autorun": (
        "qa_process/playwright_report.json",
        "qa_process/stages.json",
        "qa_process/autorun.spec.ts",
    ),
}

# 実行結果タブ（1）が使う成果物。無いものは空文字で返し、画面側で「未生成」を出す。
_RESULT_FILES: dict[str, str] = {
    "json": "report.json",
    "html": "report.html",
    "pdf": "report.pdf",
    "excel": "spec.xlsx",
    "screens_md": "screens.md",
    "forms_md": "forms.md",
    "features_md": "features.md",
    "transition_mmd": "transition.mmd",
    "diff": "diff_report.html",
    "playwright_json": "testcases/run_result.json",
    "qa_process_report": "qa_process/qa_process_report.html",
    "playwright_report_json": "qa_process/playwright_report.json",
    "playwright_report_html": "qa_process/playwright_report.html",
    "spec_ts": "qa_process/autorun.spec.ts",
    "test_plan": "qa_process/test_plan.md",
    "test_analysis": "qa_process/test_analysis.md",
    "test_design": "qa_process/test_design.md",
    "test_cases": "qa_process/test_cases.md",
    "stages": "qa_process/stages.json",
}


def _out() -> Path:
    return scoped_output_dir(OUTPUT_DIR)


def _artifact_flags(root: Path, domain: str, run_id: str) -> dict[str, bool]:
    """3 つの成果物の有無。実物があるものだけ True（捏造しない）。"""
    return {
        key: any(artifact_file(root, domain, run_id, rel) is not None for rel in rels)
        for key, rels in _ARTIFACT_FILES.items()
    }


def _files_of(root: Path, domain: str, run_id: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, rel in _RESULT_FILES.items():
        path = artifact_file(root, domain, run_id, rel)
        out[key] = str(path) if path is not None else ""
    return out


@bp.get("/runs/<domain>/<run_id>")
def run_page(domain: str, run_id: str) -> str:
    """実行結果ページ（実行回のハブ）。実体の描画はクライアント側が行う。"""
    if not _valid_domain(domain) or not valid_run_id(run_id):
        abort(404)
    target = run_dir(_out(), domain, run_id)
    if target is None or not target.is_dir():
        abort(404)
    return render_template("index.html")


@bp.get("/api/runs/<domain>")
def api_runs(domain: str) -> dict | tuple[dict, int]:
    """そのサイトの実行回一覧（新しい順）。実行回セレクタが使う。"""
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    root = _out()
    runs = list_runs(root, domain)
    return {
        "domain": domain,
        "runs": runs,
        # 「現在の成果物」を作った実行回。無ければ空文字。
        "current_run_id": str(runs[0]["run_id"]) if runs else "",
        "total": len(runs),
    }


@bp.get("/api/runs/<domain>/<run_id>")
def api_run_detail(domain: str, run_id: str) -> dict | tuple[dict, int]:
    """1 実行回の中身。3 つの成果物の有無とファイルパスを返す。"""
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    if not valid_run_id(run_id):
        return {"error": "invalid run_id"}, 400
    root = _out()
    meta = load_meta(root, domain, run_id)
    if meta is None:
        return {
            "error": "この実行回の成果物は保存されていません",
            "recovery": (
                "実行回ごとの保存を入れる前の実行です。最新の成果物を代わりに出すことはしません"
                "（別の実行の中身を、この実行のものとして見せないため）。"
            ),
        }, 404

    runs = list_runs(root, domain)
    ids = [str(r.get("run_id", "")) for r in runs]
    idx = ids.index(run_id) if run_id in ids else -1
    payload: dict[str, Any] = {
        "domain": domain,
        "run_id": run_id,
        "meta": meta,
        "artifacts": _artifact_flags(root, domain, run_id),
        "files": _files_of(root, domain, run_id),
        "is_current": bool(ids) and ids[0] == run_id,
        # 実行回セレクタの前後移動用。端では空文字を返す。
        "newer_run_id": ids[idx - 1] if idx > 0 else "",
        "older_run_id": ids[idx + 1] if 0 <= idx < len(ids) - 1 else "",
        "position": {"index": idx + 1 if idx >= 0 else 0, "total": len(ids)},
    }
    return payload


@bp.get("/api/runs/<domain>/<run_id>/exists")
def api_run_exists(domain: str, run_id: str) -> dict | tuple[dict, int]:
    """実行回の成果物があるかだけを返す（一覧の行が導線を出すかの判断用）。"""
    if not _valid_domain(domain) or not valid_run_id(run_id):
        return {"exists": False}, 200
    target = run_dir(_out(), domain, run_id)
    exists = target is not None and (target / "meta.json").is_file()
    return {"exists": exists, "run_id": run_id if exists else ""}


@bp.get("/api/runs/<domain>/<run_id>/artifact")
def api_run_artifact(domain: str, run_id: str) -> dict | tuple[dict, int]:
    """実行回の成果物ファイルの実パスを返す（/preview で開くために使う）。"""
    if not _valid_domain(domain) or not valid_run_id(run_id):
        return {"error": "not found"}, 404
    relative = request.args.get("name", "")
    path = artifact_file(_out(), domain, run_id, relative)
    if path is None:
        return {"error": "この実行回にその成果物はありません", "name": relative}, 404
    return {"path": str(path), "name": relative}
