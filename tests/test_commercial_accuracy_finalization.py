"""Commercial Accuracy Finalization（2026-10-20）で直した挙動の単体テスト。"""
from __future__ import annotations

import pytest
from web.services.backendtest import oracle, stages
from web.services.backendtest.store import StoreError
from web.services.docverify import checks
from web.services.impact.engine import candidates, changes
from web.services.impact.engine.text import tokens


def _rules(text: str) -> set[str]:
    return {f["rule"] for f in checks.candidates([{"id": "p", "location": "t", "text": text}], apply_disabled=False)}


@pytest.mark.parametrize("text,rule", [
    ("申込の受付期間は未確定とする。", "REQ.INCOMPLETE"),
    ("通知の方法は今後決める。", "REQ.INCOMPLETE"),
    ("帳票はCSVおよび／またはPDFで出力する。", "REQ.AND_OR"),
    ("検索結果は素早く表示する。", "REQ.MEASURABILITY"),
    ("申請を受け付けるとともに、承認者へ通知する。", "REQ.MULTIPLE_REQUIREMENTS"),
])
def test_docverify_rules_detect(text, rule):
    assert rule in _rules(text)


def test_docverify_quoted_status_is_not_incomplete():
    assert "REQ.INCOMPLETE" not in _rules("状態が「未定」の申請は一覧の先頭に表示する。")


def test_docverify_means_and_one_requirement_is_single():
    assert "REQ.MULTIPLE_REQUIREMENTS" not in _rules("保存ボタンを押下し、確認画面を表示する。")


def test_impact_value_tokens_keep_unit_word():
    t = tokens("所定労働時間を1日8時間とする")
    assert "8時間" in t and "時間" in t and "1日" in t


def test_impact_old_value_is_a_must_term():
    ch = changes.from_text("一般会員の貸出上限を10冊から8冊に変更する。")[0]
    q = candidates.make_query(ch)
    assert "10冊" in q["must"] and "8冊" not in q["must"]


def test_backendtest_viewpoint_excluded_needs_reason():
    job = {"viewpoints": [{"id": "V1", "decision": "emit"}]}
    assert stages._decide_viewpoint(job, "V1", "excluded", None, "対象外", "a")["viewpoints"][0]["decision"] == "excluded"
    with pytest.raises(StoreError):
        stages._decide_viewpoint(job, "V1", "excluded", None, "", "a")


def test_backendtest_golden_without_file_is_not_ready():
    ok, why = oracle.method_ready({"method": "golden"})
    assert not ok and "期待値ファイル" in why
