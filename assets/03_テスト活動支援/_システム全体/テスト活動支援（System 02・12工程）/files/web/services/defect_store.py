"""不具合（バグ）のライフサイクル永続化。

検出した不具合を 1 ファイルにまとめて保存し、状態遷移を監査可能な形で追記する。

    output/<domain>/defects/defects.json   不具合の全件（1 ドメイン 1 ファイル）

状態は「新規 → 修正中 → 再テスト待ち → クローズ」の 4 段。
1 つ進む / 1 つ戻る以外の遷移は禁止する（飛び越しは実態と合わないため）。
状態を変えても履歴（history）は上書きせず追記する。誰がいつどこまで進めたかを残すため。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

STATES: tuple[str, ...] = ("new", "fixing", "retest", "closed")  # 新規 → 修正中 → 再テスト待ち → クローズ
STATE_LABELS: dict[str, str] = {
    "new": "新規",
    "fixing": "修正中",
    "retest": "再テスト待ち",
    "closed": "クローズ",
}

SEVERITIES: tuple[str, ...] = ("critical", "high", "medium", "low")
SEVERITY_LABELS: dict[str, str] = {
    "critical": "重大",
    "high": "高",
    "medium": "中",
    "low": "低",
}

_CLOSED = "closed"


# =========================================================================
# パス（ドメイン名は必ず検証してからパス要素にする）
# =========================================================================
def _safe_domain(domain: str) -> str:
    """ドメイン名をパス要素として使える形か検証する。不正なら ValueError。"""
    value = str(domain or "").strip()
    if not value:
        raise ValueError("ドメイン名が空です")
    if value in {".", ".."} or ".." in value:
        raise ValueError(f"ドメイン名に上位ディレクトリ指定は使えません: {domain}")
    if "/" in value or "\\" in value or "\x00" in value:
        raise ValueError(f"ドメイン名にパス区切り文字は使えません: {domain}")
    return value


def _defects_path(out_dir: Path, domain: str) -> Path:
    return Path(out_dir) / _safe_domain(domain) / "defects" / "defects.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# =========================================================================
# 入出力（壊れた JSON は例外にせず空一覧へフォールバックする）
# =========================================================================
def _normalize(raw: Mapping[str, Any]) -> dict[str, Any]:
    state = str(raw.get("state") or "")
    history = raw.get("history")
    return {
        "id": str(raw.get("id") or ""),
        "summary": str(raw.get("summary") or ""),
        "severity": str(raw.get("severity") or "medium"),
        "state": state if state in STATES else STATES[0],
        "case_id": str(raw.get("case_id") or ""),
        "detected_phase": str(raw.get("detected_phase") or ""),
        "injected_phase": str(raw.get("injected_phase") or ""),
        "odc_type": str(raw.get("odc_type") or ""),
        "created_at": str(raw.get("created_at") or ""),
        "updated_at": str(raw.get("updated_at") or ""),
        "history": [dict(h) for h in history if isinstance(h, dict)]
        if isinstance(history, list)
        else [],
    }


def list_defects(out_dir: Path, domain: str) -> list[dict[str, Any]]:
    """保存済みの不具合を作成順に返す。未作成・破損時は空リスト。"""
    path = _defects_path(out_dir, domain)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("defects") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return [_normalize(item) for item in items if isinstance(item, dict)]


def _write(out_dir: Path, domain: str, defects: list[dict[str, Any]]) -> None:
    path = _defects_path(out_dir, domain)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": _now(), "defects": defects}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# =========================================================================
# 作成
# =========================================================================
def _next_id(defects: list[dict[str, Any]]) -> str:
    seq = 1
    used = {d["id"] for d in defects}
    while f"DEF-{seq:04d}" in used:
        seq += 1
    return f"DEF-{seq:04d}"


def create_defect(
    out_dir: Path,
    domain: str,
    summary: str,
    severity: str,
    *,
    case_id: str = "",
    detected_phase: str = "",
    injected_phase: str = "",
    odc_type: str = "",
) -> dict[str, Any]:
    """不具合を 1 件登録する。初期状態は new。"""
    text = str(summary or "").strip()
    if not text:
        raise ValueError("不具合の概要（summary）は必須です")
    if severity not in SEVERITIES:
        raise ValueError(f"severity が不正です: {severity}（許可: {', '.join(SEVERITIES)}）")

    defects = list_defects(out_dir, domain)
    now = _now()
    defect: dict[str, Any] = {
        "id": _next_id(defects),
        "summary": text,
        "severity": severity,
        "state": STATES[0],
        "case_id": str(case_id or ""),
        "detected_phase": str(detected_phase or ""),
        "injected_phase": str(injected_phase or ""),
        "odc_type": str(odc_type or ""),
        "created_at": now,
        "updated_at": now,
        "history": [{"state": STATES[0], "at": now}],
    }
    _write(out_dir, domain, [*defects, defect])
    return defect


# =========================================================================
# 状態遷移
# =========================================================================
def can_transition(current: str, next_state: str) -> bool:
    """1 つ進む / 1 つ戻る場合のみ True。飛び越しと同一状態は False。"""
    if current not in STATES or next_state not in STATES:
        return False
    return abs(STATES.index(next_state) - STATES.index(current)) == 1


def update_state(out_dir: Path, domain: str, defect_id: str, next_state: str) -> dict[str, Any]:
    """状態を 1 段だけ動かす。不正な遷移は ValueError。既存 dict は書き換えない。"""
    if next_state not in STATES:
        raise ValueError(f"state が不正です: {next_state}（許可: {', '.join(STATES)}）")

    defects = list_defects(out_dir, domain)
    target = next((d for d in defects if d["id"] == defect_id), None)
    if target is None:
        raise ValueError(f"不具合が見つかりません: {defect_id}")
    if not can_transition(target["state"], next_state):
        raise ValueError(
            f"許可されない状態遷移です: {STATE_LABELS.get(target['state'], target['state'])}"
            f" → {STATE_LABELS.get(next_state, next_state)}（1 つ進む/戻るのみ可）"
        )

    now = _now()
    updated: dict[str, Any] = {
        **target,
        "state": next_state,
        "updated_at": now,
        "history": [*target["history"], {"state": next_state, "at": now}],
    }
    _write(out_dir, domain, [updated if d["id"] == defect_id else d for d in defects])
    return updated


# =========================================================================
# 集計
# =========================================================================
def stats(out_dir: Path, domain: str) -> dict[str, Any]:
    """状態別の件数と、未解決・重大未解決の件数を返す。"""
    defects = list_defects(out_dir, domain)
    by_state = {state: 0 for state in STATES}
    for defect in defects:
        by_state[defect["state"]] = by_state.get(defect["state"], 0) + 1
    closed = by_state[_CLOSED]
    return {
        "total": len(defects),
        "open": len(defects) - closed,
        "closed": closed,
        "by_state": by_state,
        "critical_open": sum(
            1 for d in defects if d["severity"] == "critical" and d["state"] != _CLOSED
        ),
    }
