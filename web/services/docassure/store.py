"""分析結果の保存（サイドカー）。docverify の inspection.json は変えない（後方互換）。"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from web.services.docverify import store as _dv

_NAME = "assurance.json"


def _path(iid: str) -> Path:
    return _dv.doc_dir(iid) / _NAME   # iid の形式検証と テナント境界は doc_dir が担う


def load(iid: str) -> dict | None:
    p = _path(iid)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save(iid: str, result: dict) -> dict:
    out = {**result, "saved_at": datetime.now(timezone.utc).isoformat()}
    d = _path(iid).parent
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, d / _NAME)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return out


def decisions(iid: str) -> list[dict]:
    r = load(iid) or {}
    return list(r.get("decisions") or [])


def add_decision(iid: str, decision: dict) -> dict:
    """人の判断（採否・waiver・矛盾の決定）。AI は呼ばない。分析を再実行しても残す。"""
    r = load(iid) or {}
    entry = {**decision, "at": datetime.now(timezone.utc).isoformat()}
    return save(iid, {**r, "decisions": [*(r.get("decisions") or []), entry]})
