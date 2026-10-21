"""既知指摘の baseline と再分析との差分分類。同一性は rule_id + 要件 fingerprint（位置が動いても同一）。"""
from __future__ import annotations

from datetime import datetime, timezone

from . import _sidecar

_NAME = "assurance_baseline.json"
NEW, EXISTING, RESOLVED, REGRESSED = "NEW", "EXISTING", "RESOLVED", "REGRESSED"


def key_of(finding: dict, fp_by_req: dict) -> str:
    rid = finding.get("requirement_id") or ""
    fp = fp_by_req.get(rid) or (finding.get("location") or {}).get("snippet_hash") or rid
    return f"{finding.get('rule_id')}|{fp}"


def keyed(result: dict) -> dict:
    """result の FAIL 指摘を key -> 指摘 の dict にする。"""
    if isinstance(result.get("findings"), dict):   # baseline 形式（保存済み）
        return result["findings"]
    fp = {r.get("requirement_id"): r.get("fingerprint") for r in result.get("requirements") or []}
    return {key_of(f, fp): f for f in result.get("findings") or [] if f.get("result", "FAIL") == "FAIL"}


def _slim(f: dict) -> dict:
    return {k: f.get(k) for k in ("finding_id", "rule_id", "severity", "title", "requirement_id")}


def get(iid: str) -> dict | None:
    return _sidecar.load(iid, _NAME, None)


def set(iid: str, result: dict) -> dict:  # noqa: A001 - 仕様の名前
    cur = keyed(result)

    def fn(old):
        resolved = set_(old.get("resolved_keys") if old else [])
        if old:
            resolved |= set_(old["findings"]) - set_(cur)
        resolved -= set_(cur)
        return {"at": datetime.now(timezone.utc).isoformat(),
                "findings": {k: _slim(f) for k, f in cur.items()},
                "resolved_keys": sorted(resolved)}
    return _sidecar.update(iid, _NAME, None, fn)


set_ = frozenset  # 内部用の別名（組み込み set を上で隠すため）


def compare(before: dict, after: dict) -> dict:
    """before: baseline（findings: key->指摘, resolved_keys）か分析結果。after: 分析結果。"""
    if isinstance(before.get("findings"), dict):
        b, resolved = before["findings"], set_(before.get("resolved_keys") or [])
    else:
        b, resolved = keyed(before), set_()
    a = keyed(after)
    out = {NEW: [], EXISTING: [], RESOLVED: [], REGRESSED: []}
    for k, f in a.items():
        if k in b:
            out[EXISTING].append(_slim(f))
        elif k in resolved:
            out[REGRESSED].append(_slim(f))
        else:
            out[NEW].append(_slim(f))
    out[RESOLVED] = [_slim(f) if "finding_id" in f else f for k, f in b.items() if k not in a]
    return {**out, "counts": {k: len(v) for k, v in out.items()}}
