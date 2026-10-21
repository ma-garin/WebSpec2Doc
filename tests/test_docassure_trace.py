from web.services.docassure import coverage, semantic_diff, trace_graph, versioning
from web.services.docassure.requirement_engine import extract

DOC = """# 要件
## 3 ログイン
- REQ-001 ログインに5回失敗した場合、アカウントをロックする。
## 4 検索
- REQ-002 ユーザーは商品一覧画面で検索できる。
- REQ-003 POST /api/orders で注文を登録できる。
"""


def units(md=DOC, doc="D1"):
    return extract(doc, md)


def test_build_explicit_and_inferred_provenance():
    tests = [{"test_id": "T1", "title": "REQ-001 ロック確認"},
             {"test_id": "T2", "title": "ログインに5回失敗した場合アカウントをロックする確認"},
             {"test_id": "T9", "title": "全く無関係な天気"}]
    g = trace_graph.build({"D1": units()}, tests)
    ver = {(e["src"], e["dst"]): e for e in g["edges"] if e["kind"] == "verifies"}
    assert ver[("TEST:T1", "REQ:REQ-001")]["provenance"] == "EXPLICIT"
    e2 = ver[("TEST:T2", "REQ:REQ-001")]
    assert e2["provenance"] == "INFERRED" and 0 < e2["confidence"] < 1
    assert all(e["provenance"] in trace_graph.PROVENANCES for e in g["edges"])
    orph = {(o["node_id"], o["kind"]) for o in g["orphans"]}
    assert ("TEST:T9", "test_without_requirement") in orph
    assert ("REQ:REQ-002", "requirement_without_test") in orph
    assert ("REQ:REQ-001", "requirement_without_design") in orph
    assert ("REQ:REQ-002", "requirement_without_design") not in orph
    assert all(o["status"] == "CANDIDATE" for o in g["orphans"])
    assert {n["type"] for n in g["nodes"]} >= {"Document", "Section", "Requirement", "Screen", "API", "Test"}


def test_filters_and_neighborhood():
    d2 = extract("D2", "# 設計\n## 1 ロック\n- REQ-001 に基づきロック画面でアカウントを表示する。\n")
    g = trace_graph.build({"D1": units(), "D2": d2})
    only = trace_graph.filter_by_provenance(g, ["EXPLICIT"])
    assert all(e["provenance"] == "EXPLICIT" for e in only["edges"])
    n = trace_graph.neighborhood(g, "REQ:REQ-001", depth=1)
    assert any(x["id"] == "REQ:REQ-001" for x in n["nodes"])
    assert len(n["nodes"]) < len(g["nodes"])


def test_evidence_node():
    g = trace_graph.build({"D1": units()}, [{"test_id": "T1", "title": "REQ-001"}],
                          [{"evidence_id": "E1", "test_id": "T1"}])
    assert any(e["kind"] == "evidences" for e in g["edges"])


def test_coverage_test_design_is_not_execution():
    g = trace_graph.build({"D1": units()}, [{"test_id": "T1", "title": "REQ-001 確認"}])
    c = coverage.compute(g)
    assert c["test_designed"]["count"] == 1
    assert c["execution"] is None and c["passed"] is None and c["verified"] is None
    assert c["status"]["execution"] == "NOT_EVALUATED"
    c2 = coverage.compute(g, {"T1": "NOT_RUN"})
    assert c2["execution"]["count"] == 0 and c2["verified"]["count"] == 0


def test_coverage_with_results():
    tests = [{"test_id": "T1", "title": "REQ-001 確認"}, {"test_id": "T2", "title": "REQ-002 確認"}]
    g = trace_graph.build({"D1": units()}, tests)
    c = coverage.compute(g, {"T1": "PASS", "T2": {"status": "FAIL"}})
    assert c["execution"]["count"] == 2 and c["passed"]["count"] == 1 and c["verified"]["count"] == 1


def test_inferred_only_link_is_not_verified():
    g = trace_graph.build({"D1": units()}, [{"test_id": "T2", "title": "ログインに5回失敗した場合アカウントをロックする確認"}])
    c = coverage.compute(g, {"T2": "PASS"})
    assert c["passed"]["count"] == 1 and c["verified"]["count"] == 0


def test_diff_reorder_is_moved_not_modified():
    a = "# 要件\n## 1 A\n- REQ-001 ログインに5回失敗した場合、アカウントをロックする。\n- REQ-002 ユーザーは商品一覧画面で検索できる。\n"
    b = "# 要件\n## 1 A\n- REQ-002 ユーザーは商品一覧画面で検索できる。\n- REQ-001 ログインに5回失敗した場合、アカウントをロックする。\n"
    ch = semantic_diff.diff(units(a), units(b))
    assert ch and all(c["change"] == "MOVED" for c in ch)
    assert semantic_diff.diff(units(a), units(a)) == []


def test_diff_threshold_change():
    a = units("# 要件\n- REQ-001 ログインに5回失敗した場合、アカウントをロックする。\n- REQ-004 ロック解除は管理者がアカウントを操作する。\n")
    b = units("# 要件\n- REQ-001 ログインに10回失敗した場合、アカウントをロックする。\n- REQ-004 ロック解除は管理者がアカウントを操作する。\n")
    m = [c for c in semantic_diff.diff(a, b) if c["change"] == "MODIFIED"]
    assert len(m) == 1 and m[0]["change_type"] == "threshold_change"
    assert m[0]["before_value"] == "5回" and m[0]["after_value"] == "10回"
    assert m[0]["risk"] == "high" and m[0]["topic"] and "impacted_requirements" in m[0]


def test_diff_created_removed_split_merged():
    a = units("# 要件\n- REQ-001 ユーザーは商品を検索できる。\n- REQ-002 管理者は注文を削除できる。\n")
    b = units("# 要件\n- REQ-001 ユーザーは商品を検索できる。\n- REQ-009 管理者は在庫を更新できる。\n")
    kinds = {(c["change"], c["requirement_id"]) for c in semantic_diff.diff(a, b)}
    assert ("REMOVED", "REQ-002") in kinds and ("CREATED", "REQ-009") in kinds
    whole = [{"requirement_id": "R1", "document_id": "D", "raw_text": "管理者は注文を検索し削除できる", "fingerprint": "f0"}]
    parts = [{"requirement_id": "R1a", "document_id": "D", "raw_text": "管理者は注文を検索できる", "fingerprint": "f1", "parent_id": "R1"},
             {"requirement_id": "R1b", "document_id": "D", "raw_text": "管理者は注文を削除できる", "fingerprint": "f2", "parent_id": "R1"}]
    assert semantic_diff.diff(whole, parts)[0]["change"] == "SPLIT"
    assert semantic_diff.diff(parts, whole)[0]["change"] == "MERGED"


def test_versioning_history():
    v1 = units("# 要件\n- REQ-001 ログインに5回失敗した場合、アカウントをロックする。\n")
    v2 = units("# 要件\n- REQ-001 ログインに10回失敗した場合、アカウントをロックする。\n")
    h = versioning.history([{"version": "v1", "units": v1}, {"version": "v2", "units": v2}])
    assert [e["change"] for e in h["requirements"]["REQ-001"]] == ["CREATED", "MODIFIED"]
