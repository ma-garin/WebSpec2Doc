"""型付き参照 ref の検証と解決（共通契約 §1.2）。

解決は各 System の既存ローダ・既存の保存先を読むだけで、既存データには書かない。
参照先が無ければ missing（参照切れ）とし、0 件や空で埋めない。
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any, Callable

from web import config
from web.services.common.store import CommonError, now, sha256_file, sha256_obj, tenant_key
from web.tenancy import scoped_output_dir

TYPES_V1 = (
    "site.domain", "site.run", "docverify.inspection", "docverify.document", "docverify.finding",
    "docassure.analysis", "ta2.test", "ta.defect", "ta.completion", "autorun.run",
    "healing.project", "healing.run", "batchtest.job", "backendtest.job", "impact.job",
    "impact.cr", "orchestration.run",
)
BASIS = ("observed", "document", "inferred", "unverified")
_ID = re.compile(r"^[0-9A-Za-z_.-]{1,128}$")
_DOMAIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")


class Missing(Exception):
    """参照先が既存の保存先に無い。"""


def _ident(ref: dict) -> tuple:
    return (ref["type"], ref["id"], json.dumps(ref.get("sub") or {}, sort_keys=True))


def same(a: dict, b: dict) -> bool:
    return _ident(a) == _ident(b)


def normalize(raw: Any) -> dict:
    """入力の ref を検証して正規化する。他テナントの参照は存在しないものとして 404。"""
    if not isinstance(raw, dict):
        raise CommonError("bad_request", "参照は type・tenant・id・basis を持つ形で送ってください。")
    rtype, rid, basis = raw.get("type"), raw.get("id"), raw.get("basis")
    if rtype not in TYPES_V1:
        raise CommonError("bad_request", "参照の種類が不正です。決められた種類から選んでください。",
                          {"type": rtype})
    if rtype not in RESOLVERS:
        raise CommonError("bad_request", "この種類の参照は v1 ではまだ解決できません。",
                          {"type": rtype, "supported": sorted(RESOLVERS)})
    if not isinstance(rid, str) or not _ID.match(rid):
        raise CommonError("bad_request", "参照の id が不正です。")
    if basis not in BASIS:
        raise CommonError("bad_request", "根拠区分（observed／document／inferred／unverified）を選んでください。")
    if raw.get("tenant") != tenant_key():
        raise CommonError("not_found", "参照先が見つかりません。対象を選び直してください。")
    sub = raw.get("sub") or {}
    if not isinstance(sub, dict) or not all(isinstance(v, str) and _ID.match(v) for v in sub.values()):
        raise CommonError("bad_request", "参照の sub が不正です。")
    ref = {"type": rtype, "tenant": tenant_key(), "id": rid, "sub": sub, "basis": basis}
    if isinstance(raw.get("pinned"), dict):
        pinned = {k: raw["pinned"][k] for k in ("rev", "sha256", "mtime", "at") if k in raw["pinned"]}
        ref["pinned"] = pinned
    return ref


# ---- 各 System の既存保存先を読む解決関数。戻り値は current（rev か sha256＋mtime）。 ----

def _file_current(path: Path) -> dict:
    if not path.is_file():
        raise Missing(str(path.name))
    return {"sha256": sha256_file(path), "mtime": int(path.stat().st_mtime)}


def _inspection(ref: dict) -> dict:
    from web.services.docverify import store as dv
    try:
        insp = dv.load(ref["id"])
    except KeyError as exc:
        raise Missing("inspection") from exc
    return insp


def _r_inspection(ref: dict) -> dict:
    insp = _inspection(ref)
    cur = _file_current(Path(_dv_path(ref["id"])))
    if insp.get("rev") is not None:
        cur["rev"] = insp["rev"]
    return cur


def _dv_path(iid: str) -> Path:
    from web.services.docverify import store as dv
    return dv.doc_dir(iid) / "inspection.json"


def _r_document(ref: dict) -> dict:
    insp = _inspection(ref)
    doc_id = ref["sub"].get("document")
    if doc_id:
        docs = [v for v in insp.get("versions") or [] if str(v.get("id")) == doc_id]
        if not docs:
            raise Missing("document")
        return {"sha256": sha256_obj(docs[0])}
    if not insp.get("document"):
        raise Missing("document")
    return {"sha256": sha256_obj(insp["document"])}


def _r_finding(ref: dict) -> dict:
    insp = _inspection(ref)
    fid = ref["sub"].get("finding")
    hits = [f for f in insp.get("findings") or [] if str(f.get("id")) == fid]
    if not fid or not hits:
        raise Missing("finding")
    cur = {"sha256": sha256_obj(hits[0])}
    if insp.get("rev") is not None:
        cur["rev"] = insp["rev"]
    return cur


def _r_domain(ref: dict) -> dict:
    if not _DOMAIN.match(ref["id"]) or ".." in ref["id"]:
        raise Missing("domain")
    root = scoped_output_dir(config.OUTPUT_DIR) / ref["id"]
    if not root.is_dir():
        raise Missing("domain")
    report = root / "report.json"
    return _file_current(report) if report.is_file() else {"mtime": int(root.stat().st_mtime)}


def _r_run(ref: dict) -> dict:
    from web.services.run_store import run_dir, run_exists
    domain = ref["sub"].get("domain", "")
    if not _DOMAIN.match(domain) or ".." in domain:
        raise Missing("run")
    out = scoped_output_dir(config.OUTPUT_DIR)
    target = run_dir(out, domain, ref["id"])
    if target is None or not run_exists(out, domain, ref["id"]):
        raise Missing("run")
    return _file_current(target / "meta.json")


def _r_healing_project(ref: dict) -> dict:
    from web.services.healing import project_store
    project = project_store.get_project(scoped_output_dir(config.OUTPUT_DIR), ref["id"])
    if project is None:
        raise Missing("healing.project")
    data = dataclasses.asdict(project) if dataclasses.is_dataclass(project) else vars(project)
    return {"sha256": sha256_obj(data)}


def _job(module: str) -> Callable[[dict], dict]:
    def resolve(ref: dict) -> dict:
        mod = __import__(f"web.services.{module}.store", fromlist=["job_dir"])
        try:
            directory = mod.job_dir(ref["id"])
        except KeyError as exc:
            raise Missing("job") from exc
        return _file_current(directory / "job.json")
    return resolve


RESOLVERS: dict[str, Callable[[dict], dict]] = {
    "docverify.inspection": _r_inspection,
    "docverify.document": _r_document,
    "docverify.finding": _r_finding,
    "site.domain": _r_domain,
    "site.run": _r_run,
    "healing.project": _r_healing_project,
    "batchtest.job": _job("batchtest"),
    "backendtest.job": _job("backendtest"),
}


def current(ref: dict) -> dict:
    """現在の版。参照切れは Missing。読取りの失敗は upstream_failed。"""
    try:
        return RESOLVERS[ref["type"]](ref)
    except Missing:
        raise
    except (OSError, ValueError) as exc:
        raise CommonError("upstream_failed", "参照先の読み込みに失敗しました。時間をおいて再試行してください。",
                          {"type": ref["type"], "id": ref["id"]}, retryable=True) from exc


def pin(ref: dict) -> dict:
    """参照時点の版を埋める。参照切れは Missing を送出する。"""
    cur = current(ref)
    return {**ref, "pinned": {**{k: cur[k] for k in ("rev", "sha256", "mtime") if k in cur}, "at": now()}}


def _is_stale(pinned: dict, cur: dict) -> bool:
    if "rev" in pinned and "rev" in cur:
        return pinned["rev"] != cur["rev"]
    if "sha256" in pinned and "sha256" in cur:
        return pinned["sha256"] != cur["sha256"]
    if "mtime" in pinned and "mtime" in cur:
        return pinned["mtime"] != cur["mtime"]
    return False


def resolve(ref: dict) -> dict:
    """1 件の解決結果 {ref, status: ok|stale|missing|forbidden, current, basis}。"""
    out = {"ref": ref, "basis": ref.get("basis", "unverified")}
    if ref.get("tenant") != tenant_key():
        return {**out, "status": "forbidden", "current": None}
    if ref.get("type") not in RESOLVERS:
        return {**out, "status": "missing", "current": None, "reason": "unsupported_type"}
    try:
        cur = current(ref)
    except Missing:
        return {**out, "status": "missing", "current": None}
    except CommonError as exc:
        return {**out, "status": "missing", "current": None, "reason": exc.code}
    status = "stale" if _is_stale(ref.get("pinned") or {}, cur) else "ok"
    return {**out, "status": status, "current": cur}
