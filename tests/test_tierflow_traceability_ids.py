"""トレーサビリティ: ID の参照追跡・未定義参照・未カバー要件・種別推定・1 件注記（a1 / a2 / b5 / a10 / b9）。"""
from web.services.docverify.tierflow import links, rules, tiers


def _doc(doc_id, name, lines):
    ps = [{"id": f"P{i}", "text": t} for i, t in enumerate(lines, 1)]
    est = tiers.estimate(name, ps)
    return {"id": doc_id, "name": name, "tier": est["tier"], "passages": ps}


def _docs():
    req = _doc("A", "要件定義書.md", ["# 要件定義書", "## REQ-001 ログイン", "本文", "## REQ-002 ログアウト",
                                      "## REQ-003 検索", "UTF-8 で保存する"])
    des = _doc("B", "基本設計書.md", ["# 基本設計書", "## DES-001 ログイン画面", "REQ-001 を実現する",
                                      "## DES-002", "REQ-002 に対応"])
    tst = _doc("C", "テスト仕様書.md", ["# テスト仕様書", "## TC-001", "DES-001 / REQ-001 を確認", "## TC-003",
                                        "REQ-004 を確認"])
    return [req, des, tst]


def test_undefined_reference_is_high_finding_on_referring_doc():
    found = [f for f in rules.run(_docs()) if f["rule"] == "UNDEFINED_REF"]
    assert [(f["doc_id"], f["quote"], f["severity"]) for f in found] == [("C", "REQ-004", "high")]
    assert "定義が見つかりません" in found[0]["reason"]


def test_unknown_prefix_like_utf8_is_not_flagged():
    assert not [f for f in rules.run(_docs()) if f["quote"] == "UTF-8"]


def test_uncovered_requirement_is_mid_finding_on_defining_doc():
    found = [f for f in rules.run(_docs()) if f["rule"] == "UNCOVERED"]
    assert [(f["doc_id"], f["quote"], f["severity"]) for f in found] == [("A", "REQ-003", "mid")]


def test_uncovered_is_not_checked_with_single_doc():
    assert not [f for f in rules.run(_docs()[:1]) if f["rule"] == "UNCOVERED"]


def test_traces_edges_follow_id_references():
    edges = [e for e in links.build(_docs(), [], {})["edges"] if e["type"] == "traces"]
    pairs = {(e["from"], e["to"]): e for e in edges}
    assert set(pairs) == {("B", "A"), ("C", "B"), ("C", "A")}
    assert pairs[("B", "A")]["reason"] == "REQ-001、REQ-002 を参照"


def test_kind_distinguishes_requirement_design_test():
    kinds = [n["kind"] for n in links.build(_docs(), [], {})["nodes"]]
    assert kinds == ["requirement", "design", "test"]
    est = tiers.estimate("テスト仕様書.md", [{"id": "P1", "text": "# テスト仕様書"}])
    assert est["kind"] == "test" and "種別" in est["reason"] and est["tier"] == 3


def test_kind_from_heading_id_prefix():
    ps = [{"id": "P1", "text": "# 一覧"}, {"id": "P2", "text": "## TC-001 ログイン"}]
    assert tiers.estimate("a.md", ps)["kind"] == "test"


def test_single_document_note_without_changing_level():
    one = _docs()[:1]
    assert links.note(one) == links.SINGLE_DOC_NOTE
    assert links.build(one, [], {})["note"] == links.SINGLE_DOC_NOTE
    assert links.note(_docs()) is None
    assert links.conclude([], {}) == "pass"
