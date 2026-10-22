"""引用の実在検証と反証探索。実在しない根拠・根拠なしの指摘はユーザー向け一覧から隔離する。"""
from __future__ import annotations

import hashlib
import re
from typing import Any

try:
    from web.services.docverify.llm_assist import mask
except ImportError:  # pragma: no cover
    from services.docverify.llm_assist import mask

VALID, INVALID_EVIDENCE, UNSUPPORTED = "VALID", "INVALID_EVIDENCE", "UNSUPPORTED"
_WS = re.compile(r"\s+")


def snippet_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _norm(t: str) -> str:
    return _WS.sub("", t or "")


def doc_index(documents) -> dict[str, list[str]]:
    """documents: [{id|document_id, text}] または {id: text}。行配列にして返す。"""
    items = documents.items() if isinstance(documents, dict) else (
        ((d.get("id") or d.get("document_id")), d.get("text", "")) for d in documents)
    return {str(i): str(t or "").splitlines() for i, t in items}


def _check_one(ev: dict, idx: dict[str, list[str]]) -> tuple[bool, str]:
    lines = idx.get(str(ev.get("document_id", "")))
    if lines is None:
        return False, "document not found"
    quote = str(ev.get("quote") or "")
    if not _norm(quote):
        return False, "empty quote"
    try:
        a, b = int(ev.get("line_start", 0)), int(ev.get("line_end", 0))
    except (TypeError, ValueError):
        return False, "bad line range"
    if a < 1 or b < a or b > len(lines):
        return False, "line out of range"
    seg = "\n".join(lines[a - 1:b])
    q = _norm(quote)
    if q in _norm(seg) or q in _norm(mask(seg)["text"]):  # 伏せ字後の文を引用した場合も実在とみなす
        return True, ""
    return False, "quote not in cited lines"


def validate(finding: dict, documents) -> dict[str, Any]:
    idx = doc_index(documents)
    evs = [e for e in (finding.get("evidence") or []) if isinstance(e, dict)]
    if not evs:
        return {"status": UNSUPPORTED, "reasons": ["no evidence"], "finding": dict(finding)}
    good, reasons = [], []
    for e in evs:
        ok, why = _check_one(e, idx)
        if ok:
            good.append({**e, "snippet_hash": snippet_hash(str(e["quote"]))})
        else:
            reasons.append(f"{e.get('document_id')}:{e.get('line_start')}-{e.get('line_end')} {why}")
    if len(good) != len(evs):
        return {"status": INVALID_EVIDENCE, "reasons": reasons, "finding": dict(finding)}
    return {"status": VALID, "reasons": [], "finding": {**finding, "evidence": good}}


# --- 反証探索（決定論）---
_NEG = re.compile(r"未定義|未記載|記載(?:が)?(?:な|無)|定義(?:が)?(?:な|無)|不明|欠如|ない|なし|無い|不足|未規定|未指定|missing|undefined|not defined")
_TOPICS = ("タイムアウト", "認証", "ログ", "暗号", "監査", "バックアップ", "応答時間", "リトライ", "再試行", "権限",
           "可用性", "障害", "監視", "性能", "文字数", "上限", "桁", "エラー", "保持期間", "同時")


def find_counter_evidence(finding: dict, documents) -> list[dict]:
    """主張が否定する話題（例 タイムアウト）を、指摘の根拠行の外で肯定的に述べる記述を探す。"""
    text = " ".join(str(finding.get(k) or "") for k in ("finding", "reason"))
    if not _NEG.search(text):
        return []
    topics = [t for t in _TOPICS if t in text]
    own = {(str(e.get("document_id")), n) for e in finding.get("evidence") or [] if isinstance(e, dict)
           for n in range(int(e.get("line_start") or 0), int(e.get("line_end") or 0) + 1)}
    out = []
    for did, lines in doc_index(documents).items():
        for n, line in enumerate(lines, 1):
            if (did, n) in own or _NEG.search(line):
                continue
            for t in topics:
                if t in line and re.search(r"\d|[をがはにで]", line):
                    out.append({"document_id": did, "line_start": n, "line_end": n,
                                "quote": line.strip()[:120], "topic": t})
                    break
    return out
