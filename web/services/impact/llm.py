"""LLM による影響の判定（任意）。接続先が無い・失敗したときは規則の判定をそのまま使う。

候補は規則の検索で広めに集めた断片だけを渡す（全文は渡さない）。文書は外部データとして
untrusted_block で包み、文書内の指示には従わせない。呼び出しは activity_log に必ず残る。
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from llm.openai_client import (  # noqa: E402
    LLMResponseError, LLMUnavailableError, request_structured_json, resolve_endpoint,
)
from llm.prompt_guard import untrusted_block  # noqa: E402

log = logging.getLogger(__name__)
MAX_CANDIDATES = 24
SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["key", "related", "level", "why", "test"],
        "properties": {
            "key": {"type": "string"},
            "related": {"type": "boolean"},
            "level": {"type": "integer", "minimum": 1, "maximum": 4},
            "why": {"type": "string"},
            "test": {"type": "string"},
        }}}},
}
PROMPT = """あなたはソフトウェアテストの影響分析を行う QA エンジニアです。
仕様の変更と、検索で見つかった仕様書の断片が与えられます。断片ごとに次を判定してください。
- related: その断片の記述が、変更によって動作・表示・データ・テストの期待値が変わりうるなら true
- level: 4=致命（お金・個人情報・認証・データ消失・一括処理・停止に関わる）、3=大（変わった規則そのものに触れる、または同じ部品を使う）、2=中（間接的に関わる）、1=小（記述の見直し程度）
- why: 断片のどの記述からそう判断したかを日本語 1〜2 文。断片に無いことは書かない
- test: その影響を確かめるテストを日本語 1 文（画面・操作・入力値を具体的に）
断片に書かれていない推測で related を true にしないこと。key は渡された値をそのまま返すこと。

変更:
{changes}

{block}
"""


def endpoint_info() -> dict:
    ep = resolve_endpoint()
    return {"available": bool(ep.api_key), "model": ep.model, "local": ep.is_local}


def judge(changes: list[dict], candidates: list[dict]) -> list[dict] | None:
    """候補ごとの判定を返す。使えないときは None（呼び出し側は規則の判定を使う）。"""
    ep = resolve_endpoint()
    if not ep.api_key or not candidates:
        return None
    data = [{"key": c["key"], "doc": c["doc"], "place": c["place"], "text": c["text"][:400]}
            for c in candidates[:MAX_CANDIDATES]]
    text = "\n".join(f"- {c['id']}（{c['location']}）: {c['before'] or '（なし）'} → {c['after'] or '（なし）'}"
                     for c in changes)
    prompt = PROMPT.format(changes=text, block=untrusted_block(data, label="spec_passages", source="利用者が取り込んだ仕様書"))
    try:
        out = request_structured_json(ep.api_key, ep.model, prompt, "impact_judgement", SCHEMA,
                                      base_url=ep.base_url, purpose="impact_analysis")
    except (LLMUnavailableError, LLMResponseError, OSError) as exc:
        log.info("影響度分析の LLM 判定を使えません: %s", exc)
        return None
    keys = {c["key"] for c in data}
    return [i for i in out.get("items", []) if isinstance(i, dict) and i.get("key") in keys]
