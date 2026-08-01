from __future__ import annotations

# ruff: noqa: E402, I001

import json
import logging
from typing import Any

from flask import Blueprint, request

from llm.viewpoint_generator import make_provider

# OUTPUT_DIR はテストが monkeypatch する互換ポイント（helpers._output_dir が参照）
from web.config import OUTPUT_DIR  # noqa: F401
from web.env_store import _read_env
from web.services.openai_qa import OpenAIQAError, generate_openai_qa, has_openai_api_key
from web.services.qa.advanced_generator import _advanced_payload, _testcases_payload
from web.services.qa.helpers import (
    _ai_artifact_path,
    _input_payload,
    _load_qa_viewpoints,
    _output_payload,
    _qa_summary,
    _report_json_path,
    _truthy,
)
from web.validation import _valid_domain

bp = Blueprint("qa_process", __name__)

QA_STEPS = (
    ("test_plan", "テスト計画", "test_plan.md"),
    ("test_analysis", "テスト分析", "test_analysis.md"),
    ("test_design", "テスト設計", "test_design.md"),
    ("test_cases", "テストケース", "test_cases.md"),
    ("cross_review", "横断レビュー", "cross_review.md"),
    ("qa_process_report", "QAプロセスレポート", "qa_process_report.html"),
)

QA_ADVANCED_OUTPUTS = (
    ("screen_transition_graph", "画面遷移グラフJSON", "screen_transition_graph.json"),
    ("model_graph", "モデルグラフHTML", "model_graph.html"),
    ("coverage_metrics", "カバレッジメトリクス", "coverage_metrics.json"),
    ("playwright_candidates", "Playwright候補JSON", "playwright_candidates.json"),
    ("playwright_candidates_html", "Playwright候補HTML", "playwright_candidates.html"),
    ("quality_viewpoints", "品質観点JSON", "quality_viewpoints.json"),
    ("quality_viewpoints_html", "品質観点HTML", "quality_viewpoints.html"),
)


@bp.get("/api/qa-process/input")
def api_qa_process_input() -> dict | tuple[dict, int]:
    domain = request.args.get("domain", "")
    report_path, error = _report_json_path(domain)
    if error:
        return {"error": error}, 404
    report = _load_report(report_path)
    if report is None:
        return {"error": "invalid report.json"}, 400
    return _input_payload(domain, report)


@bp.post("/api/qa-process/generate")
def api_qa_process_generate() -> dict | tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    domain = request.form.get("domain") or body.get("domain", "")
    step = request.form.get("step") or body.get("step", "all")
    use_ai = _truthy(request.form.get("use_ai") or body.get("use_ai"))
    report_path, error = _report_json_path(domain)
    if error:
        return {"error": error}, 404
    report = _load_report(report_path)
    if report is None:
        return {"error": "invalid report.json"}, 400
    ai_status: dict[str, Any] = {
        "requested": use_ai,
        "available": has_openai_api_key(),
        "used": False,
        "fallback": False,
    }
    ai_artifact = None
    if use_ai:
        env = _read_env()
        api_key = env.get("OPENAI_API_KEY", "").strip()
        model = env.get("OPENAI_MODEL", "").strip()
        provider = make_provider(api_key, model)
        viewpoints = _load_qa_viewpoints(domain, report, provider=provider)
        if not ai_status["available"]:
            ai_status |= {
                "fallback": True,
                "error": "OPENAI_API_KEY が設定されていないためテンプレート生成に切り替えました。",
            }
        else:
            try:
                ai_artifact = generate_openai_qa(domain, report, viewpoints)
                _ai_artifact_path(domain).write_text(
                    json.dumps(ai_artifact, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                ai_status |= {"used": True, "model": ai_artifact.get("model", "")}
            except OpenAIQAError as exc:
                ai_artifact = None
                ai_status |= {"fallback": True, "error": str(exc)}
    outputs = _generate_outputs(domain, report, ai_artifact)
    outputs |= _generate_advanced_outputs(domain, report)
    selected = outputs.get(step) or outputs["qa_process_report"]
    return {
        "ok": True,
        "domain": domain,
        "step": step,
        "selected": str(selected.resolve()),
        "outputs": _output_payload(domain),
        "summary": _qa_summary(report),
        "ai": ai_status,
        "ai_artifact": ai_artifact,
        "advanced": _advanced_payload(domain, report),
    }


@bp.get("/api/qa-process/result")
def api_qa_process_result() -> dict | tuple[dict, int]:
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    from web.services.qa.helpers import _output_dir

    if not (_output_dir() / domain).is_dir():
        return {"error": "not found"}, 404
    return {"domain": domain, "outputs": _output_payload(domain)}


@bp.get("/api/testcases")
def api_testcases() -> dict | tuple[dict, int]:
    domain = request.args.get("domain", "")
    report_path, error = _report_json_path(domain)
    if error:
        return {"error": error}, 404
    report = _load_report(report_path)
    if report is None:
        return {"error": "invalid report.json"}, 400
    return _testcases_payload(domain, report)


def _table_request() -> tuple[str, dict[str, Any] | None, dict | None]:
    """テストケース表 API 共通の引数取り出し（domain と report.json）。"""
    body = request.get_json(silent=True) or {}
    domain = request.args.get("domain") or request.form.get("domain") or body.get("domain", "")
    report_path, error = _report_json_path(domain)
    if error:
        return domain, None, {"error": error}
    report = _load_report(report_path)
    if report is None:
        return domain, None, {"error": "invalid report.json"}
    return domain, report, None


@bp.get("/api/testcases/table")
def api_testcases_table() -> dict | tuple[dict, int]:
    """9 列のローレベルテストケース表（生成値＋ユーザー編集）を返す。"""
    from web.services.testcase_table_store import compose

    domain, report, error = _table_request()
    if error:
        return error, 404
    assert report is not None
    return compose(domain, report)


@bp.get("/api/testcases/count")
def api_testcases_count() -> dict | tuple[dict, int]:
    """テストケース件数だけを返す。

    タブを開く前に件数バッジを出すための軽量経路。表本体（/api/testcases/table）は
    全行を返すため、件数表示のためだけに呼ばない。
    """
    from web.services.testcase_table_store import compose

    domain, report, error = _table_request()
    if error:
        return error, 404
    assert report is not None
    return {"domain": domain, "count": len(compose(domain, report).get("rows", []))}


@bp.get("/api/testcases/history")
def api_testcases_history() -> dict | tuple[dict, int]:
    from web.services.testcase_table_store import load_history

    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    limit = request.args.get("limit", type=int) or 200
    return {"domain": domain, "items": load_history(domain, limit=limit)}


@bp.post("/api/testcases/cell")
def api_testcases_cell() -> dict | tuple[dict, int]:
    """1 セルを更新する。value は文字列、または list 列なら配列。"""
    from web.services.testcase_table_store import TestcaseStoreError, update_cell

    body = request.get_json(silent=True) or {}
    domain, report, error = _table_request()
    if error:
        return error, 404
    assert report is not None
    try:
        return update_cell(
            domain,
            report,
            str(body.get("case_id", "")),
            str(body.get("column", "")),
            body.get("value", ""),
        )
    except TestcaseStoreError as exc:
        return {"error": str(exc)}, 400


@bp.post("/api/testcases/cell/reset")
def api_testcases_cell_reset() -> dict | tuple[dict, int]:
    from web.services.testcase_table_store import TestcaseStoreError, reset_cell

    body = request.get_json(silent=True) or {}
    domain, report, error = _table_request()
    if error:
        return error, 404
    assert report is not None
    try:
        return reset_cell(domain, report, str(body.get("case_id", "")), str(body.get("column", "")))
    except TestcaseStoreError as exc:
        return {"error": str(exc)}, 400


@bp.post("/api/testcases/run")
def api_testcases_run() -> dict | tuple[dict, int]:
    """テストケース表から Playwright spec を生成し、その場で実行して結果を保存する。

    実行対象は「自動化判定＝自動化可」かつ実行操作・検証を持つ行のみ。
    body の case_ids を指定すると、その行だけに絞って実行する（画面の絞り込み結果を実行する用途）。
    """
    from datetime import datetime
    from pathlib import Path

    from crawler.url_safety import _local_targets_allowed
    from web.services.egress_gateway import EgressPolicy
    from web.services.playwright_executor import run_playwright
    from web.services.testcase_spec_generator import SpecGenerationError, generate_spec
    from web.services.testcase_table_store import compose, run_dir, save_run_result

    body = request.get_json(silent=True) or {}
    domain, report, error = _table_request()
    if error:
        return error, 404
    assert report is not None

    payload = compose(domain, report)
    rows = payload["rows"]
    wanted = body.get("case_ids")
    if isinstance(wanted, list) and wanted:
        allow = {str(x) for x in wanted}
        rows = [r for r in rows if r["case_id"] in allow]

    out_dir = run_dir(domain)
    try:
        gen = generate_spec(rows, Path(out_dir))
    except SpecGenerationError as exc:
        return {"error": str(exc)}, 400

    # 前回の進捗を先に消す。残したままだと、実行開始からレポーターがファイルを
    # 作り直すまでの数秒間、/api/testcases/live-progress が前回の完了状態を
    # 「今の進捗」として返してしまう。
    stale_progress = Path(out_dir) / "playwright_progress.ndjson"
    if stale_progress.is_file():
        stale_progress.unlink()

    # ローカル対象の許可は運用者の明示設定（WEBSPEC2DOC_ALLOW_LOCAL=1）にのみ従う
    result = run_playwright(
        Path(gen["spec_path"]),
        Path(out_dir),
        per_test_timeout_sec=int(body.get("per_test_timeout_sec") or 20),
        egress_policy=EgressPolicy(allow_local=_local_targets_allowed()),
        headed=bool(body.get("headed")),
    )
    saved = save_run_result(domain, result, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return {
        "ok": bool(result.get("ok")),
        "generated": gen,
        "run": saved,
        "error": str(result.get("error") or ""),
    }


@bp.get("/api/testcases/live-progress")
def api_testcases_live_progress() -> dict | tuple[dict, int]:
    """実行中のテスト進捗を返す。実行完了を待たずに、その時点までの結果を読む。

    Playwright の進捗レポーターが onTestEnd ごとに追記する NDJSON をそのまま読むため、
    /api/testcases/run が応答を返す前でも「今どこまで終わったか」が分かる。
    ファイルが無い（まだ実行していない）場合は total=0 / tests=[] を返す。
    ここで件数を推測して埋めることはしない。
    """
    from web.services.playwright_executor import _read_progress_ndjson
    from web.services.testcase_table_store import run_dir

    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return {"error": "domain が不正です"}, 400

    total, tests = _read_progress_ndjson(run_dir(domain) / "playwright_progress.ndjson")
    return {
        "total": total or 0,
        "done": len(tests),
        "passed": sum(1 for t in tests if t.get("status") == "passed"),
        "failed": sum(1 for t in tests if t.get("status") == "failed"),
        # 画面に出すのは直近分だけでよい（全件は完了後の run_result.json が持つ）
        "tests": tests[-40:],
    }


@bp.get("/api/testcases/live-screenshot")
def api_testcases_live_screenshot() -> Any:
    """実行中の最新スクリーンショットを返す（config の screenshot:'on' が
    testcases/test-results/ 配下に生成する PNG のうち、最終更新が新しいもの）。

    AutoRun 側の /api/autorun/live-screenshot と同じパターン。
    """
    from flask import Response, send_file

    from web.services.testcase_table_store import run_dir

    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return Response(status=404)

    results_dir = run_dir(domain) / "test-results"
    if not results_dir.is_dir():
        return Response(status=404)
    pngs = sorted(results_dir.rglob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not pngs:
        return Response(status=404)
    resp = send_file(pngs[0].resolve(), mimetype="image/png")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.post("/api/testcases/row")
def api_testcases_row() -> dict | tuple[dict, int]:
    """行の追加・削除・復元。action で切り替える。"""
    from web.services.testcase_table_store import add_row, delete_row, restore_row

    body = request.get_json(silent=True) or {}
    domain, report, error = _table_request()
    if error:
        return error, 404
    assert report is not None
    action = str(body.get("action", ""))
    case_id = str(body.get("case_id", ""))
    if action == "add":
        return add_row(domain, report, case_id)
    if action == "delete":
        if not case_id:
            return {"error": "case_id が必要です"}, 400
        return delete_row(domain, case_id)
    if action == "restore":
        if not case_id:
            return {"error": "case_id が必要です"}, 400
        return restore_row(domain, case_id)
    return {"error": f"不明な action です: {action}"}, 400


def _test_design_params(settings: dict[str, Any]) -> Any:
    """設定 dict から TestDesignParams を構築する（value_catalog と技法パラメータ）。"""
    from generator.test_design import TestDesignParams

    kwargs: dict[str, Any] = {"value_catalog": settings.get("value_catalog") or {}}
    if isinstance(settings.get("enabled_techniques"), list):
        kwargs["enabled_techniques"] = tuple(settings["enabled_techniques"])
    for key in ("bva_offset", "pairwise_strength", "n_switch", "max_dt_conditions"):
        if isinstance(settings.get(key), int):
            kwargs[key] = settings[key]
    return TestDesignParams(**kwargs)


@bp.get("/api/test-design")
def api_test_design() -> dict | tuple[dict, int]:
    """MBT テスト設計（BVA/DT/PW/ST）を画面ごとに生成して JSON で返す。"""
    domain = request.args.get("domain", "")
    report_path, error = _report_json_path(domain)
    if error:
        return {"error": error}, 404
    report = _load_report(report_path)
    if report is None:
        return {"error": "invalid report.json"}, 400
    from dataclasses import asdict

    from generator.test_design import build_test_design
    from web.services.test_design_settings import get_test_design_settings

    params = _test_design_params(get_test_design_settings())
    design = build_test_design(report, params)
    return asdict(design)


@bp.get("/api/test-design/by-screen")
def api_test_design_by_screen() -> dict | tuple[dict, int]:
    """画面別テスト設計。page_id 省略で画面リスト、指定でその画面の条件一覧を返す。"""
    from web.services.screen_test_design import build_screen_detail, build_screen_index

    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 404
    _, report, error = _table_request()
    if error:
        return error, 404
    assert report is not None
    page_id = request.args.get("page_id", "").strip()
    if not page_id:
        return {"domain": domain, "screens": build_screen_index(report)}
    detail = build_screen_detail(report, page_id)
    if detail is None:
        return {"error": f"screen not found: {page_id}"}, 404
    return _with_run_status(domain, report, detail)


def _with_run_status(domain: str, report: dict, detail: dict) -> dict:
    """条件行にテスト実行結果を付ける（P2-5）。

    実行結果が読めなくても設計そのものは表示できるべきなので、
    失敗しても detail をそのまま返す（バッジが出ないだけ）。
    """
    from web.services.condition_run_status import attach_run_status
    from web.services.testcase_table_store import compose, load_run_result

    conditions = detail.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        return detail
    try:
        rows = compose(domain, report).get("rows") or []
        run_result = load_run_result(domain)
    except Exception:
        logging.warning("テスト実行結果を条件へ紐付けられませんでした: %s", domain, exc_info=True)
        return detail
    return dict(detail, conditions=attach_run_status(conditions, rows, run_result))


@bp.get("/api/qa-process/advanced")
def api_qa_process_advanced() -> dict | tuple[dict, int]:
    domain = request.args.get("domain", "")
    report_path, error = _report_json_path(domain)
    if error:
        return {"error": error}, 404
    report = _load_report(report_path)
    if report is None:
        return {"error": "invalid report.json"}, 400
    return _advanced_payload(domain, report)


@bp.post("/api/qa-process/generate-advanced")
def api_qa_process_generate_advanced() -> dict | tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    domain = request.form.get("domain") or body.get("domain", "")
    report_path, error = _report_json_path(domain)
    if error:
        return {"error": error}, 404
    report = _load_report(report_path)
    if report is None:
        return {"error": "invalid report.json"}, 400
    outputs = _generate_advanced_outputs(domain, report)
    return {
        "ok": True,
        "domain": domain,
        "outputs": _output_payload(domain),
        "advanced": _advanced_payload(domain, report),
        "generated": {k: str(v.resolve()) for k, v in outputs.items()},
    }


# backward-compat re-exports
# fmt: off
from web.services.qa.helpers import _load_report as _load_report  # noqa: F401
from web.services.qa.doc_generator import _generate_outputs as _generate_outputs  # noqa: F401
from web.services.qa.advanced_generator import _generate_advanced_outputs as _generate_advanced_outputs  # noqa: F401
# fmt: on
