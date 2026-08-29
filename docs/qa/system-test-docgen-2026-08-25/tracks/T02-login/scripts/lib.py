"""T02 共通ヘルパ。urllib のみ使用（外部依存なし）。秘密値マスク付き。"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8765"
MOCK = "http://127.0.0.1:9102"
DOMAIN = "127.0.0.1:9102"
LOGIN_URL = f"{MOCK}/login"
SECRET = "secret123"
EVID = Path(__file__).resolve().parent.parent / "evidence"
REPO = Path(__file__).resolve().parents[6]
OUT = REPO / "output" / DOMAIN  # repo/output/127.0.0.1:9102


def mask(s: str) -> str:
    if not isinstance(s, str):
        return s
    return s.replace(SECRET, "***MASKED***")


def post(path: str, form: dict, timeout: float = 90.0):
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(BASE + path, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return -1, f"EXC:{type(e).__name__}:{e}"


def get(path: str, timeout: float = 30.0):
    req = urllib.request.Request(BASE + path, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return -1, f"EXC:{type(e).__name__}:{e}"


def jparse(body: str):
    try:
        return json.loads(body)
    except Exception:  # noqa: BLE001
        return None


def save_evidence(name: str, obj) -> None:
    EVID.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, ensure_ascii=False, indent=2)
    txt = txt.replace(SECRET, "***MASKED***")
    (EVID / name).write_text(txt, encoding="utf-8")


def ls_l(path: Path) -> str:
    try:
        return subprocess.run(["ls", "-l", str(path)], capture_output=True, text=True).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"EXC:{e}"
