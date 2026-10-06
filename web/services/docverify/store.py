"""検査（inspection）の保存と読み出し。1 検査 = 1 JSON。"""
from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from web import config
from web.tenancy import scoped_output_dir

_IID = re.compile(r"^[0-9a-f]{12}$")
_SUMMARY_EXCLUDE = ("passages", "findings")


def _root() -> Path:
    return scoped_output_dir(config.DATA_DIR) / "docverify"


def _check_iid(iid: str) -> str:
    if not isinstance(iid, str) or not _IID.match(iid):
        raise KeyError(iid)
    return iid


def doc_dir(iid: str) -> Path:
    return _root() / _check_iid(iid)


def _path(iid: str) -> Path:
    return doc_dir(iid) / "inspection.json"


def new(name: str) -> dict:
    return {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "planning",
        "goal": "",
        "exit_criteria": {"max_open_critical": 0, "max_open_major": 5},
        "phase": "plan",
        "participants": [],
        "due": None,
        "checklist_id": None,
        "checks": {},
        "approval": {"approver": None, "decided_at": None},
        "document": None,
        "passages": [],
        "findings": [],
        "versions": [],
        "diff": None,
    }


def load(iid: str) -> dict:
    path = _path(iid)
    if not path.is_file():
        raise KeyError(iid)
    return upgrade(json.loads(path.read_text(encoding="utf-8")))


_PHASE_FROM_STATUS = {"planning": "plan", "reviewing": "individual", "fixing": "rework", "closed": "closed"}


def upgrade_finding(f: dict) -> dict:
    """v1 の指摘を v2 の形に読み替える（元の dict は変えない）。"""
    from web.services.docverify.settings import normalize_severity
    return {"checklist_item": None, "disposition": None, **f,
            "raised_by": f.get("raised_by") or ("自動候補" if f.get("origin", "auto") == "auto" else "ゲスト"),
            "severity": normalize_severity(f.get("severity"))}


def upgrade(insp: dict) -> dict:
    """v1 の検査を v2 の形に読み替える。warning→major、info→minor。"""
    ec = dict(insp.get("exit_criteria") or {})
    if "max_open_major" not in ec:
        ec["max_open_major"] = ec.get("max_open_warning", 5)
    ec.pop("max_open_warning", None)
    ec.setdefault("max_open_critical", 0)
    return {
        "phase": _PHASE_FROM_STATUS.get(insp.get("status"), "plan"),
        "participants": [], "due": None, "checklist_id": None, "checks": {},
        **insp,
        "approval": {"approver": None, "decided_at": None, **(insp.get("approval") or {})},
        "exit_criteria": ec,
        "findings": [upgrade_finding(f) for f in insp.get("findings") or []],
    }


def save(insp: dict) -> None:
    directory = doc_dir(insp["id"])
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(insp, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, directory / "inspection.json")
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def list_all() -> list[dict]:
    root = _root()
    if not root.is_dir():
        return []
    items = []
    for child in root.iterdir():
        if not _IID.match(child.name):
            continue
        try:
            insp = load(child.name)
        except (KeyError, ValueError, OSError):
            continue
        items.append({k: v for k, v in insp.items() if k not in _SUMMARY_EXCLUDE})
    return sorted(items, key=lambda x: x.get("created_at", ""), reverse=True)
