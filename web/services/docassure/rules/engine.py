"""ルールエンジン。pack（データ）＋検出器（コード）を回し Finding と結果表を返す。"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from ..model import (CANDIDATE, DETERMINISTIC, FAIL, NOT_APPLICABLE, NOT_EVALUATED, PASS,
                     Finding, Location)
from .detectors import DETECTORS, Ctx

_PACKS = Path(__file__).parent / "packs"


def load_pack(name: str = "default", extra: dict | None = None) -> dict:
    """pack を読み、extra（組織固有の語彙・必須項目・無効化）を足した新しい dict を返す。

    extra: params のキー（ambiguous_terms/tbd_patterns/id_prefixes/required_items ...）は
    リストなら追記、それ以外は上書き。disabled_rules=[rule_id], profile="strict" も可。
    """
    if not name.replace("_", "").replace("-", "").isalnum():
        raise ValueError(f"pack 名が不正: {name}")
    path = _PACKS / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"pack が無い: {name}")
    pack = json.loads(path.read_text(encoding="utf-8"))
    for key, val in (extra or {}).items():
        if key == "disabled_rules":
            for r in pack["rules"]:
                if r["rule_id"] in val:
                    r["enabled"] = False
        elif key == "profile":
            pack["profile"] = val
        elif key == "ambiguous_terms":
            pack["params"][key] += [t if isinstance(t, dict) else {"term": t, "pattern": _esc(t)} for t in val]
        elif isinstance(val, list) and isinstance(pack["params"].get(key), list):
            pack["params"][key] = pack["params"][key] + copy.deepcopy(val)
        else:
            pack["params"][key] = copy.deepcopy(val)
    return pack


def _esc(s: str) -> str:
    import re
    return re.escape(s)


def _location(document_id: str, line, no: int) -> Location:
    text = line.text.strip() if line else ""
    return Location(document_id=document_id, section=line.section if line else "", line_start=no, line_end=no,
                    snippet=text[:120], snippet_hash=hashlib.sha1(text.encode("utf-8")).hexdigest()[:12])


def _req_at(units, no: int) -> str:
    for u in units or []:
        loc = getattr(u, "location", None)
        if loc and loc.line_start and loc.line_start <= no <= (loc.line_end or loc.line_start):
            return u.requirement_id
    return ""


def run_rules(document_id: str, markdown: str, units: list, pack: dict | None = None,
              other_docs: dict[str, str] | None = None) -> dict:
    pack = pack or load_pack()
    ctx = Ctx(markdown, pack["params"], other_docs)
    by_no = {ln.no: ln for ln in ctx.lines}
    findings, results = [], []
    for rule in pack["rules"]:
        rid, ver = rule["rule_id"], rule["version"]
        base = {"rule_id": rid, "rule_version": ver}
        profiles = rule.get("profile") or []
        if not rule.get("enabled", True) or (profiles and pack.get("profile") not in profiles):
            results.append({**base, "result": NOT_APPLICABLE, "checked": 0, "reason": "無効化、または今のプロファイルの対象外"})
            continue
        det = DETECTORS.get(rule["detector"])
        if det is None:
            results.append({**base, "result": NOT_EVALUATED, "checked": 0, "reason": f"検出器 {rule['detector']} が未実装"})
            continue
        out = det(ctx)
        if out.skip:
            results.append({**base, "result": NOT_EVALUATED, "checked": out.checked, "reason": out.skip})
            continue
        for n, h in enumerate(out.hits, 1):
            req = _req_at(units, h.line)
            findings.append(Finding(
                finding_id=f"{rid}:{req or 'L' + str(h.line)}:{n}", rule_id=rid, rule_version=ver, result=FAIL,
                severity=rule["severity"], title=rule["name"], why_matters=rule["why"], reason=h.reason,
                how_to_fix=rule["how_to_fix"], location=_location(document_id, by_no.get(h.line), h.line),
                requirement_id=req, source=DETERMINISTIC, status=CANDIDATE, confidence=h.confidence,
                confidence_basis=tuple(h.basis), counter_evidence=tuple(h.counter)))
        if out.hits:
            results.append({**base, "result": FAIL, "checked": out.checked, "reason": f"{len(out.hits)} 件の指摘（{out.checked} 件を検査）"})
        else:
            results.append({**base, "result": PASS, "checked": out.checked, "reason": f"{out.checked} 件を検査し指摘なし"})
    return {"findings": findings, "results": results}
