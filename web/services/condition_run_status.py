"""画面別設計の条件に、テスト実行結果を突き合わせる（P2-5）。

「設計したが検証していない」を画面上で区別するための材料を作る。

対応付けは condition_id（＝テストケースの trace_id）で行う。
テストケース側は generator/testcase_table.py が既に安定 ID を振っているため、
テストケース表のデータ構造は変えていない。規則は
web/services/screen_test_design.condition_id() に書いてある。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# 条件行に出すバッジ。「対応なし」を「未実行」に混ぜないのが要点で、
# 実行し忘れなのか、そもそも紐付くケースが無いのかを区別できるようにする。
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_NOT_RUN = "not_run"
STATUS_NO_CASE = "no_case"

_FAILED_RESULTS = frozenset({"failed", "timedOut", "interrupted"})


def _cases_by_trace(rows: list[Mapping[str, Any]]) -> dict[str, list[str]]:
    """trace_id → case_id 群。trace_id を持たない行は対象外。"""
    index: dict[str, list[str]] = {}
    for row in rows:
        trace_id = str(row.get("trace_id") or "")
        case_id = str(row.get("case_id") or "")
        if trace_id and case_id:
            index.setdefault(trace_id, []).append(case_id)
    return index


def _status_for(case_ids: list[str], results: Mapping[str, Any]) -> tuple[str, dict[str, int]]:
    """紐づくケース群の実行結果を 1 つの状態に畳む。

    1 件でも失敗していれば「失敗」にする。成功件数で薄めると、
    落ちている事実が画面から消える。
    """
    if not case_ids:
        return STATUS_NO_CASE, {"total": 0, "passed": 0, "failed": 0, "not_run": 0}
    counts = {"total": len(case_ids), "passed": 0, "failed": 0, "not_run": 0}
    for case_id in case_ids:
        result = results.get(case_id)
        if not isinstance(result, Mapping):
            counts["not_run"] += 1
            continue
        status = str(result.get("status") or "")
        if status in _FAILED_RESULTS:
            counts["failed"] += 1
        elif status == "passed":
            counts["passed"] += 1
        else:
            counts["not_run"] += 1
    if counts["failed"]:
        return STATUS_FAILED, counts
    if counts["passed"] and not counts["not_run"]:
        return STATUS_PASSED, counts
    return STATUS_NOT_RUN, counts


def attach_run_status(
    conditions: list[dict[str, Any]],
    rows: list[Mapping[str, Any]],
    run_result: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """各条件に run_status（と内訳）を足した新しいリストを返す。

    引数は変更しない（呼び出し元が元データを再利用できるようにする）。
    """
    index = _cases_by_trace(rows)
    results = run_result.get("cases") or {}
    if not isinstance(results, Mapping):
        results = {}
    attached: list[dict[str, Any]] = []
    for cond in conditions:
        case_ids = index.get(str(cond.get("condition_id") or ""), [])
        status, counts = _status_for(case_ids, results)
        attached.append(dict(cond, run_status=status, run_counts=counts))
    return attached
