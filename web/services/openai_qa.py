from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from llm.openai_client import (
    ENV_API_KEY,
    ENV_BASE_URL,
    ENV_MODEL,
    LLMResponseError,
    LLMUnavailableError,
    request_structured_json,
    resolve_endpoint,
)
from web.config import DEFAULT_OPENAI_MODEL
from web.env_store import _read_env

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
QA_ARTIFACT_VERSION = "qa-process-v1"

#: LLM 接続先。web/routes/settings.py が同名の環境変数へ書き込む。
#: settings.py（routes 層）から import すると services → routes の逆流になるため、
#: 値だけをここでも定義する。
ENV_LLM_BASE_URL = "WEBSPEC2DOC_LLM_BASE_URL"


class OpenAIQAError(RuntimeError):
    """Raised when OpenAI QA artifact generation cannot complete."""


#: ローカル宛て（Ollama 等）の既定モデルとタイムアウト（秒）。
LOCAL_DEFAULT_MODEL = "qwen2.5:3b"
LOCAL_TIMEOUT_SEC = 180
REMOTE_TIMEOUT_SEC = 90


def llm_env() -> dict[str, str]:
    """共通クライアントへ渡す設定。接続先系は os.environ と .env（.env 優先）、OpenAI キーは .env のみ。"""
    dotenv = _read_env()
    env = {k: os.environ[k] for k in (ENV_BASE_URL, ENV_MODEL, ENV_API_KEY) if k in os.environ}
    env.update({k: v for k, v in dotenv.items() if k in (ENV_BASE_URL, ENV_MODEL, ENV_API_KEY)})
    env["OPENAI_API_KEY"] = dotenv.get("OPENAI_API_KEY", "")
    return env


def has_openai_api_key() -> bool:
    """AI が使えるか。ローカル宛て（Ollama 等）はキー不要、OpenAI 宛てはキーの有無で判定する。"""
    return bool(resolve_endpoint(env=llm_env()).api_key)


def call_structured(
    system: str,
    user_json: str,
    schema_name: str,
    schema: dict[str, Any],
    max_tokens: int,
) -> tuple[dict[str, Any], str]:
    """共通クライアント経由で構造化 JSON を得る。(応答, 使用モデル名) を返す。"""
    dotenv = _read_env()
    env = llm_env()
    endpoint = resolve_endpoint(env=env)
    if not endpoint.api_key:
        raise OpenAIQAError("OPENAI_API_KEY が設定されていません。設定画面で接続先かキーを設定してください。")
    if endpoint.is_local:
        model = (env.get(ENV_MODEL) or "").strip() or LOCAL_DEFAULT_MODEL
        headers = None
        timeout = LOCAL_TIMEOUT_SEC
    else:
        model = dotenv.get("OPENAI_MODEL", "").strip() or DEFAULT_OPENAI_MODEL
        headers = {
            k: v
            for k, v in _openai_headers(endpoint.api_key, dotenv).items()
            if k.startswith("OpenAI-")
        } or None
        timeout = REMOTE_TIMEOUT_SEC
    try:
        result = request_structured_json(
            endpoint.api_key,
            model,
            user_json,
            schema_name,
            schema,
            timeout_sec=timeout,
            base_url=endpoint.base_url,
            purpose=schema_name,
            system=system,
            max_tokens=max_tokens,
            extra_headers=headers,
        )
    except urllib.error.HTTPError as exc:
        raise OpenAIQAError(f"LLM API error: HTTP {exc.code}") from exc
    except LLMUnavailableError as exc:
        raise OpenAIQAError(f"LLM API request failed: {exc}") from exc
    except LLMResponseError as exc:
        raise OpenAIQAError(f"LLM の応答が不正です: {exc}") from exc
    return result, model


def _is_local_base_url(base_url: str) -> bool:
    """ベース URL がローカルホスト宛かを判定する（SSRF 防止）。"""
    try:
        parsed = urllib.parse.urlparse(base_url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    return (parsed.hostname or "") in {"127.0.0.1", "localhost", "::1"}


def _test_local_llm_connection(base_url: str) -> tuple[bool, str]:
    """ローカルの OpenAI 互換サーバ（Ollama 等）へ疎通確認する。

    API キーは不要。宛先はローカルホストに限る（SSRF 防止）。
    """
    if not _is_local_base_url(base_url):
        return False, "ローカル（127.0.0.1 / localhost / ::1）のエンドポイントのみ疎通確認できます。"
    url = f"{base_url.rstrip('/')}/models"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return False, f"接続に失敗しました（HTTP {exc.code}）。"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, f"接続に失敗しました: {exc}"
    except (ValueError, json.JSONDecodeError):
        # 応答は返ったが OpenAI 互換の JSON ではない。到達はしているので成功扱いにしない。
        return False, "接続できましたが、OpenAI 互換の応答ではありませんでした。"
    models = [item for item in payload.get("data", []) if item.get("id")]
    return True, f"接続に成功しました（モデル {len(models)} 件）。"


def test_openai_connection() -> tuple[bool, str]:
    """設定済みの接続先で疎通確認する。

    トークン課金を避けるため軽量な /models 一覧取得のみ行い、実際の生成は行わない。

    接続先が OpenAI 以外（Ollama 等のローカル OpenAI 互換サーバ）に設定されている
    場合、OPENAI_API_KEY は不要。従来はプロバイダ設定を見ずに常に api.openai.com を
    叩いていたため、Ollama を選んでいても「OPENAI_API_KEY が設定されていません。」が
    返っていた。
    """
    env = _read_env()
    base_url = env.get(ENV_LLM_BASE_URL, "").strip()
    if base_url and "api.openai.com" not in base_url:
        return _test_local_llm_connection(base_url)

    api_key = env.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return False, "OPENAI_API_KEY が設定されていません。"

    request = urllib.request.Request(
        OPENAI_MODELS_URL,
        headers=_openai_headers(api_key, env),
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310
            response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return False, f"接続に失敗しました（HTTP {exc.code}）: {body[:200]}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, f"接続に失敗しました: {exc}"
    return True, "接続に成功しました。"


def generate_openai_qa(
    domain: str, report: dict[str, Any], viewpoints: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    system = (
        "あなたはWebアプリケーションのQAプロセス設計者です。"
        "入力されたreport.json由来の画面構造だけを根拠に、"
        "テスト計画、テスト分析、テスト設計、テストケース、横断レビュー、QAプロセスレポートを"
        "JSONで生成してください。"
        "不明な業務ルール、期待結果、権限、外部連携条件は必ず「質問待ち」として扱ってください。"
        "各テストケースには元画面、元入力項目、元仕様へ戻れるtrace_idを付与してください。"
        "自動化できるもの、手動確認が必要なもの、未実装またはN/Aのものを区別してください。"
        "qa_viewpoint_catalog がある場合は、テスト分析・設計・ケース・横断レビューの観点として必ず反映してください。"
    )
    artifact, model = call_structured(
        system,
        json.dumps(_safe_report_payload(domain, report, viewpoints or []), ensure_ascii=False),
        "webspec2doc_qa_process",
        QA_ARTIFACT_SCHEMA,
        max_tokens=8192,
    )
    missing = [key for key in QA_ARTIFACT_SCHEMA.get("required", []) if key not in artifact]
    if missing:
        raise OpenAIQAError(f"AI の応答に必須項目がありません: {', '.join(missing)}")
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


def _safe_report_payload(
    domain: str, report: dict[str, Any], viewpoints: list[dict[str, Any]]
) -> dict[str, Any]:
    screens = _safe_screens(report)
    return {
        "domain": domain,
        "meta": {
            "target_url": (
                str(report.get("meta", {}).get("target_url", ""))[:500]
                if isinstance(report.get("meta"), dict)
                else ""
            ),
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
                    for item in _list(
                        screen.get("transitions", {}).get("to")
                        if isinstance(screen.get("transitions"), dict)
                        else []
                    )
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
                    "constraints": [
                        _short(item, 160) for item in _list(field.get("constraints"))[:20]
                    ],
                    "test_conditions": [
                        _short(item, 160) for item in _list(field.get("test_conditions"))[:20]
                    ],
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
    for item in (
        response_data.get("output", []) if isinstance(response_data.get("output"), list) else []
    ):
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
            "required": [
                "scope",
                "levels",
                "risks",
                "entry_criteria",
                "exit_criteria",
                "questions",
            ],
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
                        "required": [
                            "viewpoint_id",
                            "target",
                            "technique",
                            "design_note",
                            "trace_id",
                        ],
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
