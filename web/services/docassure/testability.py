"""テスト可能性の決定論判定。LLM は使わない。原文は書き換えず、書き換え案は「提案（未承認）」で返す。"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, is_dataclass
from typing import Any

CAN_TEST, PARTIAL, NOT_TESTABLE, UNKNOWN = "CAN_TEST", "PARTIALLY_TESTABLE", "NOT_TESTABLE", "UNKNOWN"

VAGUE_WORDS = ("高速", "迅速", "適切", "柔軟", "使いやすい", "なるべく", "十分", "快適", "素早", "スムーズ",
               "簡単", "すばやく", "できるだけ", "速やか", "安全に", "安定")
_UNITS = r"(?:ms|msec|秒|分|時間|日|件|行|レコード|MB|KB|GB|TB|byte|バイト|%|％|回|文字|桁|人|ユーザー|ユーザ|個|ページ)"
RE_THRESHOLD = re.compile(r"\d+(?:\.\d+)?\s*" + _UNITS, re.I)
RE_VOLUME = re.compile(r"\d+(?:\.\d+)?\s*(?:件|行|レコード|MB|GB|TB|人|ユーザー|ユーザ|個|ページ)|データ量|同時")
RE_CONDITION = re.compile(r"環境|負荷|ブラウザ|ネットワーク|回線|計測|測定|平均|パーセンタイル|95|のとき|時に|場合|において|以内に")
RE_SUCCESS = re.compile(r"表示|返す|返却|出力|完了|成功|保存|登録|遷移|通知|できる|更新|削除|送信|ログイン|検索")
RE_FAILURE = re.compile(r"失敗|エラー|異常|拒否|不正|無効|タイムアウト|リトライ|ロック")


def to_dict(obj: Any) -> dict:
    """dict / dataclass / to_dict() 持ちを dict に正規化（元は変更しない）。"""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if is_dataclass(obj):
        return asdict(obj)
    return dict(obj)


def unit_view(unit: Any) -> dict:
    """{requirement_id, kind, raw_text, fields:{名:値}, text} を返す。INFERRED の値は事実として使わない。"""
    d = to_dict(unit)
    fields: dict[str, str] = {}
    for k, f in (d.get("fields") or {}).items():
        if isinstance(f, dict):
            if f.get("provenance") == "INFERRED":
                continue
            v = f.get("value", "")
        else:
            v = getattr(f, "value", f)
            if getattr(f, "provenance", "") == "INFERRED":
                continue
        if v:
            fields[k] = str(v)
    raw = str(d.get("raw_text") or "")
    text = unicodedata.normalize("NFKC", " ".join([raw, *fields.values()]))
    return {"requirement_id": d.get("requirement_id", ""), "kind": d.get("kind", "functional"),
            "raw_text": raw, "fields": fields, "text": text,
            "document_id": d.get("document_id", "")}


def assess(unit: Any) -> dict:
    v = unit_view(unit)
    text, fields = v["text"], v["fields"]
    if not text.strip():
        return {"verdict": UNKNOWN, "reasons": ["原文が空のため判定できない"], "missing": [], "rewrite_proposal": None}
    vague = [w for w in VAGUE_WORDS if w in text]
    has_threshold = bool(RE_THRESHOLD.search(text))
    has_success = bool(fields.get("expected_result") or fields.get("acceptance_criteria") or RE_SUCCESS.search(text))
    has_failure = bool(fields.get("exception") or RE_FAILURE.search(text))
    has_condition = bool(fields.get("condition") or fields.get("constraint") or RE_CONDITION.search(text))
    has_volume = bool(RE_VOLUME.search(text))
    missing: list[str] = []
    reasons: list[str] = []
    if not has_success:
        missing.append("成功条件")
    if not has_failure:
        missing.append("失敗時の挙動")
    if not has_threshold:
        missing.append("閾値・単位")
    if not has_condition:
        missing.append("測定条件")
    if not has_volume:
        missing.append("対象データ量")
    for w in vague:
        reasons.append(f"「{w}」の定義がない")
    if not has_threshold:
        reasons.append("閾値・単位がない")
    if vague and not has_threshold:
        verdict = NOT_TESTABLE
    elif not has_success and not has_threshold:
        verdict = NOT_TESTABLE
        reasons.append("成功条件も閾値もない")
    elif has_success and has_threshold and not vague and (has_failure or has_condition):
        verdict = CAN_TEST
    else:
        verdict = PARTIAL
    if verdict == CAN_TEST:
        reasons = ["成功条件と閾値があり、判定基準を機械的に決められる"]
    elif verdict == PARTIAL and not reasons:
        reasons = ["一部の判定基準が不足している"]
    proposal = None
    if verdict != CAN_TEST:
        proposal = ("提案（未承認・原文は変更しない）: 次を確定して書き足す -> "
                    + " / ".join(missing or ["判定基準"])
                    + "。例: 「<条件>のとき、<対象>を<N>件のデータで<M>秒以内に表示する。失敗時は<エラー>を返す」")
    return {"verdict": verdict, "reasons": reasons, "missing": missing, "rewrite_proposal": proposal}
