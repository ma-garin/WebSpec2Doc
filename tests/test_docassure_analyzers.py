"""Document Assurance 解析器（状態遷移・判定表・CRUD・NFR）のテスト。"""
from pathlib import Path

from web.services.docassure import crud_matrix, decision_table, nfr, state_transition as st
from web.services.docassure.requirement_engine import extract as req_extract

FX = Path(__file__).parent / "fixtures" / "docassure"


def _r(name):
    return (FX / name).read_text(encoding="utf-8")


def _kinds(g):
    return {f["kind"] for f in st.analyze(g)}


def test_state_sentences_extracted():
    g = st.extract(_r("an_state.md"))
    pairs = {(t["from"], t["to"]) for t in g["transitions"]}
    assert ("受付", "処理中") in pairs and ("処理中", "出荷済み") in pairs
    t = next(t for t in g["transitions"] if t["to"] == "出荷済み" and t["from"] == "処理中")
    assert t["event"].startswith("出荷") and "通知メール" in t["action"]
    assert g["initial"]["provenance"] == "INFERRED"


def test_state_table_extracted():
    g = st.extract(_r("an_state_table.md"))
    assert len(g["transitions"]) == 3
    assert g["transitions"][0]["event"] == "申請" and g["transitions"][0]["to"] == "承認待ち"


def test_state_analysis_detects():
    g = st.extract(_r("an_state.md"))
    kinds = _kinds(g)
    assert {"duplicate_transition", "undefined_state", "no_error_path", "dead_end"} <= kinds
    assert "unreachable_state" in kinds  # 孤立
    assert any(f["kind"] == "conflicting_transition" for f in st.analyze(g))


def test_state_conflict_and_error_path():
    g = st.extract(_r("an_state_table.md"))
    assert "conflicting_transition" not in _kinds(g)
    g2 = {"states": ["A", "B", "C"], "transitions": [
        {"from": "A", "event": "x", "to": "B", "guard": "", "action": "", "location": None},
        {"from": "A", "event": "x", "to": "C", "guard": "", "action": "", "location": None}],
        "initial": {"state": "A"}}
    assert "conflicting_transition" in _kinds(g2)


def test_state_trap_plain_sentence():
    g = st.extract("ユーザーは注文を登録する。システムは結果を表示する。\n状態を確認できる。")
    assert g["transitions"] == [] and st.analyze(g) == []


def test_state_accepts_units():
    units = req_extract("d", "決済が成功したとき、受付から処理中へ遷移する。")
    assert st.extract(units)["transitions"]


def test_decision_table_missing():
    ts = decision_table.extract(_r("an_decision.md"))
    assert len(ts) == 1
    t = ts[0]
    assert {c["name"] for c in t["conditions"]} == {"会員ランク", "購入額"}
    assert len(t["rules"]) == 3 and t["mode"] == "full"
    assert {"conditions", "actions", "rules", "missing"} <= t.keys()
    miss = [m["when"] for m in t["missing"]]
    assert {"会員ランク": "シルバー", "購入額": "10000円未満"} in miss
    assert all(m["provenance"] == "INFERRED" for m in t["missing"])


def test_decision_table_single_condition_trap():
    assert decision_table.extract(_r("an_single_cond.md")) == []


def test_decision_table_pairwise_over_limit():
    lines = []
    for i in range(1, 8):
        lines.append(f"条件{i}がAかつ条件{(i % 7) + 1}がBの場合、処理{i}を行う。")
    t = decision_table.extract("\n".join(lines))[0]
    assert t["combination_total"] > 64 and t["mode"] == "pairwise" and t["pairwise"]


def test_crud_matrix():
    m = crud_matrix.build(_r("an_crud.md"))
    e = {x["name"]: x for x in m["entities"]}
    assert e["注文"]["create"] and e["注文"]["read"] and e["注文"]["validation"] and e["注文"]["failure"]
    assert e["顧客"]["delete"] and e["顧客"]["audit"] and e["顧客"]["permission"]
    assert [b["id"] for b in m["business_rules"]] == ["BR-001"]
    assert "BR-001" not in e


def test_crud_trap_no_entity():
    assert crud_matrix.build("システムは安定して動作することが望ましい。")["entities"] == []


def test_nfr_classify():
    res = nfr.classify(_r("an_nfr.md"))
    by = {r["text"]: r for r in res}
    perf = by["検索の応答時間は3秒以内とする。"]
    assert "性能" in perf["categories"] and perf["measurable"] and perf["metric"].startswith("3")
    avail = by["システムは高い可用性を確保する。"]
    assert "可用性" in avail["categories"] and avail["measurable"] is False
    bk = by["データのバックアップは毎日取得し、7世代保持する。"]
    assert "バックアップ" in bk["categories"] and bk["measurable"]
    assert "セキュリティ" in by["通信はTLSで暗号化する。"]["categories"]
    assert "ユーザーを登録する。" not in by
    assert "25010" in res[0]["reference"] and "主張しない" in res[0]["reference"]
