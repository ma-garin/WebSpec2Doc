"""手動テスト実行の記録を JSONL へ追記・集計する。

1 実行 = 1 行の追記専用。あとから書き換えないことで「いつ・どのケースを・どう判定したか」
がそのまま残り、同じケースを何度試したかも辿れる。最新の判定だけが要る画面には
latest_by_case() が case_id 単位に畳んで返す。

    output/<domain>/manual_runs/records.jsonl   実行記録（追記専用・1行1記録）

壊れた行はその行だけ捨てて続行する。1 行の破損で全履歴が読めなくなる方が損失が大きい。
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: 受け付ける判定。UI のボタンと 1:1 で対応する。
RESULTS: tuple[str, ...] = ("passed", "failed", "blocked")

MAX_CASE_ID_LENGTH = 200
MAX_NOTE_LENGTH = 2000
MAX_EVIDENCE_LENGTH = 1000
MAX_READ_LIMIT = 5000

# 追記は 1 行・低頻度なので、ドメインごとにロックを作り分ける利益がない。
# プロセス内で 1 本にして、ロック辞書の管理をなくす。
_WRITE_LOCK = threading.Lock()

logger = logging.getLogger(__name__)


class ManualExecutionError(ValueError):
    """入力が不正で記録を追加できない場合に送出する。"""


# =========================================================================
# パス・整形
# =========================================================================
def _safe_domain(domain: str) -> str:
    """ドメイン名をパス要素として使う前に検証する（パストラバーサル防止）。"""
    from web.validation import _valid_domain

    name = (domain or "").strip()
    if not _valid_domain(name):
        raise ManualExecutionError(f"不正なドメイン名です: {domain!r}")
    return name


def _records_path(out_dir: Path, domain: str) -> Path:
    return Path(out_dir) / _safe_domain(domain) / "manual_runs" / "records.jsonl"


def _clip(value: Any, limit: int) -> str:
    return str(value if value is not None else "").strip()[:limit]


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """保存済み 1 行を既定形へ整える（欠損・型崩れは既定値で埋める）。"""
    result = str(raw.get("result") or "")
    return {
        "id": str(raw.get("id") or ""),
        "at": str(raw.get("at") or ""),
        "case_id": str(raw.get("case_id") or ""),
        "result": result if result in RESULTS else "",
        "note": str(raw.get("note") or ""),
        "evidence": str(raw.get("evidence") or ""),
    }


def _read_all(out_dir: Path, domain: str) -> list[dict[str, Any]]:
    """ファイル順（古い順）で全記録を返す。壊れた行は捨てる。"""
    path = _records_path(out_dir, domain)
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        logger.warning("手動実行記録を読み込めませんでした: %s", path)
        return []
    out: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            out.append(_normalize(data))
    return out


# =========================================================================
# 公開 API
# =========================================================================
def append_record(
    out_dir: Path,
    domain: str,
    case_id: str,
    result: str,
    note: str = "",
    evidence: str = "",
) -> dict[str, Any]:
    """1 件の実行結果を追記し、書き込んだ記録を返す。"""
    case = _clip(case_id, MAX_CASE_ID_LENGTH)
    if not case:
        raise ManualExecutionError("ケース ID が空です")
    verdict = _clip(result, 32)
    if verdict not in RESULTS:
        raise ManualExecutionError(f"判定は {'/'.join(RESULTS)} のいずれかです: {result!r}")

    record: dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "case_id": case,
        "result": verdict,
        "note": _clip(note, MAX_NOTE_LENGTH),
        "evidence": _clip(evidence, MAX_EVIDENCE_LENGTH),
    }
    path = _records_path(out_dir, domain)
    with _WRITE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def list_records(out_dir: Path, domain: str, limit: int = 500) -> list[dict[str, Any]]:
    """新しい順に最大 limit 件を返す。"""
    try:
        size = int(limit)
    except (TypeError, ValueError):
        size = 500
    size = max(1, min(size, MAX_READ_LIMIT))
    records = _read_all(out_dir, domain)
    return list(reversed(records[-size:]))


def latest_by_case(out_dir: Path, domain: str) -> dict[str, dict[str, Any]]:
    """ケース ID ごとの最新記録を返す（同じケースの再実行は後勝ち）。"""
    latest: dict[str, dict[str, Any]] = {}
    for record in _read_all(out_dir, domain):
        case = record["case_id"]
        if case:
            latest[case] = record
    return latest


def stats(out_dir: Path, domain: str, total_cases: int = 0) -> dict[str, Any]:
    """最新記録を集計する。total_cases は分母（0 なら実行済み件数を分母にする）。"""
    latest = latest_by_case(out_dir, domain)
    counts = {name: 0 for name in RESULTS}
    for record in latest.values():
        verdict = record["result"]
        if verdict in counts:
            counts[verdict] += 1
    done = len(latest)
    try:
        total = max(int(total_cases), 0) or done
    except (TypeError, ValueError):
        total = done
    return {
        "total": total,
        "done": done,
        "passed": counts["passed"],
        "failed": counts["failed"],
        "blocked": counts["blocked"],
        "rate": round(done / total, 3) if total else 0.0,
    }
