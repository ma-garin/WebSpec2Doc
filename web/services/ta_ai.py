"""テスト活動支援（TA）の AI 生成と、その一部の永続化。

- LLM への HTTP 呼び出しは新しく作らない。既存の `src/llm/openai_client.py`
  （OpenAI / Ollama 両対応・Structured Outputs・アクティビティログ記録済み）をそのまま使う。
- 生成結果のうち再利用する種別（テスト条件・テストケース）だけを
  `output/<domain>/ta_ai/<kind>.json` に保存し、CSV エクスポートで読み返せるようにする。
  観点・スクリプト・コード修正案・RCA下書きは都度生成の使い捨て（保存しない）。
- なぜなぜ分析（RCA）の確定記録は AI 生成と別経路（`save_rca`）で、
  ユーザーが確認した whys だけを `output/<domain>/rca/rca.json` に保存する。

呼び出し側（web/routes/test_activity.py）は本モジュールの例外だけを見ればよい:
  - TaAiError            … 入力不正（400 相当）
  - TaAiUnavailableError … LLM 未設定・到達不可（503 相当）
  - TaAiGenerationError  … LLM 応答が不正・生成失敗（502 相当）
`llm.openai_client` の例外型を呼び出し側へ漏らさない。
"""

from __future__ import annotations

import json
import sys
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from llm.openai_client import (  # noqa: E402
    LLMResponseError,
    LLMUnavailableError,
    request_structured_json,
    resolve_endpoint,
)
from llm.prompt_guard import QA_PRINCIPLES, untrusted_block  # noqa: E402

GENERATE_KINDS: tuple[str, ...] = (
    "viewpoints",
    "conditions",
    "cases",
    "scripts",
    "codefix",
    "rca",
)
# 生成結果を保存し、CSV エクスポート（kind=cases/conditions）で読み返す種別。
# 他の種別（観点・スクリプト・コード修正案・RCA下書き）は都度生成の使い捨て。
_PERSISTED_KINDS: frozenset[str] = frozenset({"conditions", "cases"})

_MAX_ITEMS = 20
_MAX_WHYS = 10
_MAX_WHY_LENGTH = 500
_GENERATION_TIMEOUT_SEC = 90

_KIND_LABELS: dict[str, str] = {
    "viewpoints": "テスト観点",
    "conditions": "テスト条件",
    "cases": "テストケース",
    "scripts": "テストスクリプト下書き",
    "codefix": "コード修正案",
    "rca": "なぜなぜ分析（RCA）下書き",
}


class TaAiError(RuntimeError):
    """利用者へそのまま提示してよい入力エラー（呼び出し側で 400 に写像する）。"""


class TaAiUnavailableError(RuntimeError):
    """LLM が未設定・到達不可（呼び出し側で 503 に写像する）。"""


class TaAiGenerationError(RuntimeError):
    """LLM 応答が不正・生成に失敗（呼び出し側で 502 に写像する）。"""


# =========================================================================
# パス（domain は必ず検証してからパス要素にする）
# =========================================================================
def _safe_domain(domain: str) -> str:
    value = str(domain or "").strip()
    if not value:
        raise TaAiError("domain は必須です")
    if value in {".", ".."} or ".." in value or "/" in value or "\\" in value or "\x00" in value:
        raise TaAiError(f"domain の形式が不正です: {domain}")
    return value


def _domain_dir(out_dir: Path, domain: str) -> Path:
    return Path(out_dir) / _safe_domain(domain)


def _generated_path(out_dir: Path, domain: str, kind: str) -> Path:
    return _domain_dir(out_dir, domain) / "ta_ai" / f"{kind}.json"


def _rca_path(out_dir: Path, domain: str) -> Path:
    return _domain_dir(out_dir, domain) / "rca" / "rca.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# =========================================================================
# 観測データの要約（実測に基づかない生成をさせないための最小コンテキスト）
# =========================================================================
def _observation_summary(out_dir: Path, domain: str) -> dict[str, Any]:
    report = _read_json(_domain_dir(out_dir, domain) / "report.json")
    pages = (
        [p for p in (report or {}).get("pages", []) if isinstance(p, dict)]
        if isinstance(report, dict)
        else []
    )
    forms = [f for p in pages for f in (p.get("forms") or []) if isinstance(f, dict)]
    fields = sum(len(f.get("fields") or []) for f in forms)
    titles = [str(p.get("title") or "").strip() for p in pages[:20]]
    return {
        "domain": domain,
        "page_count": len(pages),
        "form_count": len(forms),
        "field_count": fields,
        "screen_titles": [t for t in titles if t],
    }


def _open_defects_summary(out_dir: Path, domain: str) -> list[dict[str, Any]]:
    from web.services import defect_store

    defects = defect_store.list_defects(out_dir, domain)
    return [
        {
            "id": d.get("id", ""),
            "summary": str(d.get("summary", ""))[:300],
            "severity": d.get("severity", ""),
            "state": d.get("state", ""),
            "case_id": d.get("case_id", ""),
        }
        for d in defects
        if d.get("state") != "closed"
    ][:30]


# =========================================================================
# 生成スキーマ（Structured Outputs strict 用: 全プロパティを required に含める）
# =========================================================================
_STR: dict[str, Any] = {"type": "string"}


def _array_of_strings(description: str) -> dict[str, Any]:
    return {"type": "array", "description": description, "items": {"type": "string"}}


def _obj(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }


def _items_schema(description: str, item_schema: dict[str, Any]) -> dict[str, Any]:
    return _obj(
        ["items"],
        {
            "items": {
                "type": "array",
                "description": description,
                "maxItems": _MAX_ITEMS,
                "items": item_schema,
            }
        },
    )


_SCHEMAS: dict[str, dict[str, Any]] = {
    "viewpoints": _items_schema(
        "テスト観点の提案。",
        _obj(
            ["name", "category", "technique", "note"],
            {"name": _STR, "category": _STR, "technique": _STR, "note": _STR},
        ),
    ),
    "conditions": _items_schema(
        "テスト条件の提案。",
        _obj(
            ["condition_id", "target", "condition", "technique", "note"],
            {
                "condition_id": _STR,
                "target": _STR,
                "condition": _STR,
                "technique": _STR,
                "note": _STR,
            },
        ),
    ),
    "cases": _items_schema(
        "テストケースの提案。",
        _obj(
            ["case_id", "title", "precondition", "steps", "expected"],
            {
                "case_id": _STR,
                "title": _STR,
                "precondition": _STR,
                "steps": _array_of_strings("手順（実施順）。"),
                "expected": _STR,
            },
        ),
    ),
    "scripts": _items_schema(
        "テストスクリプト下書き（自動化手順案）。",
        _obj(
            ["case_id", "title", "script"],
            {"case_id": _STR, "title": _STR, "script": _STR},
        ),
    ),
    "codefix": _items_schema(
        "不具合に対するコード修正案。",
        _obj(
            ["defect_id", "summary", "root_cause", "fix_suggestion"],
            {"defect_id": _STR, "summary": _STR, "root_cause": _STR, "fix_suggestion": _STR},
        ),
    ),
    "rca": _items_schema(
        "根本原因分析（なぜなぜ）の下書き。",
        _obj(
            ["defect_id", "summary", "whys", "root_cause"],
            {
                "defect_id": _STR,
                "summary": _STR,
                "whys": _array_of_strings("なぜを繰り返した思考過程（3〜5件目安）。"),
                "root_cause": _STR,
            },
        ),
    ),
}


# =========================================================================
# 生成
# =========================================================================
def generate(out_dir: Path, domain: str, kind: str) -> list[dict[str, Any]]:
    """kind に応じた AI 生成物を返す。永続化対象の kind は保存もする。

    Raises:
        TaAiError: domain / kind が不正（呼び出し側で 400）
        TaAiUnavailableError: LLM 未設定・到達不可（呼び出し側で 503）
        TaAiGenerationError: LLM 応答が不正・生成に失敗（呼び出し側で 502）
    """
    domain = _safe_domain(domain)
    if kind not in GENERATE_KINDS:
        raise TaAiError(f"kind が不正です（許可: {', '.join(GENERATE_KINDS)}）")

    endpoint = resolve_endpoint()
    if not endpoint.api_key:
        raise TaAiUnavailableError("LLM の接続先が設定されていません。")

    context: dict[str, Any] = {"observation": _observation_summary(out_dir, domain)}
    if kind in ("codefix", "rca"):
        context["open_defects"] = _open_defects_summary(out_dir, domain)

    prompt = (
        QA_PRINCIPLES
        + f"\n対象ドメイン {domain} について、種別「{_KIND_LABELS[kind]}」の"
        f"テスト活動成果物を最大 {_MAX_ITEMS} 件、items 配列として提案してください。\n"
        + untrusted_block(context, label="ta_context", source="対象サイトの実測データ")
    )

    try:
        result = request_structured_json(
            api_key=endpoint.api_key,
            model=endpoint.model,
            prompt=prompt,
            schema_name=f"ta_ai_{kind}",
            json_schema=_SCHEMAS[kind],
            timeout_sec=_GENERATION_TIMEOUT_SEC,
            base_url=endpoint.base_url,
            purpose=f"ta_ai_{kind}",
        )
    except LLMUnavailableError as exc:
        raise TaAiUnavailableError(str(exc)) from exc
    except LLMResponseError as exc:
        raise TaAiGenerationError(str(exc)) from exc
    except urllib.error.HTTPError as exc:
        raise TaAiGenerationError(f"LLM呼び出しに失敗しました（HTTP {exc.code}）") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TaAiUnavailableError(str(exc)) from exc

    raw_items = result.get("items") if isinstance(result, dict) else None
    items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []

    if kind in _PERSISTED_KINDS:
        _write_json(_generated_path(out_dir, domain, kind), {"updated_at": _now(), "items": items})

    return items


def read_generated(out_dir: Path, domain: str, kind: str) -> list[dict[str, Any]]:
    """永続化済みの生成結果を返す（未生成・対象外の kind は空リスト）。"""
    domain = _safe_domain(domain)
    if kind not in _PERSISTED_KINDS:
        return []
    data = _read_json(_generated_path(out_dir, domain, kind))
    items = data.get("items") if isinstance(data, dict) else None
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


# =========================================================================
# RCA（なぜなぜ分析）の確定記録
# =========================================================================
def save_rca(out_dir: Path, domain: str, defect_id: str, whys: list[Any]) -> dict[str, Any]:
    """ユーザーが確認した whys を、対象不具合に紐づけて保存する。

    defect_id は既存の不具合を指している必要がある（存在しないIDへの記録を防ぐ）。
    """
    domain = _safe_domain(domain)
    defect_id = str(defect_id or "").strip()
    if not defect_id or ".." in defect_id or "/" in defect_id or "\\" in defect_id:
        raise TaAiError("defect_id が不正です")
    if not isinstance(whys, list) or not whys:
        raise TaAiError("whys は 1 件以上の配列で指定してください")

    from web.services import defect_store

    known_ids = {d.get("id", "") for d in defect_store.list_defects(out_dir, domain)}
    if defect_id not in known_ids:
        raise TaAiError(f"不具合が見つかりません: {defect_id}")

    cleaned = [str(w).strip()[:_MAX_WHY_LENGTH] for w in whys[:_MAX_WHYS] if str(w).strip()]
    if not cleaned:
        raise TaAiError("whys は 1 件以上の配列で指定してください")

    path = _rca_path(out_dir, domain)
    raw = _read_json(path)
    records: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    now = _now()
    previous = records.get(defect_id)
    created_at = previous.get("created_at", now) if isinstance(previous, dict) else now
    record = {
        "defect_id": defect_id,
        "whys": cleaned,
        "created_at": created_at,
        "updated_at": now,
    }
    records = {**records, defect_id: record}
    _write_json(path, records)
    return record
