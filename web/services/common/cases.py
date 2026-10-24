"""QA案件 case の作成・読取・更新と参照の付け外し（共通契約 §1.4・§3.2）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from web.services.common import refs as R
from web.services.common.store import (
    CommonError, actor, check_id, lock, new_id, now, read_json, tenant_key, tenant_root, write_json,
)

SCHEMA = "common.case/1"
STATES = ("open", "closed", "archived")
_EDITABLE = ("title", "question", "scope", "constraints", "stakeholders", "targets", "state")


def _dir() -> Path:
    return tenant_root() / "cases"


def _path(cid: str) -> Path:
    return _dir() / f"{check_id(cid, 'cs')}.json"


def _text(value: Any, name: str, *, required: bool, limit: int = 500) -> str:
    if value is None or value == "":
        if required:
            raise CommonError("bad_request", f"{name}を入力してください。", {"field": name})
        return ""
    if not isinstance(value, str) or len(value) > limit:
        raise CommonError("bad_request", f"{name}は {limit} 文字以内の文字で入力してください。", {"field": name})
    return value.strip()


def _str_list(value: Any, name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) and len(v) <= 200 for v in value):
        raise CommonError("bad_request", f"{name}は文字の一覧で送ってください。", {"field": name})
    return [v.strip() for v in value if v.strip()]


def _fields(body: dict, *, partial: bool) -> dict:
    out: dict[str, Any] = {}
    if not partial or "title" in body:
        out["title"] = _text(body.get("title"), "案件名", required=True, limit=120)
    if not partial or "question" in body:
        out["question"] = _text(body.get("question"), "判断したいこと", required=False)
    if not partial or "scope" in body:
        scope = body.get("scope") or {}
        if not isinstance(scope, dict):
            raise CommonError("bad_request", "範囲は in と out の一覧で送ってください。", {"field": "scope"})
        out["scope"] = {"in": _str_list(scope.get("in"), "範囲(in)"), "out": _str_list(scope.get("out"), "範囲(out)")}
    if not partial or "constraints" in body:
        out["constraints"] = _str_list(body.get("constraints"), "制約")
    if not partial or "stakeholders" in body:
        sh = body.get("stakeholders") or []
        if not isinstance(sh, list) or not all(
                isinstance(s, dict) and isinstance(s.get("role"), str) and isinstance(s.get("user_id"), str)
                for s in sh):
            raise CommonError("bad_request", "関係者は role と user_id の組で送ってください。", {"field": "stakeholders"})
        out["stakeholders"] = [{"role": s["role"][:40], "user_id": s["user_id"][:64]} for s in sh]
    if partial and "targets" in body:
        if not isinstance(body["targets"], list):
            raise CommonError("bad_request", "対象は参照の一覧で送ってください。", {"field": "targets"})
        out["targets"] = [R.normalize(t) for t in body["targets"]]
    if partial and "state" in body:
        if body["state"] not in STATES:
            raise CommonError("bad_request", "状態は open／closed／archived から選んでください。", {"field": "state"})
        out["state"] = body["state"]
    return out


def create(body: dict) -> dict:
    if not isinstance(body, dict):
        raise CommonError("bad_request", "入力の形式が正しくありません。")
    fields = _fields(body, partial=False)
    stamp = {"by": actor(), "at": now()}
    case = {"schema": SCHEMA, "id": new_id("cs"), "tenant": tenant_key(), "rev": 1, **fields,
            "targets": [], "current_version": None, "refs": [], "state": "open",
            "created": stamp, "updated": stamp}
    with lock():
        write_json(_path(case["id"]), case)
    return case


def get(cid: str) -> dict:
    case = read_json(_path(cid))
    if case is None or case.get("tenant") != tenant_key():
        raise CommonError("not_found", "案件が見つかりません。一覧から選び直してください。")
    return case


def list_cases() -> list[dict]:
    d = _dir()
    if not d.is_dir():
        return []
    items = [read_json(p) for p in sorted(d.glob("cs_*.json"))]
    items = [c for c in items if c and c.get("tenant") == tenant_key()]
    return sorted(items, key=lambda c: c["updated"]["at"], reverse=True)


def _require_rev(case: dict, rev: Any) -> None:
    if not isinstance(rev, int) or isinstance(rev, bool):
        raise CommonError("bad_request", "更新には rev（読み込んだ時点の版）が必要です。", {"field": "rev"})
    if rev != case["rev"]:
        raise CommonError("conflict", "他の人が先に更新しました。再読込して差分を確認してください。",
                          {"expected_rev": rev, "actual_rev": case["rev"]})


def _save(case: dict) -> dict:
    new = {**case, "rev": case["rev"] + 1, "updated": {"by": actor(), "at": now()}}
    write_json(_path(new["id"]), new)
    rebuild_index()
    return new


def patch(cid: str, body: dict) -> dict:
    if not isinstance(body, dict):
        raise CommonError("bad_request", "入力の形式が正しくありません。")
    with lock():
        case = get(cid)
        _require_rev(case, body.get("rev"))
        return _save({**case, **_fields(body, partial=True)})


def set_current_version(cid: str, tv_id: str) -> dict:
    with lock():
        case = get(cid)
        return _save({**case, "current_version": tv_id})


def add_ref(cid: str, body: dict) -> dict:
    with lock():
        case = get(cid)
        _require_rev(case, body.get("rev"))
        ref = R.normalize(body.get("ref"))
        if any(R.same(ref, r) for r in case["refs"]):
            raise CommonError("conflict", "この参照はすでに付いています。", {"ref": ref})
        try:
            pinned = ref if ref.get("pinned") else R.pin(ref)
            R.current(ref)
        except R.Missing as exc:
            raise CommonError("not_found", "参照先が見つかりません。対象を選び直してください。",
                              {"type": ref["type"], "id": ref["id"]}) from exc
        return _save({**case, "refs": [*case["refs"], pinned]})


def remove_ref(cid: str, body: dict) -> dict:
    with lock():
        case = get(cid)
        _require_rev(case, body.get("rev"))
        target = body.get("ref")
        if not isinstance(target, dict) or "type" not in target or "id" not in target:
            raise CommonError("bad_request", "外す参照の type と id を指定してください。")
        target = {"type": target["type"], "id": target["id"], "sub": target.get("sub") or {}}
        kept = [r for r in case["refs"] if not R.same(r, target)]
        if len(kept) == len(case["refs"]):
            raise CommonError("not_found", "その参照はこの案件に付いていません。")
        return _save({**case, "refs": kept})


def rebuild_index() -> None:
    """逆引き索引 index/<type>.json（type＋id → 案件）。正は cases/*.json、索引は派生物（§5.1）。"""
    index: dict[str, dict[str, list[str]]] = {}
    for case in list_cases():
        for ref in [*case.get("refs", []), *case.get("targets", [])]:
            index.setdefault(ref["type"], {}).setdefault(ref["id"], [])
            if case["id"] not in index[ref["type"]][ref["id"]]:
                index[ref["type"]][ref["id"]].append(case["id"])
    for rtype, mapping in index.items():
        write_json(tenant_root() / "index" / f"{rtype}.json", {"schema": "common.index/1", "map": mapping})
