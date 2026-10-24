"""判断 decision（data/common/<t>/decisions.jsonl・追記のみ）。

契約 A2 §1.1・§4.3: 起票 drafted → 承認 approved → 取消 revoked。行を書き換えず事象を追記し、
状態は畳み込みで求める。承認は認証済み主体のみ・起票者と別人・合格した判断のみ（403）。
"""

from __future__ import annotations

import json
import uuid

from web.services.common import evidence as ev
from web.services.common.evidence import CommonError

KINDS = frozenset({"risk_acceptance", "spec_judgement", "release"})
CONCLUSIONS = frozenset({"accept", "reject", "conditional"})
_TV_PREFIX = "tv_"


def _path():
    return ev.base_dir() / "decisions.jsonl"


def _events() -> list[dict]:
    path = _path()
    if not path.is_file():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _fold(events: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for e in events:
        if e["event"] == "drafted":
            out[e["id"]] = {**e["body"], "id": e["id"], "case": e["case"], "state": "drafted", "rev": 1,
                            "drafted": {"by": e["actor"], "at": e["at"]}, "approved": None, "revoked": None}
        elif e["id"] in out:
            cur = out[e["id"]]
            out[e["id"]] = {**cur, "state": e["event"], "rev": cur["rev"] + 1,
                            e["event"]: {"by": e["actor"], "at": e["at"], **e["body"]}}
    return out


def _schema(d: dict) -> dict:
    return {"schema": "common.decision/1", **d}


def list_for(case: str) -> list[dict]:
    ev.require_case(case)
    return [_schema(d) for d in _fold(_events()).values() if d["case"] == case]


def _write(event: dict) -> None:
    with open(_path(), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def _validate_draft(payload: dict) -> dict:
    kind, conclusion = payload.get("kind"), payload.get("conclusion")
    rationale = str(payload.get("rationale", "")).strip()
    if kind not in KINDS:
        raise CommonError("bad_request", "判断の種類（リスク受容・仕様判定・リリース判定）を選んでください。")
    if conclusion not in CONCLUSIONS:
        raise CommonError("bad_request", "結論（受容・却下・条件付き）を選んでください。")
    if not rationale:
        raise CommonError("bad_request", "判断の根拠を 1 文以上書いてください。")
    gate = payload.get("gate") or {}
    if not isinstance(gate, dict) or not isinstance(gate.get("passed", False), bool):
        raise CommonError("bad_request", "合否の形が正しくありません。対象の結果を選び直してください。")
    return {"kind": kind, "conclusion": conclusion, "rationale": rationale,
            "target": ev.check_ref(payload.get("target")), "basis": payload.get("target", {}).get("basis"),
            "gate": {"passed": bool(gate.get("passed", False)), "source": gate.get("source")}}


def draft(case: str, payload: dict, idem_key: str) -> dict:
    ev.require_case(case)
    if not idem_key:
        raise CommonError("bad_request", "送信の識別キーがありません。画面を再読込してからやり直してください。")
    body = _validate_draft(payload or {})
    with ev.locked(ev.base_dir()):
        events = _events()
        for e in events:
            if e["event"] == "drafted" and e["case"] == case and e.get("idem") == idem_key:
                return _schema(_fold(events)[e["id"]])
        dc = "dc_" + uuid.uuid4().hex[:12]
        actor = ev.current_actor()
        _write({"event": "drafted", "id": dc, "case": case, "idem": idem_key, "at": ev.now(),
                "actor": actor, "body": body})
        result = _fold(_events())[dc]
    ev.append("decision.draft", case, target=body["target"], rev_after=1, reason=body["rationale"], actor=actor)
    return _schema(result)


def _load(case: str, dc: str) -> dict:
    ev.require_case(case)
    d = _fold(_events()).get(dc)
    if d is None or d["case"] != case:
        raise CommonError("not_found", "指定の判断が見つかりません。一覧を再読込してください。")
    return d


def _require_rev(d: dict, payload: dict) -> None:
    if payload.get("rev") != d["rev"]:
        raise CommonError("conflict", "他の人が先に更新しました。再読込して差分を確認してください。",
                          {"expected_rev": payload.get("rev"), "actual_rev": d["rev"]})


def _require_human(actor: dict, verb: str) -> None:
    if not actor.get("user_id"):
        raise CommonError("forbidden", f"{verb}はログインした利用者だけが行えます。ログインしてからやり直してください。")


def approve(case: str, dc: str, payload: dict) -> dict:
    payload = payload or {}
    actor = ev.current_actor()
    _require_human(actor, "承認")
    tv, reason = str(payload.get("tv", "")).strip(), str(payload.get("reason", "")).strip()
    with ev.locked(ev.base_dir()):
        d = _load(case, dc)
        if d["state"] != "drafted":
            raise CommonError("conflict", "この判断は起票中ではないため承認できません。再読込してください。",
                              {"state": d["state"]})
        _require_rev(d, payload)
        if d["drafted"]["by"].get("user_id") == actor["user_id"]:
            from web.services.approval_policy import self_approval_note
            note = self_approval_note()
            if note is None:
                raise CommonError("forbidden", "起票した本人は承認できません。別の承認者に依頼してください。")
            reason = f"{reason}（{note}）" if reason else reason
        if not d["gate"]["passed"]:
            raise CommonError("forbidden", "合格していない判断は承認できません。結果を確認して起票し直してください。")
        if not tv.startswith(_TV_PREFIX) or not reason:
            raise CommonError("bad_request", "承認する対象の版と、承認の理由を入力してください。")
        _write({"event": "approved", "id": dc, "case": case, "at": ev.now(), "actor": actor,
                "body": {"tv": tv, "reason": reason}})
        result = _fold(_events())[dc]
    ev.append("decision.approve", case, target=d["target"], rev_before=d["rev"], rev_after=result["rev"],
              reason=reason, actor=actor)
    return _schema(result)


def revoke(case: str, dc: str, payload: dict) -> dict:
    payload = payload or {}
    actor = ev.current_actor()
    _require_human(actor, "取消")
    reason = str(payload.get("reason", "")).strip()
    with ev.locked(ev.base_dir()):
        d = _load(case, dc)
        if d["state"] == "revoked":
            raise CommonError("conflict", "この判断は既に取り消されています。再読込してください。")
        _require_rev(d, payload)
        if actor["user_id"] not in (d["drafted"]["by"].get("user_id"), ((d.get("approved") or {}).get("by") or {}).get("user_id")):
            raise CommonError("forbidden", "取り消せるのは起票した本人か承認者だけです。")
        if not reason:
            raise CommonError("bad_request", "取り消す理由を入力してください。")
        _write({"event": "revoked", "id": dc, "case": case, "at": ev.now(), "actor": actor,
                "body": {"reason": reason}})
        result = _fold(_events())[dc]
    ev.append("decision.revoke", case, target=d["target"], rev_before=d["rev"], rev_after=result["rev"],
              reason=reason, actor=actor)
    return _schema(result)
