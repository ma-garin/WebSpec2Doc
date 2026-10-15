"""案件（job）の保存と読み出し。1 案件 = 1 フォルダ（job.json・資料・版・証跡）。

接続の秘密（パスワード・トークン）は job.json に書かない。保存時に検査して拒否する。
保存期間の掃除は一覧表示のたびに呼ぶ（定時実行・常駐はしない）。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from web import config
from web.tenancy import scoped_output_dir

_JID = re.compile(r"^[0-9a-f]{12}$")
_SUMMARY_EXCLUDE = ("facts", "questions", "viewpoints", "cases", "data_specs", "code",
                    "results", "defects", "llm_log", "audit", "files", "targets")

TARGET_KINDS = ("batch",)
LEVELS = ("integration_internal", "integration_external", "system", "acceptance")
FILE_KINDS = ("ddl", "jobdef", "spec", "source", "io", "golden", "other")
STAGE_NOS = tuple(str(n) for n in range(1, 9))
DEFAULT_APPROVER_ROLES = {"1": "qa", "2": "qa", "3": "qa", "4": "senior_qa",
                          "5": "qa", "6": "qa", "7": "qa", "8": "senior_qa"}
# 段階 n の版として退避する成果物（versions/<n>-v<k>.json）
STAGE_FIELDS = {
    1: ("purpose", "scope", "targets"), 2: ("facts", "questions"), 3: ("viewpoints",),
    4: ("cases",), 5: ("data_specs",), 6: ("code",), 7: ("runs",), 8: ("results", "defects"),
}
DEFAULT_RETENTION_DAYS = 90
MAX_VERSIONS = 10
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_FILES = 50
ACTIVE_RUN = ("queued", "running")
_SECRET_KEY = re.compile(r"pass(word|wd)?|secret|token|api_?key|credential|private_?key", re.I)


class StoreError(ValueError):
    """利用者に見せてよい理由を持つ失敗。"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _root() -> Path:
    return scoped_output_dir(config.DATA_DIR) / "backendtest"


def _check(jid: str) -> str:
    if not isinstance(jid, str) or not _JID.match(jid):
        raise KeyError(jid)
    return jid


def job_dir(jid: str) -> Path:
    return _root() / _check(jid)


def files_dir(jid: str) -> Path:
    return job_dir(jid) / "files"


def redacted_dir(jid: str) -> Path:
    return job_dir(jid) / "redacted"


def versions_dir(jid: str) -> Path:
    return job_dir(jid) / "versions"


def _new_stage() -> dict:
    return {"status": "draft", "version": 0, "stale": False, "approved_by_role": None,
            "approved_by": None, "approved_at": None, "reject_reason": None,
            "comments": {}, "proposals": []}


def new(name: str, target_kind: str, level: str, purpose: str = "", scope: str = "") -> dict:
    name = (name or "").strip()
    if not name:
        raise StoreError("案件名が空です。案件名を入れてから作成してください。")
    if target_kind not in TARGET_KINDS:
        raise StoreError("この対象の種類にはまだ対応していません。バッチジョブを選んでください。")
    if level not in LEVELS:
        raise StoreError("テストレベルが読めません。結合・システム・受け入れのどれかを選んでください。")
    ts = now()
    return {
        "id": uuid.uuid4().hex[:12], "name": name[:200], "purpose": purpose, "scope": scope,
        "target_kind": target_kind, "level": level, "created_at": ts, "updated_at": ts,
        "retention_days": DEFAULT_RETENTION_DAYS, "members": {},
        "approver_roles": dict(DEFAULT_APPROVER_ROLES),
        "llm": {"provider": "openai", "external_scope": "schema_spec"},
        "files": [], "targets": [], "envs": [], "current_env": None,
        "stages": {n: _new_stage() for n in STAGE_NOS},
        "facts": [], "questions": [], "viewpoints": [], "cases": [], "data_specs": [],
        "code": {"files": [], "map": {}, "summaries": {}, "gate": []},
        "runs": [], "results": [], "defects": [], "llm_log": [], "audit": [], "notices": [],
    }


def load(jid: str) -> dict:
    path = job_dir(jid) / "job.json"
    if not path.is_file():
        raise KeyError(jid)
    return json.loads(path.read_text(encoding="utf-8"))


def _secret_keys(value, path: str = "") -> list[str]:
    """dict のキー名から秘密情報らしき欄を探す（値は見ない）。"""
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            here = f"{path}.{key}" if path else str(key)
            if _SECRET_KEY.search(str(key)):
                found.append(here)
            found.extend(_secret_keys(child, here))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            found.extend(_secret_keys(child, f"{path}[{i}]"))
    return found


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def save(job: dict) -> dict:
    leaked = _secret_keys({"envs": job.get("envs") or [], "targets": job.get("targets") or []})
    if leaked:
        raise StoreError("接続のパスワードやトークンは保存できません。"
                         "実行のたびに入力してください。")
    job = {**job, "updated_at": now()}
    _write_json(job_dir(job["id"]) / "job.json", job)
    return job


def _active(job: dict) -> bool:
    return any(r.get("status") in ACTIVE_RUN for r in job.get("runs") or [])


def summary(job: dict) -> dict:
    stages = job.get("stages") or {}
    approved = sum(1 for s in stages.values() if s.get("status") == "approved")
    return {**{k: v for k, v in job.items() if k not in _SUMMARY_EXCLUDE},
            "file_count": len(job.get("files") or []),
            "case_count": len(job.get("cases") or []),
            "approved_stages": approved, "running": _active(job)}


def _iter_jobs():
    root = _root()
    if not root.is_dir():
        return
    for child in root.iterdir():
        if not _JID.match(child.name):
            continue
        try:
            yield load(child.name)
        except (KeyError, ValueError, OSError):
            continue


def list_all() -> list[dict]:
    purge_expired()
    items = [summary(job) for job in _iter_jobs()]
    return sorted(items, key=lambda x: x.get("updated_at", ""), reverse=True)


# ---- 資料の取り込み ----

def guess_kind(name: str) -> str:
    low = name.lower()
    suffix = Path(low).suffix
    if suffix in (".sql", ".ddl") or re.search(r"ddl|schema|スキーマ|テーブル定義", low):
        return "ddl"
    if re.search(r"expect|期待|正解|golden|ゴールデン", low):
        return "golden"
    if suffix in (".jil", ".job", ".yaml", ".yml") or re.search(r"jobdef|ジョブ定義|jobnet", low):
        return "jobdef"
    if suffix in (".xlsx", ".docx", ".md", ".pdf", ".txt") or re.search(r"仕様|spec|設計|readme", low):
        return "spec"
    if suffix in (".py", ".java", ".sh", ".bat", ".cmd", ".ps1", ".pl", ".rb", ".go", ".cs", ".js", ".ts"):
        return "source"
    if suffix in (".csv", ".tsv", ".dat", ".json", ".xml", ".fixed"):
        return "io"
    return "other"


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
    entry = {"name": name, "kind": guess_kind(name), "size": len(data),
             "added_at": now(), "redactions": []}
    return {**job, "files": others + [entry]}


def remove_file(job: dict, name: str) -> dict:
    if not any(f["name"] == name for f in job["files"]):
        raise KeyError(name)
    safe = safe_name(name)
    (files_dir(job["id"]) / safe).unlink(missing_ok=True)
    (redacted_dir(job["id"]) / safe).unlink(missing_ok=True)
    return {**job, "files": [f for f in job["files"] if f["name"] != name]}


def file_path(job: dict, name: str) -> Path:
    return files_dir(job["id"]) / safe_name(name)


# ---- 監査・版 ----

def _stage_key(stage) -> str:
    key = str(stage)
    if key not in STAGE_NOS:
        raise StoreError("段階の番号が読めません。1〜8 の段階を選び直してください。")
    return key


def audit(job: dict, action: str, stage: int | None, detail: str, actor: str) -> dict:
    version = None
    if stage is not None:
        version = (job.get("stages") or {}).get(_stage_key(stage), {}).get("version")
    entry = {"at": now(), "actor": actor or "", "action": action, "stage": stage,
             "version": version, "detail": detail or ""}
    return {**job, "audit": list(job.get("audit") or []) + [entry]}


def _version_path(jid: str, stage: int, version: int) -> Path:
    return versions_dir(jid) / f"{int(stage)}-v{int(version)}.json"


def save_version(job: dict, stage: int) -> None:
    """段階 stage の現在の版を versions/ へ退避する。各段階 直近 MAX_VERSIONS 版を残す。"""
    key = _stage_key(stage)
    n = int(key)
    state = (job.get("stages") or {}).get(key) or _new_stage()
    version = int(state.get("version") or 0)
    snapshot = {"stage": n, "version": version, "saved_at": now(), "state": state,
                "artifact": {f: job.get(f) for f in STAGE_FIELDS[n]}}
    _write_json(_version_path(job["id"], n, version), snapshot)
    _trim_versions(job["id"], n)


def _trim_versions(jid: str, stage: int) -> None:
    pattern = re.compile(rf"^{stage}-v(\d+)\.json$")
    found = []
    for path in versions_dir(jid).glob(f"{stage}-v*.json"):
        match = pattern.match(path.name)
        if match:
            found.append((int(match.group(1)), path))
    for _, path in sorted(found)[:-MAX_VERSIONS]:
        path.unlink(missing_ok=True)


def load_version(jid: str, stage: int, version: int) -> dict:
    n = int(_stage_key(stage))
    path = _version_path(jid, n, version)
    if not path.is_file():
        raise KeyError(f"{n}-v{version}")
    return json.loads(path.read_text(encoding="utf-8"))


# ---- 保存期間 ----

def _updated_date(job: dict) -> date | None:
    raw = job.get("updated_at") or job.get("created_at")
    try:
        return datetime.fromisoformat(raw).date()
    except (TypeError, ValueError):
        return None


def _expired(job: dict, today: date) -> bool:
    updated = _updated_date(job)
    if updated is None:
        return False
    days = max(1, int(job.get("retention_days") or DEFAULT_RETENTION_DAYS))
    return updated + timedelta(days=days) < today


def _log_purge(jid: str) -> None:
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    with (root / "purge.log").open("a", encoding="utf-8") as fh:
        fh.write(f"{now()}\t{jid}\n")


def delete(jid: str) -> None:
    """案件フォルダを消す。実行中なら StoreError。"""
    job = load(jid)
    if _active(job):
        raise StoreError("実行中の案件は削除できません。実行を止めてから削除してください。")
    shutil.rmtree(job_dir(jid))


def purge_expired(today: date | None = None) -> list[str]:
    """保存期間を過ぎた案件を消し、消した jid を返す。実行中の案件は残す。"""
    today = today or datetime.now(timezone.utc).date()
    removed = []
    for job in list(_iter_jobs()):
        if _active(job) or not _expired(job, today):
            continue
        shutil.rmtree(job_dir(job["id"]), ignore_errors=False)
        _log_purge(job["id"])
        removed.append(job["id"])
    return removed
