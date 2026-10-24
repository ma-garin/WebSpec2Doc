"""共通 API v1（/api/common/v1）。案件・対象版・参照（共通契約 §3.1・§3.2）。

テナントは auth_guard が決めた g.tenant から決め、本文の tenant は信用しない。
応答は必ず {"schema": "common.<名>/1", …}。失敗は {"error": {code, message, …}}。
"""

from __future__ import annotations

import logging

from flask import Blueprint, request

from web.services.common import cases as C
from web.services.common import refs as R
from web.services.common import versions as V
from web.services.common.store import CommonError, idempotent, tenant_key

logger = logging.getLogger(__name__)
bp = Blueprint("common_api_v1", __name__, url_prefix="/api/common/v1")


@bp.errorhandler(CommonError)
def _common_error(exc: CommonError):
    return exc.body(), exc.status


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise CommonError("bad_request", "本文は JSON のオブジェクトで送ってください。")
    return data


def _ok(schema: str, data, status: int = 200):
    return {"schema": schema, "data": data}, status


def _guard(fn):
    """想定外の例外は詳細をログへ、利用者には次の行動だけを返す。"""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except CommonError:
            raise
        except Exception:
            logger.exception("common_api: %s に失敗しました", fn.__name__)
            return CommonError("upstream_failed", "処理に失敗しました。時間をおいて再試行してください。",
                               retryable=True).body(), 500
    wrapper.__name__ = fn.__name__
    return wrapper


@bp.get("/cases")
@_guard
def list_cases():
    return _ok("common.case_list/1", {"tenant": tenant_key(), "items": C.list_cases()})


@bp.post("/cases")
@_guard
def create_case():
    body = _body()

    def run():
        return {"schema": "common.case/1", "data": C.create(body)}, 201
    out, status, replay = idempotent(request.headers.get("Idempotency-Key"), "cases", run)
    return out, status, {"Idempotent-Replayed": "true" if replay else "false"}


@bp.get("/cases/<cid>")
@_guard
def get_case(cid: str):
    return _ok("common.case/1", C.get(cid))


@bp.patch("/cases/<cid>")
@_guard
def patch_case(cid: str):
    return _ok("common.case/1", C.patch(cid, _body()))


@bp.post("/cases/<cid>/versions")
@_guard
def create_version(cid: str):
    body = _body()
    C.get(cid)

    def run():
        out, status = V.create(cid, body)
        return {"schema": "common.version_result/1", "data": out}, status
    out, status, replay = idempotent(request.headers.get("Idempotency-Key"), f"versions:{cid}", run)
    return out, status, {"Idempotent-Replayed": "true" if replay else "false"}


@bp.get("/cases/<cid>/versions/<tv>")
@_guard
def get_version(cid: str, tv: str):
    return _ok("common.target_version/1", V.get(cid, tv))


@bp.post("/cases/<cid>/refs")
@_guard
def add_ref(cid: str):
    return _ok("common.case/1", C.add_ref(cid, _body()), 201)


@bp.delete("/cases/<cid>/refs")
@_guard
def remove_ref(cid: str):
    return _ok("common.case/1", C.remove_ref(cid, _body()))


@bp.get("/cases/<cid>/refs/resolve")
@_guard
def resolve_refs(cid: str):
    case = C.get(cid)
    results = [R.resolve(r) for r in case.get("refs", [])]
    partial = any(r["status"] != "ok" for r in results)
    summary = {s: sum(1 for r in results if r["status"] == s) for s in ("ok", "stale", "missing", "forbidden")}
    return _ok("common.ref_resolution/1",
               {"case": case["id"], "partial": partial, "summary": summary, "items": results},
               207 if partial else 200)
