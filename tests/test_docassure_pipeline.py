"""パイプライン・API・真実規律の結合テスト（System06 Document Assurance）。"""
import json

import pytest

from web.services.docassure import pipeline

REQ = """# 認証
- REQ-001 ユーザーが5回連続して認証に失敗した場合、30分間アカウントをロックすること。
- REQ-002 検索結果は適切に高速に表示すること。
- REQ-003 セッションタイムアウトは30分とする。
"""
DES = """# セッション
- REQ-003 セッションのタイムアウトは20分とする。
- API expires_in は 900 秒。
"""


def _run():
    return pipeline.analyze([{"id": "REQ", "name": "要件", "type": "requirements", "text": REQ},
                             {"id": "DES", "name": "設計", "type": "basic_design", "text": DES}])


def test_pipeline_shape_and_no_errors():
    r = _run()
    assert not r["errors"], r["errors"]
    assert r["counts"]["requirements"] >= 3
    assert r["mode"] == "DETERMINISTIC_ONLY"
    json.dumps(r, ensure_ascii=False)  # JSON 化できる


def test_findings_have_evidence_and_candidate_status():
    r = _run()
    assert r["findings"], "曖昧語の指摘が出ること"
    for f in r["findings"]:
        assert f["location"]["document_id"] and f["location"]["snippet_hash"]
        assert f["status"] == "CANDIDATE" and f["source"] == "deterministic"


def test_conflict_unresolved_truth_unknown():
    r = _run()
    cs = [c for c in r["conflicts"] if c["kind"] == "numeric"]
    assert cs, "30分と20分の矛盾候補が出ること"
    assert all(c["status"] == "UNRESOLVED" and c["truth"] == "UNKNOWN" for c in cs)


def test_900s_vs_15min_is_not_conflict():
    r = pipeline.analyze([{"id": "A", "text": "- セッションの有効期限は15分とする。"},
                          {"id": "B", "text": "- セッションの有効期限は900秒とする。"}])
    assert not [c for c in r["conflicts"] if c["kind"] == "numeric"]


def test_empty_document_is_not_ready_nor_100():
    r = pipeline.analyze([{"id": "A", "text": ""}])
    assert r["readiness"]["state"] != "READY"
    assert all(s["value"] is None or s["value"] < 100 for s in r["scores"].values())


def test_zero_findings_never_scores_100_without_coverage():
    r = pipeline.analyze([{"id": "A", "text": "概要説明のみの文書です。"}])
    for s in r["scores"].values():
        assert s["value"] is None or s["coverage"] >= 0.5


def test_not_evaluated_not_pass():
    r = _run()
    for x in r["rule_results"]:
        assert x["result"] in ("PASS", "FAIL", "NOT_EVALUATED", "NOT_APPLICABLE")
