"""AC: 段階承認の状態機械（未承認で生成不可・前段の変更で後段が stale・段階 4 はシニア QA）。"""
from __future__ import annotations

import pytest

from web.services.backendtest import stages, store

MEMBERS = {"sen": "senior_qa", "qa1": "qa"}


def _job():
    return {**store.new("月次", "batch", "system"), "members": dict(MEMBERS)}


def _gen_approve(job, n, artifact, actor="sen"):
    job = stages.put_generated(job, n, artifact, actor)
    return stages.approve(job, n, job["stages"][str(n)]["version"], None, actor)


def _through_3():
    job = _gen_approve(_job(), 1, {"purpose": "締めの検証", "scope": "orders"})
    job = _gen_approve(job, 2, {"facts": [{"id": "F001", "subject": "orders.amount"}], "questions": []})
    return stages.put_generated(job, 3, {"viewpoints": [{"id": "V01", "name": "境界値"}]}, "sen")


def test_cannot_generate_before_previous_stage_is_approved():
    """Given 段階 1 が生成済み・未承認 / When 段階 2 を生成 / Then 不可で理由が返る。"""
    job = stages.put_generated(_job(), 1, {"purpose": "目的", "scope": ""}, "qa1")
    ok, reason = stages.can_generate(job, 2)
    assert not ok and reason
    with pytest.raises(store.StoreError):
        stages.put_generated(job, 2, {"facts": [], "questions": []}, "qa1")


def test_approve_requires_current_version():
    """Given 版 1 の段階 1 / When 古い版番号で承認 / Then 拒否。"""
    job = stages.put_generated(_job(), 1, {"purpose": "目的", "scope": ""}, "qa1")
    with pytest.raises(store.StoreError):
        stages.approve(job, 1, 0, None, "qa1")
    assert job["stages"]["1"]["status"] == "generated"


def test_reject_marks_downstream_stale_and_blocks_generation():
    """Given 段階 1・2 承認、3 生成済み / When 段階 1 を差し戻す / Then 2・3 が stale になり 2 は生成できない。"""
    job = stages.reject(_through_3(), 1, "範囲が違う", {}, "sen")
    assert job["stages"]["2"]["stale"] and job["stages"]["3"]["stale"]
    assert not stages.can_generate(job, 2)[0]
    with pytest.raises(store.StoreError):
        stages.approve(job, 3, job["stages"]["3"]["version"], None, "sen")


def test_regenerating_approved_stage_becomes_proposal_and_adoption_stales_downstream():
    """Given 承認済みの段階 1 / When 再生成 / Then 成果物は壊さず提案になり、採用すると後段が stale。"""
    job = _through_3()
    proposed = stages.put_generated(job, 1, {"purpose": "別の目的", "scope": "orders"}, "sen")
    assert proposed["purpose"] == "締めの検証"
    assert proposed["stages"]["1"]["status"] == "approved"
    pid = proposed["stages"]["1"]["proposals"][0]["id"]
    adopted = stages.adopt_proposal(proposed, 1, pid, "sen")
    assert adopted["purpose"] == "別の目的"
    assert adopted["stages"]["1"]["status"] == "generated"
    assert adopted["stages"]["2"]["stale"] and adopted["stages"]["3"]["stale"]
    assert job["purpose"] == "締めの検証"  # 入力は変更しない


def _at_stage4():
    job = _gen_approve(_through_3(), 3, {"viewpoints": [{"id": "V01", "name": "境界値"}]})
    case = {"id": "C001", "oracle": {"method": "db_diff", "key": ["order_id"], "state": "auto"}}
    return stages.put_generated(job, 4, {"cases": [case]}, "sen")


def test_stage4_approval_requires_senior_qa_even_if_configured_qa():
    """Given 段階 4 の承認役割を qa に設定 / When qa が承認 / Then 拒否、シニア QA は承認できる。"""
    job = {**_at_stage4(), "approver_roles": {**store.DEFAULT_APPROVER_ROLES, "4": "qa"}}
    v = job["stages"]["4"]["version"]
    with pytest.raises(store.StoreError):
        stages.approve(job, 4, v, "qa", "qa1")
    approved = stages.approve(job, 4, v, None, "sen")
    assert approved["stages"]["4"]["status"] == "approved"
    assert approved["stages"]["4"]["approved_by"] == "sen"
    assert approved["audit"][-1]["action"] == "approve"


def test_stage4_blocks_cases_without_oracle_method():
    """Given 期待値方式が未設定のケース / When 段階 4 を承認 / Then 方式を選ぶよう求めて拒否。"""
    job = stages.put_generated({**_at_stage4()}, 4, {"cases": [{"id": "C001", "oracle": {}}]}, "sen")
    with pytest.raises(store.StoreError, match="期待値方式"):
        stages.approve(job, 4, job["stages"]["4"]["version"], None, "sen")


def test_case_expected_value_confirm_is_senior_only():
    """Given 段階 4 生成済み / When qa が期待値を確定 / Then 拒否、シニア QA は human で確定。"""
    job = _at_stage4()
    with pytest.raises(store.StoreError):
        stages.decide_item(job, 4, "C001", "confirm", {}, "", "qa1")
    done = stages.decide_item(job, 4, "C001", "confirm", {}, "", "sen")
    assert done["cases"][0]["oracle"]["state"] == "human"
