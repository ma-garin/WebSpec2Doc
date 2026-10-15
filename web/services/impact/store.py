"""分析（job）の保存と読み出し。1 分析 = 1 フォルダ（job.json・取り込んだ文書・読み取った断片）。"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from web import config
from web.tenancy import scoped_output_dir

_JID = re.compile(r"^[0-9a-f]{12}$")
_SUMMARY_EXCLUDE = ("changes", "queries", "impacts")

ROLES = ("new", "old", "store")
STORES = ("設計書", "画面仕様書", "テストケース", "その他")
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_FILES = 60


class StoreError(ValueError):
    """利用者に見せてよい理由を持つ失敗。"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _root() -> Path:
    return scoped_output_dir(config.DATA_DIR) / "impact"


def _check(jid: str) -> str:
    if not isinstance(jid, str) or not _JID.match(jid):
        raise KeyError(jid)
    return jid


def job_dir(jid: str) -> Path:
    return _root() / _check(jid)


def new(name: str) -> dict:
    ts = now()
    return {"id": uuid.uuid4().hex[:12], "name": name, "order": "", "created_at": ts, "updated_at": ts,
            "docs": [], "changes": [], "queries": [], "impacts": [], "notes": [], "analyzed_at": None}


def load(jid: str) -> dict:
    path = job_dir(jid) / "job.json"
    if not path.is_file():
        raise KeyError(jid)
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def save(job: dict) -> dict:
    job = {**job, "updated_at": now()}
    _write_json(job_dir(job["id"]) / "job.json", job)
    return job


def delete(job: dict) -> None:
    shutil.rmtree(job_dir(job["id"]), ignore_errors=True)


def summary(job: dict) -> dict:
    p1 = sum(1 for r in job.get("impacts") or [] if r.get("priority") == 1)
    return {**{k: v for k, v in job.items() if k not in _SUMMARY_EXCLUDE},
            "impact_count": len(job.get("impacts") or []), "p1_count": p1}


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


def guess_role(name: str) -> str:
    low = name.lower()
    if re.search(r"旧|変更前|old|before|_prev", low):
        return "old"
    if re.search(r"新|変更後|改訂|new|after", low):
        return "new"
    return "store"


def guess_store(name: str) -> str:
    low = name.lower()
    if re.search(r"テスト|test|tc[-_]|ケース", low):
        return "テストケース"
    if re.search(r"画面|ui|screen|画面仕様", low):
        return "画面仕様書"
    if re.search(r"設計|design|仕様|spec", low):
        return "設計書"
    return "その他"


_SAFE = re.compile(r"[^\w.\-（）()一-龥ぁ-んァ-ヶー]")


def safe_name(name: str) -> str:
    base = _SAFE.sub("_", Path(name or "").name.strip())[:120]
    if not base or base in (".", "..") or base.startswith("."):
        raise StoreError("ファイル名が読めません。英数字か日本語の名前にしてから取り込んでください。")
    return base


def file_path(job: dict, name: str) -> Path:
    return job_dir(job["id"]) / "files" / safe_name(name)


def passages_path(job: dict, name: str) -> Path:
    return job_dir(job["id"]) / "passages" / (safe_name(name) + ".json")


def add_doc(job: dict, filename: str, data: bytes) -> dict:
    """文書を保存し、読み取った断片を passages/ に置く。読めない文書は StoreError。"""
    from web.services.docverify.ingest import IngestError, ingest
    name = safe_name(filename)
    if len(data) > MAX_FILE_BYTES:
        raise StoreError(f"{name} が 20MB を超えています。分割してから取り込んでください。")
    others = [d for d in job["docs"] if d["name"] != name]
    if len(others) >= MAX_FILES:
        raise StoreError(f"取り込めるのは 1 分析 {MAX_FILES} 文書までです。不要な文書を外してください。")
    try:
        _, passages = ingest(name, data, job_dir(job["id"]) / "work")
    except IngestError as exc:
        raise StoreError(f"{name}: {exc}") from exc
    path = file_path(job, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    _write_json(passages_path(job, name), passages)
    prev = next((d for d in job["docs"] if d["name"] == name), None)
    entry = {"name": name, "role": prev["role"] if prev else guess_role(name),
             "store": prev["store"] if prev else guess_store(name),
             "size": len(data), "passages": len(passages), "indexed_at": now()}
    return {**job, "docs": others + [entry]}


def remove_doc(job: dict, name: str) -> dict:
    if not any(d["name"] == name for d in job["docs"]):
        raise KeyError(name)
    file_path(job, name).unlink(missing_ok=True)
    passages_path(job, name).unlink(missing_ok=True)
    return {**job, "docs": [d for d in job["docs"] if d["name"] != name]}


def read_passages(job: dict, name: str) -> list[dict]:
    path = passages_path(job, name)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
