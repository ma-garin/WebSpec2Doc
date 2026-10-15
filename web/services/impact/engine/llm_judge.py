"""LLM による候補の判定（DD-004 llm_judge.py。旧 llm.py を移植し policy を見る）。

候補は収集した断片だけを渡す（全文は渡さない）。文書は外部データとして untrusted_block で包み、
文書内の指示には従わせない。使えないときは None（呼び出し側は規則の判定を使う）。
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))

from llm import openai_client  # noqa: E402
from llm.openai_client import LLMResponseError, LLMUnavailableError  # noqa: E402
from llm.prompt_guard import untrusted_block  # noqa: E402

log = logging.getLogger(__name__)
MAX_CANDIDATES = 24
TEXT_LIMIT = 400
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


def _payload(candidates: list[dict]) -> list[dict]:
    return [{"key": str(c["key"]), "doc": c.get("doc", ""), "place": c.get("place", ""),
             "text": (c.get("text") or "")[:TEXT_LIMIT]} for c in candidates[:MAX_CANDIDATES]]


def _change_lines(changes: list[dict]) -> str:
    return "\n".join(f"- {c['code']}（{c['location']}）: {c['before'] or '（なし）'} → {c['after'] or '（なし）'}"
                     for c in changes)


def build_prompt(changes: list[dict], candidates: list[dict]) -> str:
    block = untrusted_block(_payload(candidates), label="spec_passages", source="利用者が取り込んだ仕様書")
    return PROMPT.format(changes=_change_lines(changes), block=block)


def allowed(policy: str) -> bool:
    """policy が送信を許すか。'local' は接続先がローカルの時だけ。"""
    if policy == "external":
        return True
    if policy == "local":
        return openai_client.resolve_endpoint().is_local
    return False


def estimate(candidates: list[dict]) -> dict:
    """送る件数と文字数の見積（確認画面用）。"""
    data = _payload(candidates)
    return {"count": len(data), "chars": len(PROMPT) + sum(len(d["text"]) + len(d["doc"]) + len(d["place"]) for d in data)}


def judge(changes: list[dict], candidates: list[dict], policy: str) -> list[dict] | None:
    """候補ごとの判定 [{key, related, level, why, test}] を返す。使えないときは None。"""
    if not candidates or not allowed(policy):
        return None
    ep = openai_client.resolve_endpoint()
    if not ep.api_key:
        return None
    keys = {str(c["key"]) for c in candidates[:MAX_CANDIDATES]}
    try:
        out = openai_client.request_structured_json(ep.api_key, ep.model, build_prompt(changes, candidates),
                                                    "impact_judgement", SCHEMA, base_url=ep.base_url,
                                                    purpose="impact_analysis")
    except (LLMUnavailableError, LLMResponseError, OSError) as exc:
        log.info("影響度分析の LLM 判定を使えません: %s", exc)
        return None
    items = out.get("items", []) if isinstance(out, dict) else []
    return [i for i in items if isinstance(i, dict) and str(i.get("key")) in keys]
