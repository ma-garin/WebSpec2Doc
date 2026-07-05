from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from web.config import OUTPUT_DIR
from web.services.openai_qa import has_openai_api_key
from web.summary import _summary_for_domain
from web.validation import _valid_domain

_VIEWPOINT_OVERRIDE: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "viewpoint_override", default=None
)


@contextmanager
def use_viewpoint_snapshot(viewpoints: list[dict[str, Any]]):
    token = _VIEWPOINT_OVERRIDE.set(viewpoints)
    try:
        yield
    finally:
        _VIEWPOINT_OVERRIDE.reset(token)


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
    ("testcases_html", "テストケースHTML", "testcases.html"),
)


def _output_dir() -> Path:
    route_mod = sys.modules.get("web.routes.qa_process")
    value = getattr(route_mod, "OUTPUT_DIR", OUTPUT_DIR)
    return value if isinstance(value, Path) else Path(value)


def _has_openai_api_key() -> bool:
    route_mod = sys.modules.get("web.routes.qa_process")
    checker = getattr(route_mod, "has_openai_api_key", has_openai_api_key)
    return bool(checker())


def _report_json_path(domain: str) -> tuple[Path | None, str]:
    if not _valid_domain(domain):
        return None, "not found"
    domain_dir = _output_dir() / domain
    if not domain_dir.is_dir():
        return None, "not found"
    report_path = domain_dir / "report.json"
    if not report_path.is_file():
        return None, "report.json not found"
    return report_path, ""


def _load_report(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _input_payload(domain: str, report: dict[str, Any]) -> dict[str, Any]:
    domain_dir = _output_dir() / domain
    return {
        "domain": domain,
        "summary": _summary_for_domain(domain) | _qa_summary(report),
        "input_files": {
            "report_json": _existing_path(domain_dir / "report.json"),
            "spec_excel": _existing_path(domain_dir / "spec.xlsx"),
            "report_html": _existing_path(domain_dir / "report.html"),
        },
        "screens": _screen_summaries(report),
        "outputs": _output_payload(domain),
        "ai": {"available": _has_openai_api_key()},
        "ai_artifact": _load_ai_artifact(domain),
        "viewpoints": _load_qa_viewpoints(),
    }


def _existing_path(path: Path) -> str:
    return str(path.resolve()) if path.exists() else ""


def _output_payload(domain: str) -> dict[str, str]:
    out_dir = _output_dir() / domain / "qa_process"
    return {
        key: _existing_path(out_dir / filename)
        for key, _label, filename in QA_STEPS + QA_ADVANCED_OUTPUTS
    }


def _qa_summary(report: dict[str, Any]) -> dict[str, int]:
    screens = _screens(report)
    forms = [form for screen in screens for form in _forms(screen)]
    fields = [field for form in forms for field in _fields(form)]
    return {
        "screens": len(screens),
        "forms": len(forms),
        "fields": len(fields),
        "required": sum(1 for field in fields if field.get("required")),
        "buttons": sum(len(_buttons(screen)) for screen in screens),
        "transitions": sum(len(_transitions_to(screen)) for screen in screens),
    }


def _load_qa_viewpoints(
    domain: str = "",
    report: dict[str, Any] | None = None,
    provider: Any = None,
) -> list[dict[str, Any]]:
    """公開済みDB観点を返し、AutoRun中は固定スナップショットだけを参照する。"""
    override = _VIEWPOINT_OVERRIDE.get()
    if override is not None:
        viewpoints = [_legacy_viewpoint(item) for item in override]
    else:
        from web.services.viewpoint_store import get_viewpoint_store

        snapshot = get_viewpoint_store().select_snapshot(
            {"url": f"https://{domain}" if domain else ""}
        )
        viewpoints = [_legacy_viewpoint(item) for item in snapshot["items"]]

    # 移行互換の環境変数 QA_VIEWPOINTS_CSV はDB初回投入元としてのみ利用する。
    # 生成処理でCSVを再読込しないため、実行中の差し替えは反映されない。
    if provider is None or report is None:
        return viewpoints

    from llm.screen_classifier import classify_screen_by_rules

    screens = _screens(report)[:5]
    fields = [field for screen in screens for form in _forms(screen) for field in _fields(form)]
    field_names = [
        str(field.get("name") or field.get("element_id") or field.get("placeholder") or "")
        for field in fields
    ]
    titles = [str(screen.get("title") or "") for screen in screens if screen.get("title")]
    headings = [str(value) for screen in screens for value in screen.get("headings", []) if value]
    classification = classify_screen_by_rules(
        " / ".join(titles) or domain,
        tuple(headings),
        field_names,
    )
    screen_info = {
        "domain": domain,
        "screens": [
            {
                "page_id": screen.get("page_id", ""),
                "title": screen.get("title", ""),
                "url": screen.get("url", ""),
            }
            for screen in screens
        ],
        "screen_classification": classification,
        "fields": fields,
    }
    generated: list[dict[str, Any]] = []
    for item in provider.generate_viewpoints(screen_info):
        if not isinstance(item, dict):
            continue
        name = str(item.get("viewpoint") or "").strip()
        if not name:
            continue
        generated.append(
            {
                "summary_type": str(item.get("category") or "provider"),
                "name": name,
                "count": 1,
                "source": str(item.get("source") or "rules"),
            }
        )

    seen = {(item["summary_type"], item["name"]) for item in viewpoints}
    for item in generated:
        key = (item["summary_type"], item["name"])
        if key not in seen:
            viewpoints.append(item)
            seen.add(key)
    return viewpoints


def _legacy_viewpoint(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "persistent_key": str(item.get("persistent_key", "")),
        "summary_type": str(item.get("category") or item.get("summary_type") or "一般"),
        "name": str(item.get("name", "")),
        "count": int(item.get("count", 1) or 1),
        "risk_weight": int(item.get("risk_weight", 3) or 3),
        "automation": str(item.get("automation", "manual")),
        "standards": str(item.get("standards", "")),
        "tags": item.get("tags", []),
    }


def _viewpoints_by_type(summary_type: str) -> list[dict[str, Any]]:
    return [vp for vp in _load_qa_viewpoints() if vp.get("summary_type") == summary_type]


def _viewpoint_names(summary_type: str, limit: int = 8) -> list[str]:
    return [str(vp["name"]) for vp in _viewpoints_by_type(summary_type)[:limit]]


def _screen_summaries(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for screen in _screens(report):
        fields = [field for form in _forms(screen) for field in _fields(form)]
        rows.append(
            {
                "page_id": screen.get("page_id", ""),
                "title": screen.get("title", ""),
                "url": screen.get("url", ""),
                "forms": len(_forms(screen)),
                "fields": len(fields),
                "required": sum(1 for field in fields if field.get("required")),
                "buttons": len(_buttons(screen)),
                "transitions_to": _transitions_to(screen),
                "raw_forms": _forms(screen),
            }
        )
    return rows


def _ai_artifact_path(domain: str) -> Path:
    out_dir = _output_dir() / domain / "qa_process"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "ai_artifacts.json"


def _load_ai_artifact(domain: str) -> dict[str, Any] | None:
    path = _output_dir() / domain / "qa_process" / "ai_artifacts.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _screens(report: dict[str, Any]) -> list[dict[str, Any]]:
    screens = report.get("screens", [])
    return (
        [screen for screen in screens if isinstance(screen, dict)]
        if isinstance(screens, list)
        else []
    )


def _forms(screen: dict[str, Any]) -> list[dict[str, Any]]:
    forms = screen.get("forms", [])
    return [form for form in forms if isinstance(form, dict)] if isinstance(forms, list) else []


def _fields(form: dict[str, Any]) -> list[dict[str, Any]]:
    fields = form.get("fields", [])
    return (
        [field for field in fields if isinstance(field, dict)] if isinstance(fields, list) else []
    )


def _buttons(screen: dict[str, Any]) -> list[str]:
    buttons = screen.get("buttons", [])
    return (
        [str(button) for button in buttons if str(button).strip()]
        if isinstance(buttons, list)
        else []
    )


def _transitions_to(screen: dict[str, Any]) -> list[str]:
    transitions = screen.get("transitions", {})
    to_ids = transitions.get("to", []) if isinstance(transitions, dict) else []
    return (
        [str(to_id) for to_id in to_ids if str(to_id).strip()] if isinstance(to_ids, list) else []
    )


def _sid(screen: dict[str, Any]) -> str:
    return str(screen.get("page_id") or "P???")


def _field_trace_id(screen: dict[str, Any], form_idx: int, field_idx: int) -> str:
    return f"{_sid(screen)}-F{form_idx:02d}-I{field_idx:02d}"


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _md(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
