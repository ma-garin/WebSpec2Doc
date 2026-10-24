"""対象版 target_version の固定と古さ判定（共通契約 §1.4・§3.2）。tv は作成後に書き換えない。"""

from __future__ import annotations

from pathlib import Path

from web.services.common import cases as C
from web.services.common import refs as R
from web.services.common.store import (
    CommonError, actor, check_id, lock, new_id, now, read_json, tenant_key, tenant_root, write_json,
)

SCHEMA = "common.target_version/1"


def _path(tv: str) -> Path:
    return tenant_root() / "versions" / f"{check_id(tv, 'tv')}.json"


def create(cid: str, body: dict) -> tuple[dict, int]:
    """各参照を解決して pinned を埋める。固定できない参照があれば 207 で分けて返す。"""
    case = C.get(cid)
    raw = body.get("refs") if isinstance(body, dict) else None
    if not isinstance(raw, list) or not raw:
        raise CommonError("bad_request", "固定する参照を 1 件以上選んでください。", {"field": "refs"})
    if len(raw) > 200:
        raise CommonError("too_large", "一度に固定できる参照は 200 件までです。分けて送ってください。")
    fixed, failed = [], []
    for item in raw:
        ref = R.normalize(item)
        try:
            fixed.append(R.pin({k: v for k, v in ref.items() if k != "pinned"}))
        except R.Missing:
            failed.append({"ref": ref, "status": "missing",
                           "message": "参照先が見つからないため固定できませんでした。"})
        except CommonError as exc:
            failed.append({"ref": ref, "status": "upstream_failed", "message": exc.message})
    if not fixed:
        return {"schema": "common.version_result/1", "partial": True, "version": None,
                "fixed": [], "failed": failed}, 207
    with lock():
        tv = {"schema": SCHEMA, "id": new_id("tv"), "tenant": tenant_key(), "case": case["id"],
              "previous": case.get("current_version"), "refs": fixed, "unfixed": failed,
              "created": {"by": actor(), "at": now()}}
        write_json(_path(tv["id"]), tv)
        C.set_current_version(cid, tv["id"])
    body_out = {"schema": "common.version_result/1", "partial": bool(failed), "version": tv,
                "fixed": fixed, "failed": failed}
    return body_out, (207 if failed else 201)


def get(cid: str, tv: str) -> dict:
    """版と古さ。refs ごとの解決結果と、案件の現行版かどうかを返す。"""
    case = C.get(cid)
    data = read_json(_path(tv))
    if data is None or data.get("tenant") != tenant_key() or data.get("case") != case["id"]:
        raise CommonError("not_found", "対象版が見つかりません。案件の版一覧から選び直してください。")
    results = [R.resolve(r) for r in data["refs"]]
    stale = [r for r in results if r["status"] != "ok"]
    return {"schema": SCHEMA, "version": data, "is_current": case.get("current_version") == data["id"],
            "fresh": not stale and case.get("current_version") == data["id"], "refs": results}
