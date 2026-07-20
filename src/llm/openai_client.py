"""LLM への HTTP 呼び出しを一元化するクライアントモジュール。

各生成モジュールが urllib を直叩きするのを避け、Structured Outputs
（JSON Schema strict）でのリクエスト構築・レスポンス解釈をここに集約する。

**OpenAI と Ollama の両対応。** Ollama は OpenAI 互換エンドポイントを
提供するため、ベース URL を差し替えるだけで同じ経路が使える。

    # ローカル（Ollama）
    export WEBSPEC2DOC_LLM_BASE_URL=http://127.0.0.1:11434/v1
    export WEBSPEC2DOC_LLM_MODEL=qwen2.5:3b

    # 本番（OpenAI）
    export OPENAI_API_KEY=sk-...
    export WEBSPEC2DOC_LLM_MODEL=gpt-4o-mini

Structured Outputs（`json_schema` strict）に対応しないサーバもあるため、
拒否された場合は `json_object` ＋プロンプト内スキーマ提示へ自動で退避する。
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TIMEOUT_SEC = 30
# Ollama は認証しないが、OpenAI 互換クライアントは Authorization ヘッダを送るため置き値を使う
PLACEHOLDER_API_KEY = "local"

ENV_BASE_URL = "WEBSPEC2DOC_LLM_BASE_URL"
ENV_MODEL = "WEBSPEC2DOC_LLM_MODEL"
ENV_API_KEY = "WEBSPEC2DOC_LLM_API_KEY"

# 後方互換: 旧コードが参照していた定数
OPENAI_CHAT_URL = f"{DEFAULT_BASE_URL}/chat/completions"


class LLMResponseError(RuntimeError):
    """LLM 応答が不正（スキーマ違反・JSON 解釈不能など）であることを表す例外。"""


class LLMUnavailableError(RuntimeError):
    """LLM エンドポイントへ到達できないことを表す例外。

    LLM は必須ではない。呼び出し側はこれを捕捉してルールベースの
    フォールバックへ切り替えること。
    """


@dataclass(frozen=True)
class LLMEndpoint:
    """接続先の解決結果。"""

    base_url: str
    api_key: str
    model: str

    @property
    def chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    @property
    def is_local(self) -> bool:
        return "127.0.0.1" in self.base_url or "localhost" in self.base_url


def resolve_endpoint(model: str | None = None) -> LLMEndpoint:
    """環境変数から接続先を解決する。

    ベース URL がローカル（Ollama 等）の場合、API キーは不要なので置き値を使う。
    """
    base_url = os.environ.get(ENV_BASE_URL, "").strip() or DEFAULT_BASE_URL
    resolved_model = (model or os.environ.get(ENV_MODEL, "").strip() or "gpt-4o-mini")
    api_key = (
        os.environ.get(ENV_API_KEY, "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )
    is_local = "127.0.0.1" in base_url or "localhost" in base_url
    if not api_key and is_local:
        api_key = PLACEHOLDER_API_KEY
    return LLMEndpoint(base_url=base_url, api_key=api_key, model=resolved_model)


def _post_json(url: str, api_key: str, payload: dict[str, Any], timeout_sec: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_sec) as resp:  # nosec B310
        return json.loads(resp.read().decode("utf-8"))


def _extract_json(data: dict[str, Any]) -> dict[str, Any]:
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMResponseError(f"LLM 応答の形式が不正です: {exc}") from exc
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMResponseError(f"LLM 応答を JSON として解釈できません: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LLMResponseError("LLM 応答のトップレベルが JSON オブジェクトではありません。")
    return parsed


def request_structured_json(
    api_key: str,
    model: str,
    prompt: str,
    schema_name: str,
    json_schema: dict[str, Any],
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Structured Outputs で LLM を呼び出し、応答 JSON を返す。

    `json_schema` 非対応のサーバでは `json_object` ＋プロンプト内スキーマへ退避する。
    接続できない場合は ``LLMUnavailableError`` を送出するので、呼び出し側は
    ルールベースのフォールバックへ切り替えること。
    """
    endpoint = LLMEndpoint(
        base_url=(base_url or os.environ.get(ENV_BASE_URL, "").strip() or DEFAULT_BASE_URL),
        api_key=api_key,
        model=model,
    )

    strict_payload: dict[str, Any] = {
        "model": endpoint.model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": json_schema},
        },
        "temperature": 0,
    }

    try:
        return _extract_json(_post_json(endpoint.chat_url, api_key, strict_payload, timeout_sec))
    except urllib.error.HTTPError as exc:
        if exc.code not in (400, 404, 422, 501):
            raise LLMUnavailableError(f"LLM 呼び出しに失敗しました: {exc}") from exc
        logger.info("json_schema 非対応のため json_object へ退避します（HTTP %s）", exc.code)
    except urllib.error.URLError as exc:
        raise LLMUnavailableError(f"LLM エンドポイントへ到達できません: {exc.reason}") from exc
    except (TimeoutError, OSError) as exc:
        raise LLMUnavailableError(f"LLM エンドポイントへ到達できません: {exc}") from exc

    # 退避経路: スキーマをプロンプトに埋め込み、JSON オブジェクトとしてだけ縛る
    fallback_prompt = (
        f"{prompt}\n\n"
        "出力は次の JSON Schema に厳密に従う JSON オブジェクトのみとし、"
        "前後に説明文やコードフェンスを付けないこと:\n"
        f"{json.dumps(json_schema, ensure_ascii=False)}"
    )
    fallback_payload: dict[str, Any] = {
        "model": endpoint.model,
        "messages": [{"role": "user", "content": fallback_prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    try:
        return _extract_json(_post_json(endpoint.chat_url, api_key, fallback_payload, timeout_sec))
    except urllib.error.URLError as exc:
        raise LLMUnavailableError(f"LLM エンドポイントへ到達できません: {exc.reason}") from exc
    except (TimeoutError, OSError) as exc:
        raise LLMUnavailableError(f"LLM エンドポイントへ到達できません: {exc}") from exc
