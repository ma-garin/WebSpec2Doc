"""共通の証跡（data/common/<t>/audit.jsonl）と、C2 の最小ストア。

契約 A2 §4.2: seq＋SHA-256 連鎖（06 の _r4_audit.jsonl と同じ方式）。
追記と読取・検算だけを持ち、行を書き換える関数・消す関数は置かない（編集禁止）。
主体は web/auth.py の auth_guard が入れる g.auth_user。認証オフ・未ログインはゲスト。
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import g, has_request_context

from web import config
from web.tenancy import scoped_output_dir

_GENESIS = "0" * 64
NO_TENANT = "_none"
JST = timezone(timedelta(hours=9))
CASE_ID_RE = re.compile(r"^cs_[0-9a-f]{12}$")
REF_TYPES = frozenset({
    "site.domain", "site.run", "docverify.inspection", "docverify.document", "docverify.finding",
    "docassure.analysis", "ta2.test", "ta.defect", "ta.completion", "autorun.run",
    "healing.project", "healing.run", "batchtest.job", "backendtest.job", "impact.job",
    "impact.cr", "orchestration.run",
})
BASIS = frozenset({"observed", "document", "inferred", "unverified"})


class CommonError(Exception):
    """契約 §3.1 のエラー形式へ写す例外。route 層が JSON に変換する。"""

    STATUS = {"bad_request": 400, "unauthorized": 401, "forbidden": 403, "not_found": 404,
              "conflict": 409, "stale": 409, "too_large": 413}

    def __init__(self, code: str, message: str, detail: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.detail = code, message, detail or {}

    @property
    def status(self) -> int:
        return self.STATUS.get(self.code, 400)


def now() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def tenant_key() -> str:
    """要求本文ではなく g.tenant から決める（契約 §1.3）。テナント無しは _none。"""
    base = Path(config.DATA_DIR) / "common"
    scoped = scoped_output_dir(base)
    return NO_TENANT if scoped == base else scoped.name


def base_dir() -> Path:
    base = Path(config.DATA_DIR) / "common"
    scoped = scoped_output_dir(base)
    return base / NO_TENANT if scoped == base else scoped


@contextlib.contextmanager
def locked(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / ".lock", "a", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def current_actor() -> dict:
    """証跡の主体。user_id を正とし表示名も残す。ゲストは user_id=None。"""
    user = getattr(g, "auth_user", None) if has_request_context() else None
    if not isinstance(user, dict) or not user.get("id"):
        return {"user_id": None, "name": "ゲスト", "auth": "off"}
    name = user.get("display_name") or user.get("username") or user.get("email") or str(user["id"])
    return {"user_id": str(user["id"]), "name": str(name), "auth": str(getattr(g, "auth_via", "session"))}


def require_case(cid: str) -> Path:
    """案件は C1 の保存先規約 cases/<cid>.json にあるものだけを対象にする。"""
    if not CASE_ID_RE.match(cid or ""):
        raise CommonError("not_found", "指定の案件が見つかりません。一覧から選び直してください。")
    path = base_dir() / "cases" / f"{cid}.json"
    if not path.is_file():
        raise CommonError("not_found", "指定の案件が見つかりません。一覧から選び直してください。")
    return path


def check_ref(ref, *, field: str = "target") -> dict:
    """型付き参照の形とテナントを検査する。他テナントの参照は 404（存在を明かさない）。"""
    if not isinstance(ref, dict) or ref.get("type") not in REF_TYPES or not str(ref.get("id", "")).strip():
        raise CommonError("bad_request", f"{field} の参照の形が正しくありません。対象を選び直してください。")
    if ref.get("tenant") != tenant_key():
        raise CommonError("not_found", "参照先が見つかりません。対象を選び直してください。")
    if ref.get("basis") not in BASIS:
        raise CommonError("bad_request", f"{field} の根拠の区分（観測・文書・推定・未検証）を選んでください。")
    return dict(ref)


def _path() -> Path:
    return base_dir() / "audit.jsonl"


def _digest(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def append(op: str, case: str, *, target: dict | None = None, rev_before=None, rev_after=None,
           reason: str = "", ai: bool = False, actor: dict | None = None) -> dict:
    """1 行追記する。既存行は読むだけで書き換えない。"""
    path = _path()
    with locked(path.parent):
        lines = _lines(path)
        prev = json.loads(lines[-1]).get("hash", _GENESIS) if lines else _GENESIS
        entry = {"seq": len(lines) + 1, "prev": prev, "at": now(), "actor": actor or current_actor(),
                 "op": op, "case": case, "target": target, "rev_before": rev_before,
                 "rev_after": rev_after, "reason": reason, "ai": bool(ai)}
        entry = {**entry, "hash": _digest(entry)}
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read(case: str | None = None) -> list[dict]:
    rows = [json.loads(ln) for ln in _lines(_path())]
    return [r for r in rows if case is None or r.get("case") == case]


def verify() -> dict:
    """連鎖を頭から検算し、最初に食い違った行番号を返す。"""
    lines = _lines(_path())
    prev = _GENESIS
    for n, ln in enumerate(lines, start=1):
        try:
            e = json.loads(ln)
        except ValueError:
            e = {}
        if e.get("prev") != prev or e.get("seq") != n or e.get("hash") != _digest(e):
            return {"ok": False, "line": n, "count": len(lines),
                    "message": f"証跡の {n} 行目に改ざんまたは破損があります。管理者に連絡してください。"}
        prev = e["hash"]
    return {"ok": True, "line": None, "count": len(lines), "message": f"証跡 {len(lines)} 行に食い違いはありません。"}
