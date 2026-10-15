"""LLM 送信の唯一の出口。送信前検査・振り分け・記録。

方針（RD-008 v0.2・基本設計書 8 章）:
- OpenAI に送るのはスキーマと仕様だけ。データ値を含む用途は Ollama（ローカル）に固定する。
- 送信本文は保存しない。sha256 と検査結果（件数・規則名・資料名と行）だけを llm_log に残す。
- 検査で 1 件でも検出したら送らず、sent=false の記録を付けて利用者向けの例外を投げる。
実際の HTTP 呼び出しは既存の LLM 層（openai_qa）の接続先・認証・応答解析を使う。
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from web.config import DEFAULT_OPENAI_MODEL
from web.env_store import _read_env
from web.services import openai_qa
from web.services.backendtest import redact

try:  # store.py は別単位。未配置でも同じ契約（ValueError 派生）で動かす
    from web.services.backendtest.store import StoreError
except ImportError:  # pragma: no cover - store.py 配置後は通らない

    class StoreError(ValueError):  # type: ignore[no-redef]
        """利用者に見せてよい失敗（理由。次の行動。）。"""


PROVIDER_OPENAI = "openai"
PROVIDER_OLLAMA = "ollama"
PAYLOAD_KINDS = ("schema", "spec", "data")
#: OpenAI に渡してよい区分。これ以外に中身があれば送らない。
OPENAI_KINDS = frozenset({"schema", "spec"})
#: データ値を扱う用途。payload の data が空でも Ollama に固定する。
DATA_PURPOSES = frozenset({"test_data", "data_values", "golden", "expected_values"})
OLLAMA_DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
OLLAMA_DEFAULT_MODEL = "qwen2.5:3b"
MAX_LOCATIONS = 50
_TIMEOUT_SEC = 120
_DATE_OR_NUMBER = re.compile(
    r"^[+\-]?\d+(?:[.,]\d+)*$|^\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?$"
)

Transport = Callable[[str, str, str], str]


class GateBlocked(StoreError):
    """送信前検査で止めた。record に sent=false の記録を持つ。"""

    def __init__(self, message: str, record: dict) -> None:
        super().__init__(message)
        self.record = record


class LlmCallFailed(StoreError):
    """検査は通ったが LLM の呼び出しに失敗した。record を持つ。"""

    def __init__(self, message: str, record: dict) -> None:
        super().__init__(message)
        self.record = record


# ---------------------------------------------------------------- 検査


def is_data_value(value: str) -> bool:
    """列値を照合対象にするか（8 文字以上、または数値・日付以外。1 文字は除く）。"""
    text = str(value).strip()
    if len(text) >= 8:
        return True
    return len(text) >= 2 and not _DATE_OR_NUMBER.match(text)


def column_values(text: str, has_header: bool = True) -> list[str]:
    """CSV/TSV らしき本文から列値を取り出す（見出し行は列名＝スキーマなので除く）。"""
    lines = [line for line in (text or "").splitlines() if line.strip()]
    if has_header:
        lines = lines[1:]
    delimiter = "\t" if any("\t" in line for line in lines[:5]) else ","
    values: list[str] = []
    for line in lines:
        values.extend(cell.strip().strip('"') for cell in line.split(delimiter))
    return sorted({v for v in values if is_data_value(v)})


def _data_value_pattern(value: str) -> re.Pattern[str]:
    """英数字で始まる・終わる値は語の途中に一致させない。"""
    left = r"(?<![A-Za-z0-9_])" if re.match(r"\w", value[0]) else ""
    right = r"(?![A-Za-z0-9_])" if re.match(r"\w", value[-1]) else ""
    return re.compile(left + re.escape(value) + right)


def _data_hits(body: str, data_values: Iterable[str]) -> list[dict]:
    hits = []
    for value in {str(v).strip() for v in data_values if is_data_value(v)}:
        for match in _data_value_pattern(value).finditer(body):
            hits.append({"start": match.start(), "rule": "data_value"})
    return hits


def inspect(
    body: str, secrets: Iterable[str], data_values: Iterable[str], source: str = "本文"
) -> dict:
    """送信本文を検査し、件数・規則名・検出箇所だけを返す（値と本文は返さない）。

    (1) redact の秘密情報規則 (2) 入力された秘密の値の部分一致 → secret_hits。
    (3) 取り込んだ列値の出現と、個人情報らしき値（メール・電話等）→ data_hits。
    """
    body = body or ""
    scanned = redact.scan(body)
    secret = [h for h in scanned if h["kind"] == redact.KIND_SECRET]
    secret += [
        {"start": h["start"], "rule": "secret_value"}
        for h in redact.scan(body, extra_values=secrets)
        if h["kind"] == redact.KIND_CUSTOM
    ]
    data = [h for h in scanned if h["kind"] == redact.KIND_PERSONAL]
    data += _data_hits(body, data_values)
    rules, locations = [], []
    for hit in sorted(secret + data, key=lambda h: h["start"]):
        if hit["rule"] not in rules:
            rules.append(hit["rule"])
        location = {"file": source, "line": redact.line_of(body, hit["start"])}
        if location not in locations and len(locations) < MAX_LOCATIONS:
            locations.append(location)
    return {
        "secret_hits": len(secret),
        "data_hits": len(data),
        "rules": rules,
        "locations": locations,
    }


def _merge(results: list[dict]) -> dict:
    merged: dict[str, Any] = {"secret_hits": 0, "data_hits": 0, "rules": [], "locations": []}
    for result in results:
        merged["secret_hits"] += result["secret_hits"]
        merged["data_hits"] += result["data_hits"]
        merged["rules"] += [r for r in result["rules"] if r not in merged["rules"]]
        merged["locations"] += result["locations"]
    merged["locations"] = merged["locations"][:MAX_LOCATIONS]
    return merged


# ---------------------------------------------------------------- 振り分け


def _kinds(payload: dict) -> list[str]:
    unknown = set(payload) - set(PAYLOAD_KINDS)
    if unknown:
        raise StoreError(
            "LLM に渡す内容の区分が不正です。スキーマ・仕様・データのいずれかで指定してください。"
        )
    return [k for k in PAYLOAD_KINDS if str(payload.get(k) or "").strip()]


def route(job: dict, payload: dict, purpose: str = "") -> str:
    """送信先を決める。データ値を含む・扱う用途は Ollama 固定。"""
    if "data" in _kinds(payload) or purpose in DATA_PURPOSES:
        return PROVIDER_OLLAMA
    configured = str(((job or {}).get("llm") or {}).get("provider") or PROVIDER_OPENAI)
    return PROVIDER_OLLAMA if configured == PROVIDER_OLLAMA else PROVIDER_OPENAI


def _assert_openai_scope(kinds: list[str]) -> None:
    if set(kinds) - OPENAI_KINDS:
        raise StoreError(
            "外部の LLM にはスキーマと仕様だけを送れます。データ値はローカルの LLM で扱ってください。"
        )


def build_body(payload: dict) -> str:
    """区分ごとに見出しを付けた送信本文（ハッシュの対象と同じ）。"""
    return "\n\n".join(
        f"## {kind}\n{str(payload[kind]).strip()}" for kind in _kinds(payload)
    )


def _blocking(provider: str, inspection: dict) -> bool:
    if inspection["secret_hits"]:
        return True
    return provider == PROVIDER_OPENAI and inspection["data_hits"] > 0


def _block_message(provider: str, inspection: dict) -> str:
    places = "、".join(f"{loc['file']} {loc['line']} 行目" for loc in inspection["locations"][:5])
    if inspection["secret_hits"]:
        reason = "送信内容に秘密情報らしき値が含まれていたため、LLM へ送りませんでした"
    else:
        reason = "外部の LLM へ送る内容にデータ値が含まれていたため、送りませんでした"
    return f"{reason}（{places}）。該当箇所を伏せ字にしてから、もう一度生成してください。"


def make_record(stage: int, purpose: str, provider: str, kinds: list[str],
                body: str, inspection: dict, sent: bool) -> dict:
    """llm_log の 1 件（本文は持たず sha256 だけ）。"""
    return {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stage": stage,
        "purpose": purpose,
        "provider": provider,
        "kinds": list(kinds),
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "inspection": dict(inspection),
        "sent": sent,
    }


def append_record(job: dict, record: dict) -> dict:
    """llm_log に記録を足した新しい Job を返す（入力は変更しない）。"""
    return {**job, "llm_log": [*(job.get("llm_log") or []), record]}


# ---------------------------------------------------------------- 送信


def send(
    job: dict,
    stage: int,
    purpose: str,
    payload: dict,
    actor: str,
    *,
    secrets: Iterable[str] = (),
    data_values: Iterable[str] = (),
    instructions: str = "",
    transport: Transport | None = None,
) -> dict:
    """検査を通った場合だけ送り ``{"text", "record"}`` を返す。

    secrets は実行時に入力された接続の秘密（メモリ内のみ）、data_values は io/golden・
    テストデータの列値（column_values で作る）。止めた場合は GateBlocked（record 付き）。
    actor は呼び出し側が audit に残す（llm_log の形には含めない）。
    """
    del actor  # 記録の形は基本設計書 3.2 に合わせる。監査は呼び出し側
    kinds = _kinds(payload)
    if not kinds:
        raise StoreError("LLM に渡す内容が空です。資料を取り込んでから生成してください。")
    provider = route(job, payload, purpose)
    if provider == PROVIDER_OPENAI:
        _assert_openai_scope(kinds)
    secrets, data_values = list(secrets), list(data_values)
    inspection = _merge(
        [inspect(str(payload[k]), secrets, data_values, source=k) for k in kinds]
    )
    body = build_body(payload)
    if _blocking(provider, inspection):
        record = make_record(stage, purpose, provider, kinds, body, inspection, sent=False)
        raise GateBlocked(_block_message(provider, inspection), record)
    record = make_record(stage, purpose, provider, kinds, body, inspection, sent=True)
    try:
        text = (transport or _default_transport)(provider, instructions, body)
    except (openai_qa.OpenAIQAError, OSError, ValueError) as exc:
        raise LlmCallFailed(
            "LLM の呼び出しに失敗しました。接続設定を確かめて、もう一度生成してください。", record
        ) from exc
    return {"text": text, "record": record}


def _default_transport(provider: str, instructions: str, body: str) -> str:
    if provider == PROVIDER_OPENAI:
        return _call_openai(instructions, body)
    return _call_ollama(instructions, body)


def _post_json(url: str, payload: dict, headers: dict[str, str]) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SEC) as response:  # nosec B310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise openai_qa.OpenAIQAError(f"LLM API error: HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise openai_qa.OpenAIQAError(f"LLM API request failed: {exc}") from exc


def _call_openai(instructions: str, body: str) -> str:
    env = _read_env()
    api_key = env.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise openai_qa.OpenAIQAError("OPENAI_API_KEY が設定されていません。")
    payload = {
        "model": env.get("OPENAI_MODEL", "").strip() or DEFAULT_OPENAI_MODEL,
        "input": [
            {"role": "system", "content": instructions or "You are a senior QA engineer."},
            {"role": "user", "content": body},
        ],
    }
    data = _post_json(
        openai_qa.OPENAI_RESPONSES_URL, payload, openai_qa._openai_headers(api_key, env)
    )
    text = openai_qa._extract_output_text(data)
    if not text:
        raise openai_qa.OpenAIQAError("OpenAI API response did not include output text.")
    return text


def _call_ollama(instructions: str, body: str) -> str:
    """ローカルの OpenAI 互換サーバ（Ollama）へ送る。宛先はローカルホストに限る。"""
    env = _read_env()
    base_url = env.get(openai_qa.ENV_LLM_BASE_URL, "").strip() or OLLAMA_DEFAULT_BASE_URL
    if not openai_qa._is_local_base_url(base_url):
        raise openai_qa.OpenAIQAError("データ値を扱う LLM の宛先がローカルではありません。")
    payload = {
        "model": env.get("WEBSPEC2DOC_LLM_MODEL", "").strip() or OLLAMA_DEFAULT_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": instructions or "You are a senior QA engineer."},
            {"role": "user", "content": body},
        ],
    }
    data = _post_json(
        f"{base_url.rstrip('/')}/chat/completions", payload, {"Content-Type": "application/json"}
    )
    try:
        return str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise openai_qa.OpenAIQAError("LLM の応答に本文がありませんでした。") from exc
