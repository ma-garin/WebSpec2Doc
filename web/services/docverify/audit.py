"""監査ログ（System 06 R2。NFR-06-04・20・25）: 追記・絞り込み・CSV。

1 テナント 1 ファイル（``_audit.jsonl``）。1 行 = 1 操作。追記のみで書き換えない。
保持期間の既定は要確認-5（NFR-06-03）のため、本版は自動で消さない。
"""
from __future__ import annotations

import csv
import io
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from web import config
from web.tenancy import scoped_output_dir

ACTIONS = {
    "llm_send": "AI へ送信",
    "llm_send_failed": "AI へ送信（失敗）",
    "ai_adopt": "AI 提案を採用",
    "ai_reject": "AI 提案を不採用",
    "ai_question": "質問票へ送る",
    "llm_settings": "送信先の変更",
    "docassure_review": "品質保証の AI レビュー",
}
HEADER = ["日時", "利用者", "操作", "対象", "内容"]
_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")
_lock = threading.Lock()


def _path() -> Path:
    return scoped_output_dir(config.DATA_DIR) / "docverify" / "_audit.jsonl"


def append(action: str, user: str, target: str, detail: dict | None = None) -> dict:
    if action not in ACTIONS:
        raise ValueError(action)
    row = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "user": str(user),
           "action": action, "target": str(target), "detail": dict(detail or {})}
    path = _path()
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def read_all() -> list[dict]:
    path = _path()
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # 途中で切れた行は読み飛ばす（追記のみなので最後の 1 行に限られる）
    return rows


def query(since: str = "", until: str = "", user: str = "", action: str = "") -> list[dict]:
    """期間（YYYY-MM-DD。両端を含む）・利用者・操作で絞り込む。新しい順。"""
    out = []
    for r in read_all():
        day = str(r.get("at", ""))[:10]
        if (since and day < since) or (until and day > until):
            continue
        if (user and r.get("user") != user) or (action and r.get("action") != action):
            continue
        out.append(r)
    return sorted(out, key=lambda r: r.get("at", ""), reverse=True)


def count(action: str) -> int:
    return sum(1 for r in read_all() if r.get("action") == action)


def describe(r: dict) -> str:
    d = r.get("detail") or {}
    keys = ("provider", "model", "chars", "masked", "outcome", "destination", "question")
    return " ".join(f"{k}={d[k]}" for k in keys if k in d)


def _safe(v) -> str:
    s = "" if v is None else str(v)
    return "'" + s if s.startswith(_DANGEROUS) else s


def to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(HEADER)
    for r in rows:
        w.writerow([_safe(r.get("at")), _safe(r.get("user")), _safe(ACTIONS.get(r.get("action"), r.get("action"))),
                    _safe(r.get("target")), _safe(describe(r))])
    return "﻿" + buf.getvalue()
