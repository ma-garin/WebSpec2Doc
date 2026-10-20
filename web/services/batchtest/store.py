"""案件（job）の保存と読み出し。1 案件 = 1 フォルダ（job.json と取り込んだファイル）。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from web import config
from web.tenancy import scoped_output_dir

_JID = re.compile(r"^[0-9a-f]{12}$")
_SUMMARY_EXCLUDE = ("facts", "cases", "sources", "spec")

ENVS = ("cmd", "sh", "pwsh")
FRAMEWORKS = ("pytest", "pester", "bats")
KINDS = ("script", "spec", "input", "expected")
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_FILES = 30


class StoreError(ValueError):
    """利用者に見せてよい理由を持つ失敗。"""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _root() -> Path:
    return scoped_output_dir(config.DATA_DIR) / "batchtest"


def _check(jid: str) -> str:
    if not isinstance(jid, str) or not _JID.match(jid):
        raise KeyError(jid)
    return jid


def job_dir(jid: str) -> Path:
    return _root() / _check(jid)


def files_dir(jid: str) -> Path:
    return job_dir(jid) / "files"


def new(name: str) -> dict:
    ts = now()
    return {
        "id": uuid.uuid4().hex[:12], "name": name, "created_at": ts, "updated_at": ts,
        "files": [], "settings": {"env": "cmd", "framework": "pytest", "command": ""},
        "facts": None, "spec": [], "cases": [], "sources": [],
        "analyzed_at": None, "designed_at": None, "generated_at": None,
    }


EXPORT_KINDS = ("cases.xlsx", "code.zip", "questions.csv")


def export_basis(job: dict, kind: str) -> str:
    """書き出した中身の指紋。ケース表・質問票はケースから、テストコード一式はケースとコードから作る。"""
    part: dict = {"cases": job.get("cases") or []}
    if kind == "code.zip":
        part["sources"] = job.get("sources") or []
    raw = json.dumps(part, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def with_export_state(job: dict) -> dict:
    """書き出しの記録に「その後で中身が変わったか（stale）」を付ける。

    記録はサーバがファイルを送り出した事実だけ。受け取り・実行・確認は記録しない（画面では未実行・未確認のまま）。
    """
    exports = job.get("exports")
    if not isinstance(exports, dict) or not exports:
        return job
    marked = {
        kind: {**rec, "stale": rec.get("basis") != export_basis(job, kind)}
        for kind, rec in exports.items()
        if kind in EXPORT_KINDS and isinstance(rec, dict)
    }
    return {**job, "exports": marked}


def load(jid: str) -> dict:
    path = job_dir(jid) / "job.json"
    if not path.is_file():
        raise KeyError(jid)
    return with_export_state(json.loads(path.read_text(encoding="utf-8")))


def save(job: dict) -> dict:
    job = {**job, "updated_at": now()}
    directory = job_dir(job["id"])
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(job, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, directory / "job.json")
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return with_export_state(job)


def summary(job: dict) -> dict:
    asks = sum(1 for c in job.get("cases") or [] if c.get("ask"))
    return {**{k: v for k, v in job.items() if k not in _SUMMARY_EXCLUDE},
            "case_count": len(job.get("cases") or []), "ask_count": asks}


def list_all() -> list[dict]:
    root = _root()
    if not root.is_dir():
        return []
    items = []
    for child in root.iterdir():
        if not _JID.match(child.name):
            continue
        try:
            items.append(summary(load(child.name)))
        except (KeyError, ValueError, OSError):
            continue
    return sorted(items, key=lambda x: x.get("updated_at", ""), reverse=True)


def guess_kind(name: str) -> str:
    low = name.lower()
    suffix = Path(low).suffix
    if suffix in (".bat", ".cmd", ".sh", ".ps1"):
        return "script"
    if suffix in (".xlsx", ".docx", ".md", ".pdf") or re.search(r"仕様|spec|設計|readme", low):
        return "spec"
    if re.search(r"expect|期待|正解|golden", low):
        return "expected"
    return "input"


_SAFE = re.compile(r"[^\w.\-（）()一-龥ぁ-んァ-ヶー]")


def safe_name(name: str) -> str:
    base = Path(name or "").name.strip()
    base = _SAFE.sub("_", base)[:120]
    if not base or base in (".", "..") or base.startswith("."):
        raise StoreError("ファイル名が読めません。英数字か日本語の名前にしてから取り込んでください。")
    return base


def add_file(job: dict, filename: str, data: bytes) -> dict:
    name = safe_name(filename)
    if not data:
        raise StoreError(f"{name} は空です。中身のあるファイルを選んでください。")
    if len(data) > MAX_FILE_BYTES:
        raise StoreError(f"{name} が 20MB を超えています。小さくしてから取り込んでください。")
    others = [f for f in job["files"] if f["name"] != name]
    if len(others) >= MAX_FILES:
        raise StoreError(f"取り込めるのは 1 案件 {MAX_FILES} ファイルまでです。不要なファイルを外してください。")
    directory = files_dir(job["id"])
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(data)
    entry = {"name": name, "kind": guess_kind(name), "size": len(data), "added_at": now()}
    return {**job, "files": others + [entry]}


def remove_file(job: dict, name: str) -> dict:
    if not any(f["name"] == name for f in job["files"]):
        raise KeyError(name)
    path = files_dir(job["id"]) / safe_name(name)
    path.unlink(missing_ok=True)
    return {**job, "files": [f for f in job["files"] if f["name"] != name]}


def file_path(job: dict, name: str) -> Path:
    return files_dir(job["id"]) / safe_name(name)
