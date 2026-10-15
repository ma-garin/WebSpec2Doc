"""AI の説明（System 06 R2）: 送信前の伏せ字・説明と書き換え案・解釈の揺れ・時間切れとキャンセル。

契約: docs/sdlc/20_design/WS2D-DD-006_詳細設計書_System06_R2.md 2 章。
LLM の呼び出し口は ``LLMClient``（``request(prompt, schema_name, schema, timeout_sec) -> dict``）。
本物は llm_settings.client_for が作り、テストはスタブを渡す。
"""
from __future__ import annotations

import difflib
import hashlib
import re
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

TIMEOUT_SEC = 60.0  # NFR-06-11（暫定。要確認-7）
POLL_SEC = 0.1
SIMILARITY = 0.8  # FR-06-116（暫定。R5 で見直す）
WOBBLE_RUNS = 3

KINDS = ("email", "phone", "postal", "url_query", "api_key", "my_number", "card", "ip")
LABELS = {"email": "メール", "phone": "電話", "postal": "郵便番号", "url_query": "URL の値",
          "api_key": "API キー", "my_number": "個人番号", "card": "カード番号", "ip": "IP アドレス",
          "manual": "伏せ字"}

_P = {
    "url_query": re.compile(r"(?<=[?&])[A-Za-z0-9_.\-%]+=([^&#\s]+)"),
    "email": re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
    "api_key": re.compile(r"\b(?:sk-(?:proj-)?[A-Za-z0-9_\-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
                          r"|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{30,}|xox[abprs]-[A-Za-z0-9\-]{10,}"
                          r"|[A-Za-z0-9]{32,})\b"),
    "card": re.compile(r"(?<![\d-])\d(?:[ -]?\d){12,18}(?![\d-])"),
    "my_number": re.compile(r"(?<![\d-])\d{4}[ -]?\d{4}[ -]?\d{4}(?![\d-])"),
    "phone": re.compile(r"(?<![\d-])(?:\+81[ -]?\d{1,4}[ -]?\d{1,4}[ -]?\d{3,4}|0\d{1,4}-\d{1,4}-\d{3,4}"
                        r"|0[5789]0\d{8}|0\d{9})(?![\d-])"),
    "postal": re.compile(r"(?:〒\s?)?(?<![\d-])\d{3}-\d{4}(?![\d-])"),
    "ip": re.compile(r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\d.])"),
}
# 重なりは先に見つけた種類を優先する（カード番号 → 個人番号 → 電話 → 郵便番号の順で数字列を取り合う）
_ORDER = ("url_query", "email", "api_key", "card", "my_number", "phone", "postal", "ip")


class AssistError(RuntimeError):
    """LLM が失敗した（接続不可・応答不正）。利用者向けの文は route が出す。"""


class AssistTimeout(AssistError):
    """時間切れ。"""


class AssistCancelled(AssistError):
    """利用者が取りやめた。"""


class LLMClient(Protocol):
    name: str
    model: str

    def request(self, prompt: str, schema_name: str, schema: dict, timeout_sec: float) -> dict: ...


def luhn(digits: str) -> bool:
    nums = [int(c) for c in digits if c.isdigit()]
    if not 13 <= len(nums) <= 19:
        return False
    total = 0
    for i, n in enumerate(reversed(nums)):
        if i % 2:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def _spans_of(kind: str, text: str) -> list[tuple[int, int]]:
    out = []
    for m in _P[kind].finditer(text):
        start, end = (m.start(1), m.end(1)) if kind == "url_query" else (m.start(), m.end())
        if kind == "card" and not luhn(m.group()):
            continue
        out.append((start, end))
    return out


def find(text: str, extra: list | None = None) -> list[dict]:
    """伏せ字にする範囲（元の文の位置）を返す。extra は利用者が足す [start, end] の並び。"""
    taken: list[dict] = []
    for start, end in _clean_extra(text, extra):
        taken.append({"kind": "manual", "start": start, "end": end})
    for kind in _ORDER:
        for start, end in _spans_of(kind, text):
            if all(end <= t["start"] or start >= t["end"] for t in taken):
                taken.append({"kind": kind, "start": start, "end": end})
    return sorted(taken, key=lambda s: s["start"])


def _clean_extra(text: str, extra) -> list[tuple[int, int]]:
    out = []
    for item in extra or []:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError("伏せ字の範囲が正しくありません。文を選び直してください。")
        s, e = item
        if not isinstance(s, int) or not isinstance(e, int) or not 0 <= s < e <= len(text):
            raise ValueError("伏せ字の範囲が正しくありません。文を選び直してください。")
        if all(e <= a or s >= b for a, b in out):
            out.append((s, e))
    return out


def word_ranges(text: str, words) -> list[list[int]]:
    """利用者が足す伏せ字の語（送信前確認で入力）を、元の文の範囲に直す。"""
    if words is None:
        return []
    if not isinstance(words, list) or not all(isinstance(w, str) for w in words):
        raise ValueError("伏せ字の範囲が正しくありません。文を選び直してください。")
    out = []
    for w in {w.strip() for w in words if w.strip()}:
        out.extend([m.start(), m.end()] for m in re.finditer(re.escape(w), text))
    return out


def mask(text: str, extra: list | None = None) -> dict:
    """伏せ字後の文と、伏せ字の位置（伏せ字後の文での位置）を返す。"""
    spans = find(text, extra)
    parts, out_spans, cursor, pos = [], [], 0, 0
    for s in spans:
        parts.append(text[cursor:s["start"]])
        pos += s["start"] - cursor
        token = f"［{LABELS[s['kind']]}］"
        out_spans.append({"kind": s["kind"], "start": pos, "end": pos + len(token)})
        parts.append(token)
        pos += len(token)
        cursor = s["end"]
    parts.append(text[cursor:])
    counts = {k: sum(1 for s in spans if s["kind"] == k) for k in (*KINDS, "manual")}
    return {"text": "".join(parts), "spans": out_spans, "counts": counts}


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_text(insp: dict, finding: dict) -> str:
    """送る元の文: 指摘の規則・文・引用と、その断片の全文。"""
    pid = finding.get("passage_id")
    passage = next((p for p in insp.get("passages") or [] if p.get("id") == pid), None)
    body = (passage or {}).get("text") or finding.get("quote") or ""
    return (f"規則: {finding.get('rule') or ''} {finding.get('viewpoint') or ''}\n"
            f"候補: {finding.get('message') or ''}\n引用: {finding.get('quote') or ''}\n断片: {body}")


EXPLAIN_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["reason", "rewrite", "open_questions"],
    "properties": {"reason": {"type": "string"}, "rewrite": {"type": "string"},
                   "open_questions": {"type": "array", "items": {"type": "string"}}},
}
INTERPRET_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["interpretation"],
                    "properties": {"interpretation": {"type": "string"}}}


def _explain_prompt(masked: str) -> str:
    return ("あなたは要件文書のレビュアーです。次の規則の候補について、なぜ問題になりうるかを 3 文以内で述べ、"
            "書き換え案を 1 つ、文書で決まっていない事項（作成者への質問）を 0〜3 件、日本語で出してください。"
            "［］の部分は伏せ字です。推測で埋めないでください。\n\n" + masked)


def _interpret_prompt(masked: str) -> str:
    return "次の文の意味を 1 文で言い換えてください。［］は伏せ字です。\n\n" + masked


def three_sentences(text: str) -> str:
    parts = [p for p in re.split(r"(?<=[。！？!?])", str(text or "").strip()) if p.strip()]
    return "".join(parts[:3]).strip()


def run_with_timeout(fn: Callable[[], Any], timeout: float, cancel: threading.Event | None = None) -> Any:
    """fn を別スレッドで動かし、時間切れ（AssistTimeout）とキャンセル（AssistCancelled）で打ち切る。"""
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(fn)
    waited = 0.0
    try:
        while True:
            if cancel is not None and cancel.is_set():
                future.cancel()
                raise AssistCancelled("cancelled")
            step = min(POLL_SEC, max(timeout - waited, 0))
            try:
                return future.result(timeout=step)
            except FutureTimeout:
                waited += step
                if waited >= timeout:
                    future.cancel()
                    raise AssistTimeout("timeout") from None
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _call(client: LLMClient, prompt: str, name: str, schema: dict, timeout: float, cancel) -> dict:
    try:
        data = run_with_timeout(lambda: client.request(prompt, name, schema, timeout), timeout, cancel)
    except AssistError:
        raise
    except Exception as exc:  # 接続不可・応答不正・HTTP エラーはまとめて縮退する（FR-06-115）
        raise AssistError(type(exc).__name__) from exc
    if not isinstance(data, dict):
        raise AssistError("invalid_response")
    return data


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKC", str(text or "")).lower()
    return re.sub(r"[\s。、．，,.!！?？「」『』（）()・:：;；\"']", "", t)


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def judge_wobble(interpretations: list[str]) -> dict:
    """どの組も 0.8 未満なら「割れ」（FR-06-116）。"""
    sims = [similarity(a, b) for i, a in enumerate(interpretations) for b in interpretations[i + 1:]]
    best = max(sims, default=0.0)
    return {"interpretations": list(interpretations), "max_similarity": round(best, 3),
            "split": bool(sims) and best < SIMILARITY}


def explain(client: LLMClient, masked: str, *, with_wobble: bool = False,
            timeout: float | None = None, cancel: threading.Event | None = None) -> dict:
    """説明・書き換え案・未決定事項を作る。指摘の状態は変えない（FR-06-110）。"""
    limit = TIMEOUT_SEC if timeout is None else timeout
    data = _call(client, _explain_prompt(masked), "docverify_explain", EXPLAIN_SCHEMA, limit, cancel)
    questions = [str(q).strip() for q in data.get("open_questions") or [] if str(q).strip()][:3]
    ai = {"label": "AI の提案", "provider": client.name, "model": client.model,
          "explanation": three_sentences(data.get("reason")), "rewrite": str(data.get("rewrite") or "").strip(),
          "open_questions": questions, "generated_at": datetime.now(timezone.utc).isoformat(),
          "input_sha256": sha256(masked), "adopted": None, "wobble": None}
    if not ai["explanation"] and not ai["rewrite"]:
        raise AssistError("empty")
    if with_wobble:
        texts = [str(_call(client, _interpret_prompt(masked), "docverify_interpret", INTERPRET_SCHEMA,
                           limit, cancel).get("interpretation") or "") for _ in range(WOBBLE_RUNS)]
        ai = {**ai, "wobble": judge_wobble(texts)}
    return ai


def sends_for(with_wobble: bool) -> int:
    return 1 + (WOBBLE_RUNS if with_wobble else 0)
