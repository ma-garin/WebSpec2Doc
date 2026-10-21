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


def test_single_document_consistency_not_scored_and_traceability_not_fake_100():
    r = pipeline.analyze([{"id": "A", "text": "- REQ-001 検索は適切に表示すること。\n- REQ-002 結果を保存すること。\n"}])
    assert r["scores"]["Consistency"]["value"] is None          # 比較していないのに満点にしない（H-4）
    assert r["scores"]["Traceability"]["value"] is None
    assert r["readiness"]["state"] != "READY"


def test_traceability_zero_links_is_not_100():
    r = pipeline.analyze([{"id": "A", "text": "- REQ-001 検索は表示すること。\n"},
                          {"id": "B", "text": "- 無関係な説明文です。\n"}])
    v = r["scores"]["Traceability"]["value"]
    assert v is None or v < 100                                   # contains だけでは「つながり」と数えない（H-1）


def test_human_decision_applied_and_waiver_expiry():
    docs = [{"id": "R", "text": "- REQ-003 セッションタイムアウトは30分とする。\n"},
            {"id": "D", "text": "- REQ-003 セッションのタイムアウトは20分とする。\n"}]
    base = pipeline.analyze(docs)
    cid = base["conflicts"][0]["conflict_id"]
    dec = [{"target": cid, "decision": "conflict_decided", "reason": "設計を正とする", "source": "human", "by": "u"}]
    r = pipeline.analyze(docs, decisions=dec)
    c = [x for x in r["conflicts"] if x["conflict_id"] == cid][0]
    assert c["status"] == "DECIDED" and c["truth"] == "UNKNOWN"   # 人の決定は記録。事実の証明にしない
    assert r["scores"]["Consistency"]["value"] > base["scores"]["Consistency"]["value"]
    fid = base["findings"][0]["finding_id"] if base["findings"] else None
    if fid:
        exp = pipeline.analyze(docs, decisions=[{"target": fid, "decision": "waived", "expiry": "2020-01-01",
                                                  "reason": "x", "source": "human"}])
        f = [x for x in exp["findings"] if x["finding_id"] == fid][0]
        assert f["status"] == "CANDIDATE" and f.get("waiver_expired")


def test_unchanged_document_is_not_reanalyzed_and_metrics_have_no_text():
    docs = [{"id": "CACHE-A", "text": "- REQ-901 検索は適切に表示すること。\n"}]
    first = pipeline.analyze(docs)
    second = pipeline.analyze(docs)
    assert second["metrics"]["cache_hits"] >= 1 and second["metrics"]["cache_misses"] == 0
    assert first["findings"] == second["findings"]            # キャッシュで結果が変わらない
    assert "検索" not in str(second["metrics"])
    changed = pipeline.analyze([{"id": "CACHE-A", "text": "- REQ-901 検索は3秒以内に表示すること。\n"}])
    assert changed["metrics"]["cache_misses"] == 1


def test_pack_findings_reduce_their_dimension_and_clarity_is_evaluated():
    r = pipeline.analyze([{"id": "A", "text": "- REQ-001 検索は適切に表示すること。\n- REQ-002 保存は速やかに行うこと。\n"},
                          {"id": "B", "text": "- REQ-001 検索画面で表示する。\n"}])
    c = r["scores"]["Clarity"]
    assert c["value"] is not None and c["value"] < 100      # 曖昧語の指摘が Clarity を下げる（評価不能のままにしない）
