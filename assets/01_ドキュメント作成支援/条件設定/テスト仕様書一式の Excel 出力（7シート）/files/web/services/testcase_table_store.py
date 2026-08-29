"""テストケース表の永続化（生成値・ユーザー編集・編集履歴）。

生成値とユーザー編集を分けて持つ。再クロールで生成値が変わっても編集は失われず、
どのセルを人が直したのかが常に判別できる。

    output/<domain>/testcases/edits.json    ユーザー編集（差分のみ）と手動追加行・削除行
    output/<domain>/testcases/history.jsonl 編集履歴（追記のみ・1行1操作）

履歴は追記専用。取り消しは履歴を削除せず、逆操作を新しい行として積む。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

# 表の列定義（UI の表示順・編集可否の唯一の情報源）
COLUMNS: tuple[dict[str, Any], ...] = (
    {"key": "case_id", "label": "ID", "editable": False, "kind": "text"},
    {"key": "name", "label": "テストケース名", "editable": True, "kind": "text"},
    {"key": "screen", "label": "画面", "editable": True, "kind": "enum"},
    {"key": "function", "label": "機能", "editable": True, "kind": "enum"},
    {"key": "viewpoint", "label": "観点", "editable": True, "kind": "enum"},
    {"key": "preconditions", "label": "前提条件", "editable": True, "kind": "list"},
    {"key": "steps", "label": "手順", "editable": True, "kind": "list"},
    {"key": "expected", "label": "期待結果", "editable": True, "kind": "list"},
    {"key": "automation", "label": "自動化判定", "editable": True, "kind": "enum"},
    {"key": "result", "label": "結果", "editable": False, "kind": "enum"},
)

_LIST_COLUMNS = {c["key"] for c in COLUMNS if c["kind"] == "list"}
_EDITABLE = {c["key"] for c in COLUMNS if c["editable"]}


class TestcaseStoreError(ValueError):
    """入力が不正で編集を適用できない場合に送出する。"""


# =========================================================================
# パス
# =========================================================================
def _base_dir(domain: str) -> Path:
    from web.services.qa.helpers import _output_dir

    return _output_dir() / domain / "testcases"


def _edits_path(domain: str) -> Path:
    return _base_dir(domain) / "edits.json"


def _history_path(domain: str) -> Path:
    return _base_dir(domain) / "history.jsonl"


def run_dir(domain: str) -> Path:
    """spec.ts と実行結果の置き場（テストケース表と同じ場所にまとめる）。"""
    return _base_dir(domain)


def _run_result_path(domain: str) -> Path:
    return _base_dir(domain) / "run_result.json"


def load_run_result(domain: str) -> dict[str, Any]:
    path = _run_result_path(domain)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_run_result(domain: str, result: Mapping[str, Any], ran_at: str) -> dict[str, Any]:
    """Playwright の実行結果を case_id 単位に畳んで保存する。

    テスト名の先頭が case_id（`TC-...`）なので、そこから対応付ける。
    """
    per_case: dict[str, Any] = {}
    for test in result.get("tests") or []:
        title = str(test.get("title") or "")
        case_id = title.split(" ", 1)[0]
        if not case_id.startswith("TC-"):
            continue
        per_case[case_id] = {
            "status": str(test.get("status") or ""),
            "duration_ms": int(test.get("duration_ms") or 0),
            "error": str(test.get("error") or "")[:2000],
        }
    payload = {
        "ran_at": ran_at,
        "summary": {
            "ok": bool(result.get("ok")),
            "passed": int(result.get("passed") or 0),
            "failed": int(result.get("failed") or 0),
            "skipped": int(result.get("skipped") or 0),
            "total": int(result.get("total") or 0),
            "duration_ms": int(result.get("duration_ms") or 0),
            "error": str(result.get("error") or ""),
        },
        "cases": per_case,
    }
    _write_json(_run_result_path(domain), payload)
    return payload


# =========================================================================
# 読み込み
# =========================================================================
def _empty_edits() -> dict[str, Any]:
    return {"overrides": {}, "manual": [], "deleted": []}


def load_edits(domain: str) -> dict[str, Any]:
    path = _edits_path(domain)
    if not path.is_file():
        return _empty_edits()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_edits()
    if not isinstance(data, dict):
        return _empty_edits()
    base = _empty_edits()
    base["overrides"] = data.get("overrides") if isinstance(data.get("overrides"), dict) else {}
    base["manual"] = data.get("manual") if isinstance(data.get("manual"), list) else []
    base["deleted"] = data.get("deleted") if isinstance(data.get("deleted"), list) else []
    return base


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def append_history(domain: str, entry: Mapping[str, Any]) -> dict[str, Any]:
    record = {"ts": datetime.now().isoformat(timespec="seconds"), **entry}
    path = _history_path(domain)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def load_history(domain: str, limit: int = 200) -> list[dict[str, Any]]:
    path = _history_path(domain)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    out.reverse()  # 新しい順
    return out


# =========================================================================
# 生成 + 編集の合成
# =========================================================================
def build_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """report からテストケース表の生成値を作る（編集は未適用）。"""
    from generator.test_design import build_test_design
    from generator.testcase_table import build_testcase_table

    # web.routes.qa_process 経由だと services -> routes の循環 import になるため、
    # 実体が移設された web.services.test_design_settings から直接 import する。
    from web.services.test_design_settings import _test_design_params, get_test_design_settings

    params = _test_design_params(get_test_design_settings())
    design = build_test_design(report, params)
    return [asdict(row) for row in build_testcase_table(report, design)]


def compose(domain: str, report: Mapping[str, Any]) -> dict[str, Any]:
    """生成値にユーザー編集を重ね、UI がそのまま描画できる形にして返す。"""
    edits = load_edits(domain)
    overrides: dict[str, Any] = edits["overrides"]
    deleted = set(str(x) for x in edits["deleted"])

    rows: list[dict[str, Any]] = []
    for row in build_rows(report):
        case_id = row["case_id"]
        if case_id in deleted:
            continue
        rows.append(_apply_override(row, overrides.get(case_id) or {}))
    for manual in edits["manual"]:
        if not isinstance(manual, dict):
            continue
        case_id = str(manual.get("case_id") or "")
        if not case_id or case_id in deleted:
            continue
        rows.append(_apply_override(_manual_row(manual), overrides.get(case_id) or {}))

    from generator.testcase_table import COMMON_PRECONDITIONS

    run = load_run_result(domain)
    cases = run.get("cases") or {}
    status_label = {"passed": "PASS", "failed": "FAIL", "timedOut": "TIMEOUT", "skipped": "SKIP"}
    for row in rows:
        entry = cases.get(row["case_id"])
        row["result"] = status_label.get(
            str((entry or {}).get("status")), "—" if entry is None else "?"
        )
        row["result_error"] = (entry or {}).get("error", "")

    return {
        "domain": domain,
        "run": {"ran_at": run.get("ran_at", ""), "summary": run.get("summary") or {}},
        "columns": [dict(c) for c in COLUMNS],
        "count": len(rows),
        "rows": rows,
        "common_preconditions": list(COMMON_PRECONDITIONS),
        "edited_cells": sum(len(v) for v in overrides.values()),
    }


def _apply_override(row: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(row)
    edited: list[str] = []
    for key, value in override.items():
        if key not in _EDITABLE:
            continue
        out[key] = list(value) if key in _LIST_COLUMNS and isinstance(value, list) else value
        edited.append(key)
    out["edited_columns"] = sorted(edited)
    return out


def _manual_row(manual: Mapping[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "case_id": str(manual.get("case_id") or ""),
        "name": str(manual.get("name") or ""),
        "screen": str(manual.get("screen") or ""),
        "function": str(manual.get("function") or ""),
        "viewpoint": str(manual.get("viewpoint") or ""),
        "preconditions": list(manual.get("preconditions") or []),
        "steps": list(manual.get("steps") or []),
        "expected": list(manual.get("expected") or []),
        "automation": str(manual.get("automation") or ""),
        "automation_reason": "手動追加のため未判定",
        "trace_id": "",
        "origin": "manual",
    }
    return row


# =========================================================================
# 更新
# =========================================================================
def _normalize(column: str, value: Any) -> Any:
    if column in _LIST_COLUMNS:
        if isinstance(value, list):
            return [str(v) for v in value]
        return [line for line in str(value).split("\n") if line.strip() != ""]
    return str(value)


def update_cell(
    domain: str, report: Mapping[str, Any], case_id: str, column: str, value: Any
) -> dict[str, Any]:
    """1 セルを更新し、履歴に前後値を残す。戻り値は更新後の行と履歴レコード。"""
    if column not in _EDITABLE:
        raise TestcaseStoreError(f"編集できない列です: {column}")
    current = compose(domain, report)
    target = next((r for r in current["rows"] if r["case_id"] == case_id), None)
    if target is None:
        raise TestcaseStoreError(f"テストケースが見つかりません: {case_id}")

    before = target.get(column)
    after = _normalize(column, value)
    if before == after:
        return {"row": target, "history": None, "changed": False}

    edits = load_edits(domain)
    overrides = edits["overrides"]
    # 生成値と同じ値に戻した場合は override を残さない。
    # 残すと値は元通りなのに「編集済み」の印だけが付き続ける（取り消し操作で発生）。
    generated = _generated_value(report, case_id, column)
    back_to_generated = generated is not None and generated == after
    if back_to_generated:
        cell = overrides.get(case_id) or {}
        cell.pop(column, None)
        if not cell:
            overrides.pop(case_id, None)
    else:
        overrides.setdefault(case_id, {})[column] = after
    _write_json(_edits_path(domain), edits)
    record = append_history(
        domain,
        {
            "action": "reset" if back_to_generated else "edit",
            "case_id": case_id,
            "column": column,
            "before": before,
            "after": after,
        },
    )
    updated = dict(target)
    updated[column] = after
    edited = set(updated.get("edited_columns") or [])
    if back_to_generated:
        edited.discard(column)
    else:
        edited.add(column)
    updated["edited_columns"] = sorted(edited)
    return {"row": updated, "history": record, "changed": True}


def _generated_value(report: Mapping[str, Any], case_id: str, column: str) -> Any:
    """編集を当てる前（生成そのまま）の値。手動追加行には生成値が無いので None。"""
    for row in build_rows(report):
        if row["case_id"] == case_id:
            return row.get(column)
    return None


def reset_cell(domain: str, report: Mapping[str, Any], case_id: str, column: str) -> dict[str, Any]:
    """1 セルを生成値へ戻す（履歴には reset として残す）。"""
    if column not in _EDITABLE:
        raise TestcaseStoreError(f"編集できない列です: {column}")
    edits = load_edits(domain)
    override = edits["overrides"].get(case_id) or {}
    if column not in override:
        raise TestcaseStoreError("この列は編集されていません")
    before = override.pop(column)
    if not override:
        edits["overrides"].pop(case_id, None)
    _write_json(_edits_path(domain), edits)
    composed = compose(domain, report)
    row = next((r for r in composed["rows"] if r["case_id"] == case_id), None)
    record = append_history(
        domain,
        {
            "action": "reset",
            "case_id": case_id,
            "column": column,
            "before": before,
            "after": (row or {}).get(column),
        },
    )
    return {"row": row, "history": record, "changed": True}


def add_row(domain: str, report: Mapping[str, Any], after_case_id: str = "") -> dict[str, Any]:
    """手動行を 1 件追加する（ID は MAN-nnn で採番）。"""
    edits = load_edits(domain)
    existing = [str(m.get("case_id") or "") for m in edits["manual"] if isinstance(m, dict)]
    seq = 1
    while f"TC-MAN-{seq:03d}" in existing:
        seq += 1
    case_id = f"TC-MAN-{seq:03d}"
    template = _manual_row({"case_id": case_id, "name": "（新規テストケース）"})
    edits["manual"].append(template)
    _write_json(_edits_path(domain), edits)
    record = append_history(
        domain, {"action": "add", "case_id": case_id, "column": "", "before": None, "after": None}
    )
    return {"row": template, "history": record, "after_case_id": after_case_id}


def delete_row(domain: str, case_id: str) -> dict[str, Any]:
    """行を削除する（生成行は非表示リストへ、手動行は実体を除去する）。"""
    edits = load_edits(domain)
    manual_ids = [str(m.get("case_id") or "") for m in edits["manual"] if isinstance(m, dict)]
    if case_id in manual_ids:
        edits["manual"] = [
            m for m in edits["manual"] if str((m or {}).get("case_id") or "") != case_id
        ]
    elif case_id not in edits["deleted"]:
        edits["deleted"].append(case_id)
    edits["overrides"].pop(case_id, None)
    _write_json(_edits_path(domain), edits)
    record = append_history(
        domain,
        {"action": "delete", "case_id": case_id, "column": "", "before": None, "after": None},
    )
    return {"case_id": case_id, "history": record}


def restore_row(domain: str, case_id: str) -> dict[str, Any]:
    """削除した生成行を戻す。"""
    edits = load_edits(domain)
    edits["deleted"] = [x for x in edits["deleted"] if str(x) != case_id]
    _write_json(_edits_path(domain), edits)
    record = append_history(
        domain,
        {"action": "restore", "case_id": case_id, "column": "", "before": None, "after": None},
    )
    return {"case_id": case_id, "history": record}
