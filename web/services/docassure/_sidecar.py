"""サイドカー JSON の原子的な読み書き（baseline/feedback/policy 共通）。"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from web.services.docverify import perm, store as _dv


def load(iid: str, name: str, default):
    p = _dv.doc_dir(iid) / name
    if not p.is_file():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def update(iid: str, name: str, default, fn):
    """排他の下で fn(現在値)->新値 を保存して返す。"""
    d = _dv.doc_dir(iid)
    with perm.locked(d):
        new = fn(load(iid, name, default))
        fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(new, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, d / name)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return new
