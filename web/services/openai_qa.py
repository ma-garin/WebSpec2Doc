from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from web.config import DEFAULT_OPENAI_MODEL
from web.env_store import _read_env

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
QA_ARTIFACT_VERSION = "qa-process-v1"


class OpenAIQAError(RuntimeError):
    """Raised when OpenAI QA artifact generation cannot complete."""


def has_openai_api_key() -> bool:
    return bool(_read_env().get("OPENAI_API_KEY", "").strip())


def generate_openai_qa(domain: str, report: dict[str, Any], viewpoints: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    env = _read_env()
    api_key = env.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise OpenAIQAError("OPENAI_API_KEY が設定されていません。")

    model = env.get("OPENAI_MODEL", "").strip() or DEFAULT_OPENAI_MODEL
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": (
                    "あなたはWebアプリケーションのQAプロセス設計者です。"
                    "入力されたreport.json由来の画面構造だけを根拠に、"
                    "テスト計画、テスト分析、テスト設計、テストケース、横断レビュー、QAプロセスレポートを"
                    "JSONで生成してください。"
                    "不明な業務ルール、期待結果、権限、外部連携条件は必ず「質問待ち」として扱ってください。"
                    "各テストケースには元画面、元入力項目、元仕様へ戻れるtrace_idを付与してください。"
                    "自動化できるもの、手動確認が必要なもの、未実装またはN/Aのものを区別してください。"
                    "qa_viewpoint_catalog がある場合は、テスト分析・設計・ケース・横断レビューの観点として必ず反映してください。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(_safe_report_payload(domain, report, viewpoints or []), ensure_ascii=False),
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "webspec2doc_qa_process",
                "description": "WebSpec2Doc QA process artifacts with traceability and review notes.",
                "strict": True,
                "schema": QA_ARTIFACT_SCHEMA,
            }
        },
    }

    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=_openai_headers(api_key, env),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise OpenAIQAError(f"OpenAI API error: HTTP {exc.code} {body[:300]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OpenAIQAError(f"OpenAI API request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise OpenAIQAError("OpenAI API response is not valid JSON.") from exc

    text = _extract_output_text(response_data)
    if not text:
        raise OpenAIQAError("OpenAI API response did not include output text.")
    try:
        artifact = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OpenAIQAError("OpenAI QA artifact is not valid JSON.") from exc
    if not isinstance(artifact, dict):
        raise OpenAIQAError("OpenAI QA artifact must be an object.")
    artifact["mode_version"] = artifact.get("mode_version") or QA_ARTIFACT_VERSION
    artifact["model"] = model
    return artifact


def _openai_headers(api_key: str, env: dict[str, str]) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    org_id = env.get("OPENAI_ORG_ID", "").strip()
    project_id = env.get("OPENAI_PROJECT_ID", "").strip()
    if org_id:
        headers["OpenAI-Organization"] = org_id
    if project_id:
        headers["OpenAI-Project"] = project_id
    return headers


def _safe_report_payload(domain: str, report: dict[str, Any], viewpoints: list[dict[str, Any]]) -> dict[str, Any]:
    screens = _safe_screens(report)
    return {
        "domain": domain,
        "meta": {
            "target_url": str(report.get("meta", {}).get("target_url", ""))[:500]
            if isinstance(report.get("meta"), dict)
            else "",
            "page_count": len(screens),
        },
        "source_files": ["report.json", "spec.xlsx", "report.html"],
        "qa_viewpoint_catalog": _safe_viewpoints(viewpoints),
        "privacy_policy": {
            "sent": "画面構造、URL、タイトル、フォーム定義、入力項目定義、操作要素、遷移情報のみ",
            "not_sent": "認証ファイル、Cookie、パスワード、APIキー、実入力値、個人情報らしき値",
        },
        "screens": screens,
        "caps": {
            "max_screens_sent": 80,
            "max_fields_per_screen_sent": 60,
            "note": "上限を超えた画面または入力項目はコスト抑制のため送信対象から除外されます。",
        },
    }


def _safe_viewpoints(viewpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    safe: list[dict[str, Any]] = []
    for item in viewpoints[:80]:
        if not isinstance(item, dict):
            continue
        safe.append(
            {
                "summary_type": _short(item.get("summary_type"), 80),
                "name": _short(item.get("name"), 160),
                "count": int(item.get("count") or 0),
            }
        )
    return safe


def _safe_screens(report: dict[str, Any]) -> list[dict[str, Any]]:
    raw_screens = report.get("screens", [])
    if not isinstance(raw_screens, list):
        return []
    screens: list[dict[str, Any]] = []
    for screen in raw_screens[:80]:
        if not isinstance(screen, dict):
            continue
        screens.append(
            {
                "page_id": _short(screen.get("page_id"), 80),
                "url": _short(screen.get("url"), 500),
                "title": _short(screen.get("title"), 200),
                "headings": [_short(item, 200) for item in _list(screen.get("headings"))[:20]],
                "buttons": [_short(item, 160) for item in _list(screen.get("buttons"))[:40]],
                "forms": _safe_forms(screen),
                "transitions_to": [
                    _short(item, 80)
                    for item in _list(screen.get("transitions", {}).get("to") if isinstance(screen.get("transitions"), dict) else [])
                ],
            }
        )
    return screens


def _safe_forms(screen: dict[str, Any]) -> list[dict[str, Any]]:
    forms = screen.get("forms", [])
    if not isinstance(forms, list):
        return []
    safe_forms: list[dict[str, Any]] = []
    for form_index, form in enumerate(forms[:20], 1):
        if not isinstance(form, dict):
            continue
        fields = []
        for field_index, field in enumerate(_list(form.get("fields"))[:60], 1):
            if not isinstance(field, dict):
                continue
            trace_id = f"{screen.get('page_id') or 'P???'}-F{form_index:02d}-I{field_index:02d}"
            fields.append(
                {
                    "trace_id": trace_id,
                    "name": _short(field.get("name"), 160),
                    "element_id": _short(field.get("element_id"), 160),
                    "placeholder": _short(field.get("placeholder"), 160),
                    "field_type": _short(field.get("field_type") or field.get("type"), 80),
                    "required": bool(field.get("required")),
                    "constraints": [_short(item, 160) for item in _list(field.get("constraints"))[:20]],
                    "test_conditions": [_short(item, 160) for item in _list(field.get("test_conditions"))[:20]],
                }
            )
        safe_forms.append(
            {
                "trace_id": f"{screen.get('page_id') or 'P???'}-F{form_index:02d}",
                "action": _short(form.get("action"), 300),
                "method": _short(form.get("method"), 20),
                "fields": fields,
            }
        )
    return safe_forms


def _extract_output_text(response_data: dict[str, Any]) -> str:
    direct = response_data.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    chunks: list[str] = []
    for item in response_data.get("output", []) if isinstance(response_data.get("output"), list) else []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
            if not isinstance(content, dict):
                continue
            text = content.get("text") or content.get("output_text")
            if isinstance(text, str):
                chunks.append(text)
    return "".join(chunks).strip()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _short(value: Any, limit: int) -> str:
    text = "" if value is None else str(value)
    return text[:limit]


def _array_of_strings(description: str) -> dict[str, Any]:
    return {
        "type": "array",
        "description": description,
        "items": {"type": "string"},
    }


QA_ARTIFACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "mode_version",
        "approach",
        "test_plan",
        "test_analysis",
        "test_design",
        "test_cases",
        "cross_review",
        "qa_process_report",
    ],
    "properties": {
        "mode_version": {"type": "string"},
        "approach": {
            "type": "object",
            "additionalProperties": False,
            "required": ["generation_policy", "reference_process", "open_questions_policy"],
            "properties": {
                "generation_policy": {"type": "string"},
                "reference_process": {"type": "string"},
                "open_questions_policy": {"type": "string"},
            },
        },
        "test_plan": {
            "type": "object",
            "additionalProperties": False,
            "required": ["scope", "levels", "risks", "entry_criteria", "exit_criteria", "questions"],
            "properties": {
                "scope": _array_of_strings("Testing scope."),
                "levels": _array_of_strings("Test levels."),
                "risks": _array_of_strings("Key risks."),
                "entry_criteria": _array_of_strings("Entry criteria."),
                "exit_criteria": _array_of_strings("Exit criteria."),
                "questions": _array_of_strings("Open questions."),
            },
        },
        "test_analysis": {
            "type": "object",
            "additionalProperties": False,
            "required": ["source_inventory", "risk_items", "questions"],
            "properties": {
                "source_inventory": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["screen_id", "title", "observations", "risk", "trace_id"],
                        "properties": {
                            "screen_id": {"type": "string"},
                            "title": {"type": "string"},
                            "observations": _array_of_strings("Observed structures."),
                            "risk": {"type": "string"},
                            "trace_id": {"type": "string"},
                        },
                    },
                },
                "risk_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["risk_id", "description", "impact", "trace_id"],
                        "properties": {
                            "risk_id": {"type": "string"},
                            "description": {"type": "string"},
                            "impact": {"type": "string"},
                            "trace_id": {"type": "string"},
                        },
                    },
                },
                "questions": _array_of_strings("Open questions."),
            },
        },
        "test_design": {
            "type": "object",
            "additionalProperties": False,
            "required": ["viewpoints", "coverage_matrix", "questions"],
            "properties": {
                "viewpoints": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["viewpoint_id", "target", "technique", "design_note", "trace_id"],
                        "properties": {
                            "viewpoint_id": {"type": "string"},
                            "target": {"type": "string"},
                            "technique": {"type": "string"},
                            "design_note": {"type": "string"},
                            "trace_id": {"type": "string"},
                        },
                    },
                },
                "coverage_matrix": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["trace_id", "covered_by", "coverage_note"],
                        "properties": {
                            "trace_id": {"type": "string"},
                            "covered_by": {"type": "string"},
                            "coverage_note": {"type": "string"},
                        },
                    },
                },
                "questions": _array_of_strings("Open questions."),
            },
        },
        "test_cases": {
            "type": "object",
            "additionalProperties": False,
            "required": ["expected_case_yield", "case_expansion_ledger", "cases", "questions"],
            "properties": {
                "expected_case_yield": {"type": "string"},
                "case_expansion_ledger": _array_of_strings("Expansion notes."),
                "cases": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "case_id",
                            "title",
                            "precondition",
                            "steps",
                            "expected",
                            "execution_type",
                            "automation_candidate",
                            "status",
                            "trace_id",
                        ],
                        "properties": {
                            "case_id": {"type": "string"},
                            "title": {"type": "string"},
                            "precondition": {"type": "string"},
                            "steps": _array_of_strings("Test steps."),
                            "expected": {"type": "string"},
                            "execution_type": {
                                "type": "string",
                                "enum": ["自動化候補", "手動確認", "未実装", "N/A"],
                            },
                            "automation_candidate": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": ["生成済み", "質問待ち", "未実装", "N/A"],
                            },
                            "trace_id": {"type": "string"},
                        },
                    },
                },
                "questions": _array_of_strings("Open questions."),
            },
        },
        "cross_review": {
            "type": "object",
            "additionalProperties": False,
            "required": ["findings", "gaps", "recommendations", "questions"],
            "properties": {
                "findings": _array_of_strings("Review findings."),
                "gaps": _array_of_strings("Coverage gaps."),
                "recommendations": _array_of_strings("Recommendations."),
                "questions": _array_of_strings("Open questions."),
            },
        },
        "qa_process_report": {
            "type": "object",
            "additionalProperties": False,
            "required": ["summary", "next_actions"],
            "properties": {
                "summary": {"type": "string"},
                "next_actions": _array_of_strings("Next actions."),
            },
        },
    },
}
