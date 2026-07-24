"""QA アシスタント（LLM チャット）の API。

AutoRun の各段階（テスト目的・観点・設計・ケース）について相談するための
軽量なチャット経路。**LLM は必須ではない**——到達できない場合は 503 と
理由を返し、UI 側で「利用できない」と正直に表示する。

接続先は `src/llm/openai_client.resolve_endpoint()` が環境変数から解決する
（ローカルは Ollama、本番は OpenAI）。
"""

from __future__ import annotations

import json
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path

from flask import Blueprint, request

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from llm.activity_log import record_llm_activity  # noqa: E402
from llm.openai_client import LLMUnavailableError, resolve_endpoint  # noqa: E402

logger = logging.getLogger(__name__)

bp = Blueprint("llm_chat", __name__)

MAX_MESSAGE_CHARS = 4000
MAX_HISTORY_TURNS = 8
TIMEOUT_SEC = 120

SYSTEM_PROMPT = (
    "あなたはWebSpec2Docに組み込まれたベテランQAエンジニアの相談相手です。"
    "日本語で、簡潔かつ具体的に答えてください。\n"
    "守ること:\n"
    "- 観測していない事実を断定しない。推測は推測と明示する。\n"
    "- 「欠陥が無い」ことは証明できない。検証できていない範囲は「未検証」と述べる。\n"
    "- テスト設計の助言はISTQBの技法名（同値分割・境界値分析・デシジョンテーブル・"
    "状態遷移・組合せ）を用いて具体的に述べる。\n"
    "- 最終的な採用判断は人間が行う前提で、選択肢と根拠を示す。"
)


def _chat(endpoint, messages: list[dict[str, str]]) -> str:
    payload = {
        "model": endpoint.model,
        "messages": messages,
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        endpoint.chat_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {endpoint.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:  # nosec B310
        data = json.loads(resp.read().decode("utf-8"))
    try:
        return str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMUnavailableError(f"LLM 応答の形式が不正です: {exc}") from exc


@bp.post("/api/llm/chat")
def api_llm_chat() -> tuple[dict, int] | dict:
    """QA アシスタントへの相談。

    body: {message: str, context?: str, history?: [{role, content}]}
    """
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    context = str(payload.get("context", "")).strip()
    history = payload.get("history") or []

    if not message:
        return {"error": "相談内容を入力してください"}, 400
    if len(message) > MAX_MESSAGE_CHARS:
        return {"error": f"入力が長すぎます（上限 {MAX_MESSAGE_CHARS} 文字）"}, 400

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context:
        messages.append({"role": "system", "content": f"現在ユーザーが見ている段階: {context}"})

    if isinstance(history, list):
        for turn in history[-MAX_HISTORY_TURNS:]:
            if not isinstance(turn, dict):
                continue
            role = str(turn.get("role", ""))
            content = str(turn.get("content", ""))[:MAX_MESSAGE_CHARS]
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": message})

    endpoint = resolve_endpoint()
    prompt_chars = sum(len(m.get("content", "")) for m in messages)

    def _record(outcome: str, detail: str = "") -> None:
        # 生成AIを使う経路は成功・失敗を問わず必ずアクティビティログに残す
        record_llm_activity(
            purpose="qa_chat",
            endpoint_url=endpoint.chat_url,
            model=endpoint.model,
            outcome=outcome,
            detail=detail,
            prompt_chars=prompt_chars,
        )

    if not endpoint.api_key:
        _record("not_configured")
        return {
            "error": "LLM の接続先が設定されていません。",
            "detail": "OPENAI_API_KEY もしくは WEBSPEC2DOC_LLM_BASE_URL を設定してください。",
        }, 503

    try:
        reply = _chat(endpoint, messages)
    except urllib.error.HTTPError as exc:
        logger.info("LLM チャットが失敗しました: %s", exc)
        _record("http_error", str(exc))
        return {"error": f"QAアシスタントの呼び出しに失敗しました（HTTP {exc.code}）"}, 502
    except (LLMUnavailableError, urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.info("LLM チャットに到達できません: %s", exc)
        _record("unavailable", str(exc))
        return {
            "error": "QAアシスタントに接続できませんでした。",
            "detail": "この機能は補助であり、AutoRun の実行自体には影響しません。",
        }, 503

    _record("ok")
    return {"reply": reply, "model": endpoint.model}
