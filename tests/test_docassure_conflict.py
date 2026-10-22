"""矛盾候補検出・数量正規化・用語集のテスト。fixtures/docassure/conflict_*.md を使う。"""
import re
from pathlib import Path

import pytest

from web.services.docassure import conflict, glossary
from web.services.docassure.model import Location, RequirementUnit
from web.services.docassure.units import normalize_quantity

FIX = Path(__file__).parent / "fixtures" / "docassure"


def load(*names, as_dict=False):
    docs = {}
    for name in names:
        units = []
        for n, line in enumerate((FIX / f"conflict_{name}.md").read_text(encoding="utf-8").splitlines(), 1):
            m = re.match(r"- (\S+?):\s*(.*)", line)
            if not m:
                continue
            u = RequirementUnit(m.group(1), f"conflict_{name}.md",
                                Location(f"conflict_{name}.md", "", n, n, m.group(2)[:100], "h" + m.group(1)), m.group(2))
            units.append(u.to_dict() if as_dict else u)
        docs[f"conflict_{name}.md"] = units
    return docs


POSITIVE = ("numeric_a", "numeric_b", "permission", "temporal", "semantic")
TRAPS = ("trap_a", "trap_b")


@pytest.mark.parametrize("text,kind,canon", [
    ("900秒", "time", 900), ("15分", "time", 900), ("15 min", "time", 900), ("0.25時間", "time", 900),
    ("1,000件", "count", 1000), ("3回", "count", 3), ("30%", "percent", 30), ("１０分", "time", 600),
    ("十五分", "time", 900), ("1時間30分", "time", 5400), ("10MB", "size", 10 * 1024 ** 2),
    ("5万円", "money", 50000)])
def test_normalize_quantity(text, kind, canon):
    q = normalize_quantity(text)
    assert len(q) == 1 and q[0]["unit_kind"] == kind and q[0]["canonical_value"] == pytest.approx(canon)
    assert q[0]["raw"] and q[0]["span"]


def test_normalize_bound_and_date():
    assert normalize_quantity("8文字以上")[0]["bound"] == "ge"
    assert normalize_quantity("3秒以内")[0]["bound"] == "le"
    assert normalize_quantity("10月5日") == []


def by_kind(res, kind):
    return [c for c in res if c["kind"] == kind]


def test_numeric_detected_with_unit_conversion():
    res = conflict.detect(load(*POSITIVE))
    num = [c for c in by_kind(res, "numeric") if "セッション" in c["topic"]]
    assert len(num) == 1
    c = num[0]
    assert {e["canonical_value"] for e in c["evidence"]} == {1800.0, 1200.0, 900.0}
    assert c["status"] == "UNRESOLVED" and c["truth"] == "UNKNOWN" and c["question"].startswith("どちらが正しい")
    assert c["confidence_basis"] and 0 < c["confidence"] < 1
    # 同値のパスワード有効期限(90日×2)は矛盾にしない
    assert not [x for x in by_kind(res, "numeric") if "パスワード" in x["topic"]]
    for e in c["evidence"]:
        assert e["document_id"] and e["requirement_id"] and e["quote"] and e["location"]


def test_dict_input_equals_unit_input():
    a = conflict.detect(load(*POSITIVE))
    b = conflict.detect(load(*POSITIVE, as_dict=True))
    assert [x["conflict_id"] for x in a] == [x["conflict_id"] for x in b]


def test_permission_temporal_semantic_detected():
    res = conflict.detect(load(*POSITIVE))
    assert len(by_kind(res, "permission")) == 1
    assert len(by_kind(res, "temporal")) == 1
    sem = by_kind(res, "semantic_candidate")
    assert len(sem) == 1 and sem[0]["confidence"] <= 0.5


def test_traps_produce_no_conflicts():
    res = conflict.detect(load(*TRAPS))
    assert res == [], [(c["kind"], c["topic"]) for c in res]


@pytest.mark.parametrize("a,b", [
    ("リンク有効期限は900秒", "リンク有効期限は15分"),
    ("管理者のトークン有効期限は30分", "一般ユーザーのトークン有効期限は15分"),
    ("パスワードは12文字以下", "パスワード再設定の試行は3回までとする"),
    ("夜間の場合、処理時間は60分", "日中の場合、処理時間は30分"),
])
def test_individual_traps(a, b):
    docs = {"d1": [{"requirement_id": "A", "raw_text": a}], "d2": [{"requirement_id": "B", "raw_text": b}]}
    assert conflict.detect(docs) == []


def test_bound_difference_not_conflict():
    docs = {"d1": [{"requirement_id": "A", "raw_text": "パスワードは8文字以上とする。"}],
            "d2": [{"requirement_id": "B", "raw_text": "パスワードは12文字以下とする。"}]}
    assert conflict.detect(docs) == []


def test_precision_and_recall_combined():
    res = conflict.detect(load(*POSITIVE, *TRAPS))
    pos_docs = {f"conflict_{n}.md" for n in POSITIVE}
    for c in res:
        assert {e["document_id"] for e in c["evidence"]} <= pos_docs, c
    assert {c["kind"] for c in res} == {"numeric", "permission", "temporal", "semantic_candidate"}
    assert len([c for c in res if c["kind"] == "numeric"]) == 1  # precision: 誤検出なし


def test_hints_only_and_versions():
    docs = {"spec_v1.md": [{"requirement_id": "A", "raw_text": "ログインの有効期限は30分とする。"}],
            "spec_v2.md": [{"requirement_id": "B", "raw_text": "ログインの有効期限は20分とする。"}]}
    res = conflict.detect(docs)
    assert len(res) == 1 and res[0]["hints"]["newer_version"] == "spec_v2.md"
    assert res[0]["truth"] == "UNKNOWN" and res[0]["status"] == "UNRESOLVED"


def test_permission_non_exclusive_roles_ok():
    docs = {"d": [{"requirement_id": "A", "raw_text": "管理者は監査ログを閲覧可とする。"},
                  {"requirement_id": "B", "raw_text": "一般ユーザーは監査ログを閲覧可とする。"}]}
    assert conflict.detect(docs) == []
    docs["d"].append({"requirement_id": "C", "raw_text": "監査ログは一般ユーザーは閲覧不可とする。"})
    assert [c["kind"] for c in conflict.detect(docs)] == ["permission"]


def test_glossary():
    docs = {"d": [
        {"requirement_id": "G1", "raw_text": "「会員」とは、サービスに登録した個人を指す。", "document_id": "d"},
        {"requirement_id": "G2", "raw_text": "「会員」とは、課金契約を結んだ個人をいう。", "document_id": "d"},
        {"requirement_id": "R1", "raw_text": "顧客は注文できる。利用者は履歴を見られる。"},
        {"requirement_id": "R2", "raw_text": "ユーザーはワークスペースを作成する。ワークスペースを削除する。"},
    ]}
    g = glossary.build(docs)
    terms = {t["canonical"]: t for t in g["terms"]}
    assert terms["会員"]["status"] == "CANDIDATE" and terms["会員"]["source"]["document_id"] == "d"
    assert [m["term"] for m in g["multiple_definitions"]] == ["会員"]
    syn = g["synonym_candidates"][0]
    assert {"顧客", "利用者"} <= set(syn["candidates"]) and syn["status"] == "CANDIDATE" and "断定しない" in syn["note"]
    assert "ワークスペース" in {u["term"] for u in g["undefined_terms"]}
