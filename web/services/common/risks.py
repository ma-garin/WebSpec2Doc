"""リスク risk（data/common/<t>/risks/<rk>.json・rev 整数）。

契約 A2 §3.2: 入力 {title, cause, impact, condition, mitigation, evidence_needed[], sources[], tests[], basis}。
数値スコアは持たない（根拠のない数値を作らない）。重大度 severity と優先度 priority は別欄。
"""

from __future__ import annotations

import json
import os
import re
import uuid

from web.services.common import evidence as ev
from web.services.common.evidence import CommonError

SEVERITY = frozenset({"critical", "major", "minor", "trivial"})
PRIORITY = frozenset({"high", "medium", "low"})
_TEXT = ("title", "cause", "impact", "condition", "mitigation")
_RK_RE = re.compile(r"^rk_[0-9a-f]{12}$")
_FORBIDDEN_KEYS = frozenset({"score", "risk_score", "rpn"})


def _dir():
    return ev.base_dir() / "risks"


def _validate(payload: dict, *, partial: bool) -> dict:
    if _FORBIDDEN_KEYS & set(payload):
        raise CommonError("bad_request", "リスクに数値スコアは付けられません。重大度と優先度を選んでください。")
    out: dict = {}
    for key in _TEXT:
        if key in payload or not partial:
            val = str(payload.get(key, "")).strip()
            if key == "title" and not val:
                raise CommonError("bad_request", "リスクの題名を入力してください。")
            out[key] = val
    for key, allowed, label in (("severity", SEVERITY, "重大度"), ("priority", PRIORITY, "優先度")):
        if key in payload or not partial:
            if payload.get(key) not in allowed:
                raise CommonError("bad_request", f"{label}を一覧から選んでください。")
            out[key] = payload[key]
    if "basis" in payload or not partial:
        if payload.get("basis") not in ev.BASIS:
            raise CommonError("bad_request", "根拠の区分（観測・文書・推定・未検証）を選んでください。")
        out["basis"] = payload["basis"]
    if "evidence_needed" in payload or not partial:
        items = payload.get("evidence_needed", [])
        if not isinstance(items, list):
            raise CommonError("bad_request", "必要な証拠は一覧で指定してください。")
        out["evidence_needed"] = [str(x).strip() for x in items if str(x).strip()]
    for key in ("sources", "tests"):
        if key in payload or not partial:
            refs = payload.get(key, [])
            if not isinstance(refs, list):
                raise CommonError("bad_request", "参照は一覧で指定してください。")
            out[key] = [ev.check_ref(r, field=key) for r in refs]
    return out


def _read(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(risk: dict) -> None:
    path = _dir() / f"{risk['id']}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(risk, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def list_for(case: str) -> list[dict]:
    ev.require_case(case)
    d = _dir()
    if not d.is_dir():
        return []
    rows = [_read(p) for p in sorted(d.glob("rk_*.json"))]
    return [r for r in rows if r.get("case") == case]


def create(case: str, payload: dict, idem_key: str) -> dict:
    ev.require_case(case)
    if not idem_key:
        raise CommonError("bad_request", "送信の識別キーがありません。画面を再読込してからやり直してください。")
    body = _validate(payload or {}, partial=False)
    actor = ev.current_actor()
    with ev.locked(_dir()):
        for r in list_for(case):
            if r.get("idem") == idem_key:
                return r
        stamp = {"by": actor, "at": ev.now()}
        risk = {"schema": "common.risk/1", "id": "rk_" + uuid.uuid4().hex[:12], "tenant": ev.tenant_key(),
                "case": case, "rev": 1, **body, "idem": idem_key, "created": stamp, "updated": stamp}
        _save(risk)
    ev.append("risk.create", case, target={"type": "common.risk", "id": risk["id"]}, rev_after=1,
              reason=risk["title"], actor=actor)
    return risk


def update(case: str, rk: str, payload: dict) -> dict:
    ev.require_case(case)
    payload = payload or {}
    path = _dir() / f"{rk}.json"
    if not _RK_RE.match(rk or "") or not path.is_file():
        raise CommonError("not_found", "指定のリスクが見つかりません。一覧を再読込してください。")
    changes = _validate({k: v for k, v in payload.items() if k != "rev"}, partial=True)
    actor = ev.current_actor()
    with ev.locked(_dir()):
        cur = _read(path)
        if cur.get("case") != case:
            raise CommonError("not_found", "指定のリスクが見つかりません。一覧を再読込してください。")
        if payload.get("rev") != cur["rev"]:
            raise CommonError("conflict", "他の人が先に更新しました。再読込して差分を確認してください。",
                              {"expected_rev": payload.get("rev"), "actual_rev": cur["rev"]})
        new = {**cur, **changes, "rev": cur["rev"] + 1, "updated": {"by": actor, "at": ev.now()}}
        _save(new)
    ev.append("risk.update", case, target={"type": "common.risk", "id": rk}, rev_before=cur["rev"],
              rev_after=new["rev"], reason=", ".join(sorted(changes)), actor=actor)
    return new
