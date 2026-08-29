"""テスト活動の工程ゲート（どこまで進んだかの永続化）。

    output/<domain>/process/progress.json   完了した工程と、その時刻・実行者

工程は順番にしか進めない。前の工程が完了するまで次の工程は開けない。
「開いた」ではなく「人が完了を押した」を完了とする。開いただけで先へ進めると、
ゲートが素通りになり順序を守らせる意味が無くなるため。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ISO/IEC/IEEE 29119 の工程順。ここが順序の唯一の定義で、
# 画面側（ナビ・ステッパー・遷移ガード）はすべてこの並びを参照する。
PHASES: tuple[str, ...] = (
    "test-plan",
    "test-analysis",
    "test-strategy",
    "test-design",
    "test-implementation",
    "test-execution",
    "manual-execution",
    "defect-analysis",
    "code-fix",
    "test-completion",
)

PHASE_LABELS: dict[str, str] = {
    "test-plan": "テスト計画",
    "test-analysis": "テスト基本設計",
    "test-strategy": "テスト詳細設計",
    "test-design": "テストケース実装",
    "test-implementation": "自動テストケース実装",
    "test-execution": "自動テスト実行",
    "manual-execution": "手動テスト実行",
    "defect-analysis": "不具合分析",
    "code-fix": "コード修正提案",
    "test-completion": "テスト完了",
}


class ProcessGateError(ValueError):
    """工程ゲートの規則違反。利用者に見せてよい文言だけを持たせる。"""


def _safe_domain(domain: str) -> str:
    """ドメインをパス要素にする前に検証する。"""
    name = (domain or "").strip()
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise ProcessGateError("対象ドメインの指定が不正です")
    return name


def _path(out_dir: Path, domain: str) -> Path:
    return out_dir / _safe_domain(domain) / "process" / "progress.json"


def _load(out_dir: Path, domain: str) -> dict[str, Any]:
    path = _path(out_dir, domain)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"completed": {}}
    if not isinstance(data, dict) or not isinstance(data.get("completed"), dict):
        # 壊れていても利用者に 500 を見せない。未着手として扱う
        return {"completed": {}}
    return data


def _save(out_dir: Path, domain: str, data: dict[str, Any]) -> None:
    path = _path(out_dir, domain)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def unlocked_index(completed: dict[str, Any]) -> int:
    """開いてよい工程の最後の添字。

    完了済みが途中で途切れていたら、途切れた所で止める。
    後ろだけ完了印が付いていても、そこへは飛ばせない。
    """
    idx = 0
    for i, phase in enumerate(PHASES):
        if completed.get(phase):
            idx = i + 1
        else:
            break
    return min(idx, len(PHASES) - 1)


def status(out_dir: Path, domain: str) -> dict[str, Any]:
    """各工程の状態。画面はこれだけを見れば描ける。"""
    completed = _load(out_dir, domain).get("completed", {})
    unlocked = unlocked_index(completed)
    phases = []
    for i, phase in enumerate(PHASES):
        done = bool(completed.get(phase))
        phases.append(
            {
                "phase": phase,
                "label": PHASE_LABELS[phase],
                "order": i + 1,
                "completed": done,
                "completed_at": (completed.get(phase) or {}).get("at", "") if done else "",
                "unlocked": i <= unlocked,
                "current": i == unlocked and not done,
            }
        )
    return {
        "phases": phases,
        "unlocked_index": unlocked,
        "current_phase": PHASES[unlocked],
        "all_completed": all(completed.get(p) for p in PHASES),
    }


def can_enter(out_dir: Path, domain: str, phase: str) -> bool:
    if phase not in PHASES:
        return True  # 工程外の画面（連携設定・サポート等）は素通しする
    completed = _load(out_dir, domain).get("completed", {})
    return PHASES.index(phase) <= unlocked_index(completed)


def complete(out_dir: Path, domain: str, phase: str, *, by: str = "") -> dict[str, Any]:
    """工程を完了にする。飛ばして完了はできない。"""
    if phase not in PHASES:
        raise ProcessGateError("その工程は存在しません")
    data = _load(out_dir, domain)
    completed = dict(data.get("completed", {}))
    if PHASES.index(phase) > unlocked_index(completed):
        raise ProcessGateError(
            f"前の工程が完了していません（{PHASE_LABELS[PHASES[unlocked_index(completed)]]} が先です）"
        )
    completed[phase] = {"at": _now(), "by": by}
    _save(out_dir, domain, {**data, "completed": completed})
    return status(out_dir, domain)


def reopen(out_dir: Path, domain: str, phase: str) -> dict[str, Any]:
    """完了を取り消す。以降の工程の完了印もまとめて外す。

    途中の工程をやり直したのに後続が完了のままだと、
    完了印が実態を指さなくなるため。
    """
    if phase not in PHASES:
        raise ProcessGateError("その工程は存在しません")
    data = _load(out_dir, domain)
    completed = dict(data.get("completed", {}))
    for later in PHASES[PHASES.index(phase):]:
        completed.pop(later, None)
    _save(out_dir, domain, {**data, "completed": completed})
    return status(out_dir, domain)
