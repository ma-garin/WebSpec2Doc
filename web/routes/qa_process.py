from __future__ import annotations

# ruff: noqa: E402, I001

import json
from typing import Any

from flask import Blueprint, request

from llm.viewpoint_generator import make_provider
from web.config import OUTPUT_DIR
from web.env_store import _read_env
from web.services.openai_qa import OpenAIQAError, generate_openai_qa, has_openai_api_key
from web.services.qa.advanced_generator import _advanced_payload
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
    if not (OUTPUT_DIR / domain).is_dir():
        return {"error": "not found"}, 404
    return {"domain": domain, "outputs": _output_payload(domain)}


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
