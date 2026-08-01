"""条件 ⇄ テスト実行結果の突き合わせ（P2-5）。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from web.services.condition_run_status import (
    STATUS_FAILED,
    STATUS_NO_CASE,
    STATUS_NOT_RUN,
    STATUS_PASSED,
    attach_run_status,
)
from web.services.screen_test_design import condition_id


class TestConditionId:
    """条件側の ID は generator/testcase_table.py の trace_id と同じ規則であること。

    ここがずれると、条件行の結果が「対応なし」に落ちるか、別のケースの結果を
    表示してしまう。テストケース側の trace_id は
    src/generator/testcase_table.py の trace_id=... 各行が正。
    """

    def test_input_field_matches_bva_trace_id(self) -> None:
        cond = {"source_kind": "入力項目", "source_name": "email"}
        assert condition_id("P001", cond) == "P001:email"

    def test_link_uses_transition_trace_id(self) -> None:
        cond = {"source_kind": "リンク", "source_name": "商品一覧", "trace_target": "P003"}
        assert condition_id("P001", cond) == "P001->P003"

    def test_decision_table_matches_dt_trace_id(self) -> None:
        cond = {"source_kind": "フォーム", "technique": "デシジョンテーブル"}
        assert condition_id("P001", cond) == "P001:DT"

    def test_pairwise_matches_pw_trace_id(self) -> None:
        cond = {"source_kind": "フォーム", "technique": "ペアワイズ"}
        assert condition_id("P001", cond) == "P001:PW"

    def test_block_technique_without_testcases_has_no_id(self) -> None:
        """直交表・分類ツリー法等はテストケース行を生まない。

        既存 ID に寄せると「検証済み」と誤表示するため、空 ID にして
        「対応なし」に落とす。
        """
        for technique in ("直交表", "分類ツリー法", "原因結果グラフ", "エラー推測"):
            cond = {"source_kind": "フォーム", "technique": technique}
            assert condition_id("P001", cond) == "", technique

    def test_display_falls_back_to_page_id(self) -> None:
        cond = {"source_kind": "見出し", "source_name": "ご注文内容", "technique": "表示確認"}
        assert condition_id("P001", cond) == "P001"

    def test_empty_page_id_yields_empty(self) -> None:
        assert condition_id("", {"source_kind": "入力項目", "source_name": "email"}) == ""


def _cond(condition_id_value: str) -> dict:
    return {"condition": "x", "condition_id": condition_id_value}


class TestAttachRunStatus:
    def test_no_matching_case_is_no_case(self) -> None:
        got = attach_run_status([_cond("P001:email")], [], {})
        assert got[0]["run_status"] == STATUS_NO_CASE

    def test_matching_case_never_run_is_not_run(self) -> None:
        rows = [{"case_id": "TC-1", "trace_id": "P001:email"}]
        got = attach_run_status([_cond("P001:email")], rows, {"cases": {}})
        assert got[0]["run_status"] == STATUS_NOT_RUN

    def test_all_passed_is_passed(self) -> None:
        rows = [
            {"case_id": "TC-1", "trace_id": "P001:email"},
            {"case_id": "TC-2", "trace_id": "P001:email"},
        ]
        run = {"cases": {"TC-1": {"status": "passed"}, "TC-2": {"status": "passed"}}}
        got = attach_run_status([_cond("P001:email")], rows, run)
        assert got[0]["run_status"] == STATUS_PASSED
        assert got[0]["run_counts"] == {"total": 2, "passed": 2, "failed": 0, "not_run": 0}

    def test_one_failure_makes_the_condition_failed(self) -> None:
        """1 件でも落ちていれば失敗にする。成功件数で薄めない。"""
        rows = [
            {"case_id": "TC-1", "trace_id": "P001:email"},
            {"case_id": "TC-2", "trace_id": "P001:email"},
        ]
        run = {"cases": {"TC-1": {"status": "passed"}, "TC-2": {"status": "failed"}}}
        got = attach_run_status([_cond("P001:email")], rows, run)
        assert got[0]["run_status"] == STATUS_FAILED

    def test_timeout_counts_as_failure(self) -> None:
        rows = [{"case_id": "TC-1", "trace_id": "P001:email"}]
        run = {"cases": {"TC-1": {"status": "timedOut"}}}
        got = attach_run_status([_cond("P001:email")], rows, run)
        assert got[0]["run_status"] == STATUS_FAILED

    def test_partially_run_is_not_run(self) -> None:
        """一部しか流していないものを「検証済み」と言わない。"""
        rows = [
            {"case_id": "TC-1", "trace_id": "P001:email"},
            {"case_id": "TC-2", "trace_id": "P001:email"},
        ]
        run = {"cases": {"TC-1": {"status": "passed"}}}
        got = attach_run_status([_cond("P001:email")], rows, run)
        assert got[0]["run_status"] == STATUS_NOT_RUN

    def test_rows_without_trace_id_are_ignored(self) -> None:
        rows = [{"case_id": "TC-1", "trace_id": ""}]
        got = attach_run_status([_cond("P001:email")], rows, {"cases": {}})
        assert got[0]["run_status"] == STATUS_NO_CASE

    def test_input_is_not_mutated(self) -> None:
        conds = [_cond("P001:email")]
        attach_run_status(conds, [], {})
        assert "run_status" not in conds[0]

    def test_broken_run_result_does_not_raise(self) -> None:
        rows = [{"case_id": "TC-1", "trace_id": "P001:email"}]
        got = attach_run_status([_cond("P001:email")], rows, {"cases": "not-a-dict"})
        assert got[0]["run_status"] == STATUS_NOT_RUN
