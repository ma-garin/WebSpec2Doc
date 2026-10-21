"""意味レビュー委員会。専門 Reviewer が独立に分析し、実在する根拠のある指摘だけを候補として返す。

LLM へは該当チャンク（伏せ字済み）だけを渡す。他 Reviewer の結論は渡さない。AI は人の判断を上書きしない
（status は常に CANDIDATE）。client=None は DEGRADED で、決定論の結果には触れない。
"""
from __future__ import annotations

import hashlib
from types import SimpleNamespace
from typing import Any

try:
    from web.services.docverify.llm_assist import AssistError, _call, mask
except ImportError:  # pragma: no cover
    from services.docverify.llm_assist import AssistError, _call, mask
from . import confidence as _conf
from . import evidence_guard as guard

REVIEWERS = {
    "Requirements": "要件の完全性・一貫性・曖昧さ",
    "QA-Testability": "テスト可能性・受入基準・境界値",
    "Architecture": "構成・責務分割・依存",
    "Security": "認証・認可・暗号・機密情報",
    "Performance": "応答時間・容量・スループット",
    "Reliability": "障害時挙動・再試行・タイムアウト・復旧",
    "UX": "利用者の操作・メッセージ・状態遷移",
    "Accessibility": "支援技術・キーボード操作・色以外の手段",
    "Operations": "運用・保守・設定・デプロイ",
    "Data": "データ定義・保持・整合性・移行",
    "Integration": "外部連携・インターフェース・契約",
    "Observability": "ログ・メトリクス・監視・追跡",
}
SCHEMA = {"type": "object", "properties": {"findings": {"type": "array", "items": {"type": "object", "properties": {
    "finding": {"type": "string"}, "reason": {"type": "string"}, "severity": {"type": "string"},
    "confidence": {"type": "number"}, "question": {"type": "string"}, "recommended_action": {"type": "string"},
    "stance": {"type": "string"},
    "evidence": {"type": "array", "items": {"type": "object", "properties": {
        "document_id": {"type": "string"}, "line_start": {"type": "integer"},
        "line_end": {"type": "integer"}, "quote": {"type": "string"}}}}}}}}}
SEV = ("info", "low", "medium", "high", "critical")
_CACHE: dict[str, list] = {}


def clear_cache() -> None:
    _CACHE.clear()


def _get(u, key, default=""):
    if isinstance(u, dict):
        return u.get(key, default)
    return getattr(u, key, default)


def _chunk(u) -> dict:
    loc = _get(u, "location", None)
    g = (lambda k, d=0: loc.get(k, d)) if isinstance(loc, dict) else (lambda k, d=0: getattr(loc, k, d))
    return {"id": _get(u, "requirement_id"), "document_id": _get(u, "document_id") or g("document_id", ""),
            "line_start": g("line_start"), "line_end": g("line_end"), "text": str(_get(u, "raw_text"))}


def _prompt(role: str, focus: str, ch: dict) -> str:
    body = mask(ch["text"])["text"]  # 送信前の伏せ字（llm_assist の既存関数）
    return (f"あなたは {role} 専門のレビュアーです（観点: {focus}）。次の要件チャンクだけを根拠に、問題点を JSON で返す。"
            "引用は原文の一部をそのまま quote に入れ、document_id と行番号を付ける。根拠が無ければ空配列。\n"
            f"document_id={ch['document_id']} lines={ch['line_start']}-{ch['line_end']}\n---\n{body}")


def _ask(client, role: str, ch: dict, timeout: float, stats: dict) -> list:
    key = hashlib.sha256(f"{getattr(client, 'name', '')}|{getattr(client, 'model', '')}|{role}|{ch['text']}".encode()).hexdigest()
    if key in _CACHE:
        stats["cache_hits"] += 1
        return _CACHE[key]
    stats["sends"] += 1
    data = _call(client, _prompt(role, REVIEWERS[role], ch), "docassure_review", SCHEMA, timeout, None)
    out = [f for f in (data.get("findings") or []) if isinstance(f, dict)]
    _CACHE[key] = out
    return out


def _sev(v) -> str:
    return v if v in SEV else "medium"


def _target(f: dict) -> tuple:
    e = (f.get("evidence") or [{}])[0]
    return (e.get("document_id"), e.get("line_start"), e.get("line_end"))


def run(units, documents, client, reviewers=None, timeout: float = 30.0) -> dict[str, Any]:
    if client is None:
        return {"mode": "DEGRADED", "reason": "semantic review unavailable", "findings": []}
    roles = [r for r in (reviewers or REVIEWERS) if r in REVIEWERS]
    stats = {"cache_hits": 0, "sends": 0, "failures": 0}
    raw: list[dict] = []
    for role in roles:
        for u in units:
            ch = _chunk(u)
            try:
                items = _ask(client, role, ch, timeout, stats)
            except AssistError:
                stats["failures"] += 1
                continue
            for it in items:
                raw.append({**it, "reviewer": role, "requirement_id": ch["id"]})
    if stats["failures"] and not (stats["sends"] - stats["failures"] + stats["cache_hits"]):
        return {"mode": "DEGRADED", "reason": "semantic review unavailable", "findings": [], **stats}
    provider = {"name": getattr(client, "name", ""), "model": getattr(client, "model", "")}
    ok, unsupported, dismissed = [], [], []
    for f in raw:
        v = guard.validate(f, documents)
        if v["status"] != guard.VALID:
            unsupported.append({**f, "status": v["status"], "invalid_reasons": v["reasons"]})
            continue
        ok.append(dict(v["finding"]))
    for f in ok:
        f["counter_evidence"] = counter_evidence.find(f, documents)
    by_target: dict[tuple, set] = {}
    for f in ok:
        by_target.setdefault(_target(f), set()).add(f["reviewer"])
    final = []
    for f in ok:
        sig = {"direct_evidence": bool(f["evidence"]), "sources": len({e["document_id"] for e in f["evidence"]}),
               "contradictions": len(f["counter_evidence"]), "rule_verified": False,
               "reviewer_agreement": len(by_target[_target(f)] - {f["reviewer"]})}
        d = _conf.calibrate_detail(f, sig)
        g = {**f, "severity": _sev(f.get("severity")), "confidence": d["confidence"],
             "confidence_basis": d["basis"], "source": "ai", "status": "CANDIDATE", "provider": provider}
        (dismissed if g["counter_evidence"] else final).append(
            {**g, "dismissed_candidate": True} if g["counter_evidence"] else g)
    final = debate.adjudicate(final)
    return {"mode": "AI", "findings": final, "unsupported": unsupported, "dismissed": dismissed,
            "provider": provider, **stats}


def _adjudicate(findings: list[dict]) -> list[dict]:
    """同一対象で Reviewer 間の主張が割れたら DISPUTED として両方保持する。status は CANDIDATE のまま。"""
    groups: dict[tuple, list[int]] = {}
    for i, f in enumerate(findings):
        groups.setdefault(_target(f), []).append(i)
    out = [dict(f) for f in findings]
    for n, idxs in enumerate(g for g in groups.values() if len(g) > 1):
        fs = [findings[i] for i in idxs]
        if len({f.get("reviewer") for f in fs}) < 2:
            continue
        stances = {f.get("stance") for f in fs if f.get("stance")}
        sevs = [SEV.index(_sev(f.get("severity"))) for f in fs]
        if len(stances) > 1 or max(sevs) - min(sevs) >= 2:
            for i in idxs:
                out[i].update(disputed=True, dispute_status="DISPUTED", dispute_group=f"D{n + 1}", status="CANDIDATE")
    return out


debate = SimpleNamespace(adjudicate=_adjudicate)
counter_evidence = SimpleNamespace(find=guard.find_counter_evidence)
