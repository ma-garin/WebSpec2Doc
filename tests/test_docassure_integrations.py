from web.services.docassure import integrations as I
from web.services.docassure import rewrite as R


def U(rid, text, **f):
    return {"requirement_id": rid, "raw_text": text, "document_id": "d",
            "fields": {k: {"value": v, "provenance": "OBSERVED"} for k, v in f.items()}}


GOOD = U("REQ-1", "管理者は商品名を1文字以上100文字以下で登録できる。不正な入力はエラーを返す。")
VAGUE = U("REQ-2", "システムは高速に処理する。")


def test_candidates_positive_and_grounded():
    c = I.test_candidates([GOOD])
    kinds = {x["kind"] for x in c}
    assert {"happy", "boundary", "permission", "negative"} <= kinds
    assert "recovery" not in kinds and "state" not in kinds
    h = next(x for x in c if x["kind"] == "boundary")
    assert h["data"] and h["verification"] == "NOT_VERIFIED" and h["execution"] == "NOT_EXECUTED"
    assert h["state"] == "GENERATED" and h["steps"][0].startswith("Given")


def test_not_testable_makes_no_candidate():
    c = I.test_candidates([VAGUE])
    assert len(c) == 1 and c[0]["required_clarification"] and c[0]["candidate_id"] is None


def test_impact_payload():
    d = [{"change": "MODIFIED", "requirement_id": "R1", "change_type": "threshold_change",
          "before_value": "3秒", "after_value": "10秒", "risk": "high", "impacted_requirements": ["R2"]},
         {"change": "REMOVED", "requirement_id": "R3", "before": {"text": "x"}}]
    p = I.impact_payload(d, [])
    assert p["wired"] is False and p["removed"] == ["R3"]
    assert p["changes"][0]["threshold_change"] and p["changes"][0]["risk"] == "high"
    assert p["conflicts_hint"][0]["may_conflict_with"] == "R2"


def test_alignment_not_observed_is_not_defect():
    u = [U("R1", "利用者は「登録」ボタンで保存できる。")]
    obs = [{"kind": "button", "label": "登録", "url": "/a", "observed": True, "limitation": ""},
           {"kind": "button", "label": "削除", "url": "/a", "observed": False, "limitation": "ログイン壁"},
           {"kind": "route", "label": "承認", "url": "/b", "observed": False, "limitation": ""}]
    r = I.alignment(u, obs)
    assert r[0]["status"] == "ALIGNED_CANDIDATE" and r[0]["requirement_ids"] == ["R1"]
    assert r[1]["status"] == "NOT_OBSERVED" and r[1]["limitation"] == "ログイン壁" and not r[1]["is_defect"]
    assert r[2]["status"] == "NOT_OBSERVED" and r[2]["limitation"]
    assert all(x["wired"] is False for x in r)


def test_rewrite_placeholders_not_values():
    p = R.propose(VAGUE)
    assert p["status"] == "PROPOSAL" and "未承認" in p["note"] and p["original"] == VAGUE["raw_text"]
    assert p["structured"]["threshold"]["value"] == "<要確認: 閾値>"
    assert p["structured"]["threshold"]["provenance"] == "INFERRED"
    assert p["structured"]["expected"]["value"].startswith("<要確認")
    assert set(p["fix_levels"]) == {"minimal", "recommended", "strict"}
    assert not any(ch.isdigit() for ch in p["proposal"]["then"])


def test_rewrite_keeps_observed():
    p = R.propose(U("R9", "x", actor="管理者", action="登録する", expected_result="一覧に表示する"))
    assert p["structured"]["actor"] == {"value": "管理者", "provenance": "OBSERVED"}
