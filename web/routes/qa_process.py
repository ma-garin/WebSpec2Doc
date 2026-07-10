from __future__ import annotations

# ruff: noqa: E402, I001

import json
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
