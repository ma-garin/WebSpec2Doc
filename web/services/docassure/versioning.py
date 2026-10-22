"""版ごとの差分をつないで、要件ごとの変更履歴を作る。"""
from __future__ import annotations

from web.services.docassure.semantic_diff import diff


def history(versions: list[dict]) -> dict:
    """versions: [{"version": "v1", "units": [...]}...]（古い順）。

    返り値: {"versions": [...], "requirements": {requirement_id: [{version, change, ...}]}}
    """
    reqs: dict[str, list[dict]] = {}
    alias: dict[str, str] = {}   # 旧 ID -> 履歴上の正 ID（採番変更を同一要件として追う）
    if versions:
        v0 = versions[0]
        for u in v0.get("units", []):
            rid = _rid(u)
            reqs.setdefault(rid, []).append({"version": v0["version"], "change": "CREATED"})
    for prev, cur in zip(versions, versions[1:]):
        for d in diff(prev.get("units", []), cur.get("units", [])):
            ch = d["change"]
            rid = d["requirement_id"]
            entry = {"version": cur["version"], "change": ch}
            for k in ("change_type", "topic", "before_value", "after_value", "risk",
                      "impacted_requirements", "after_ids", "before_ids"):
                if k in d:
                    entry[k] = d[k]
            if ch == "MOVED":
                b = d["before"]["requirement_id"]
                alias[rid] = alias.get(b, b)
            key = alias.get(rid, rid)
            if ch == "SPLIT":
                for n in d["after_ids"]:
                    alias[n] = key
            if ch == "MERGED":
                for o in d["before_ids"]:
                    reqs.setdefault(alias.get(o, o), []).append(entry)
            reqs.setdefault(key, []).append(entry)
    return {"versions": [v["version"] for v in versions], "requirements": reqs}


def _rid(u) -> str:
    return u.get("requirement_id", "") if isinstance(u, dict) else getattr(u, "requirement_id", "")
