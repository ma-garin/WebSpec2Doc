"""AC: 差分・許容差・期待値の自動確定の範囲・未判定は合格に数えない・終了コード≠0 は不合格。"""
from __future__ import annotations

import pytest

from web.services.backendtest import diffing, judge, oracle, results, store

BEFORE = [{"order_id": 1, "amount": 100.0, "updated_at": "t0"}, {"order_id": 2, "amount": 5, "updated_at": "t0"}]


def test_diff_detects_added_removed_updated():
    after = [{"order_id": 1, "amount": 120.0, "updated_at": "t0"}, {"order_id": 3, "amount": 9, "updated_at": "t0"}]
    d = diffing.diff(BEFORE, after, ["order_id"])
    assert len(d["added"]) == 1 and len(d["removed"]) == 1
    assert d["updated"][0]["cols"]["amount"] == [100.0, 120.0]


def test_diff_tolerance_and_exclude_columns():
    """Given 許容差 0.01 の金額と除外列の更新日時 / When 比べる / Then 範囲内と除外列は差分にしない。"""
    after = [{"order_id": 1, "amount": 100.004, "updated_at": "t1"}, {"order_id": 2, "amount": 5, "updated_at": "t1"}]
    d = diffing.diff(BEFORE, after, ["order_id"], exclude=["updated_at"], tolerance={"amount": 0.01})
    assert d["updated"] == [] and d["added"] == [] and d["removed"] == []
    strict = diffing.diff(BEFORE, after, ["order_id"], exclude=["updated_at"])
    assert [u["key"] for u in strict["updated"]] and "amount" in strict["updated"][0]["cols"]


def test_diff_duplicate_key_is_indeterminate():
    dup = BEFORE + [{"order_id": 2, "amount": 6, "updated_at": "t0"}]
    assert diffing.diff(dup, dup, ["order_id"])["indeterminate"] > 0


def test_auto_confirm_only_for_machine_checkable_expectations():
    """Given 前後比較のみ / 件数式付き / When 設定 / Then 前者は auto、業務判断を含む後者は unconfirmed。"""
    case = {"id": "C001", "oracle": {"method": "db_diff"}}
    assert oracle.configure_db_diff(case, ["order_id"])["oracle"]["state"] == "auto"
    counted = oracle.configure_db_diff(case, ["order_id"], count_formula="after = before + 3")
    assert counted["oracle"]["state"] == "unconfirmed"
    assert oracle.can_confirm(counted, "qa")[0] is False
    assert oracle.can_confirm(counted, "senior_qa")[0] is True
    assert oracle.can_confirm(counted, "sen", {"sen": "senior_qa"})[0] is True
    assert case["oracle"] == {"method": "db_diff"}  # 入力は変更しない


def test_expected_value_based_only_on_source_cannot_be_confirmed():
    """Given 根拠がソースの事実だけ / When シニア QA が確定 / Then 拒否（振る舞いから期待値を作らない）。"""
    case = oracle.configure_db_diff({"id": "C1", "basis": ["F1"], "oracle": {"method": "db_diff"}},
                                    ["order_id"], count_formula="after = 10")
    ok, reason = oracle.can_confirm(case, "senior_qa", facts=[{"id": "F1", "origin": "source"}])
    assert ok is False and "根拠" in reason


def test_evaluate_unconfirmed_is_undetermined_and_auto_compares():
    """Given 未確定の期待値 / When 判定 / Then 未判定。auto なら差分 0 で合格・差分ありで不合格。"""
    auto = oracle.configure_db_diff({"id": "C1", "oracle": {"method": "db_diff"}}, ["order_id"])
    unconf = oracle.configure_db_diff({"id": "C2", "oracle": {"method": "db_diff"}}, ["order_id"], count_formula="after = 2")
    assert oracle.evaluate(unconf, {"before": BEFORE, "after": BEFORE})["verdict"] == oracle.UNDETERMINED
    assert oracle.evaluate(auto, {"before": BEFORE, "after": BEFORE})["verdict"] == oracle.PASS
    assert oracle.evaluate(auto, {"before": BEFORE, "after": BEFORE[:1]})["verdict"] == oracle.FAIL
    assert oracle.evaluate(auto, {})["verdict"] == oracle.UNDETERMINED


def test_undetermined_and_unknown_states_are_not_counted_as_pass():
    """Given 合格 1・未判定 1・未知の状態 1 / When 集計 / Then 未検証 2 件で保留、合格にしない。"""
    s = judge.summarize([{"state": "pass"}, {"state": "undetermined"}, {"state": "weird"}])
    assert s["pass"] == 1 and s["unverified"] == 2 and s["total"] == 3
    assert judge.verdict(s)["verdict"].startswith("保留")
    assert judge.verdict(judge.summarize([]))["verdict"] != "合格"
    assert judge.verdict(judge.summarize([{"state": "pass"}, {"state": "fail"}]))["verdict"] == "不合格"
    assert judge.verdict(judge.summarize([{"state": "pass"}]))["verdict"] == "合格"


def test_nonzero_exit_code_is_fail_even_if_test_passed(data_dir):
    """Given テストコードは pass だが対象の終了コード 3 / When 結果を作る / Then 不合格で終了コードを理由に出す。"""
    job = store.save(store.new("月次", "batch", "system"))
    ev = store.job_dir(job["id"]) / "runs" / "r1" / "C001"
    ev.mkdir(parents=True)
    case = oracle.configure_db_diff({"id": "C001", "oracle": {"method": "db_diff"}}, ["order_id"])
    row = {"case": "C001", "state": "pass", "facts": {"rc": [3], "evidence": str(ev)}}
    rec = results._record(job["id"], "r1", row, case)
    assert rec["state"] == "fail" and rec["auto"]["rule"] == "exit_code"
    assert rec["fact"]["rc"] == 3 and "3" in rec["cause"]
    ok_row = {**row, "facts": {"rc": [0], "evidence": str(ev)}}
    assert results._record(job["id"], "r1", ok_row, case)["state"] != "fail"


@pytest.mark.parametrize("state", ["not_run", "error", "cancelled"])
def test_unrun_rows_stay_unverified(data_dir, state):
    job = store.save(store.new("月次", "batch", "system"))
    case = oracle.configure_db_diff({"id": "C001", "oracle": {"method": "db_diff"}}, ["order_id"])
    rec = results._record(job["id"], "r1", {"case": "C001", "state": state, "facts": {}}, case)
    assert rec["state"] == state
    assert judge.summarize([rec])["unverified"] == 1
