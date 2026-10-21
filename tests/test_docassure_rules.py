"""決定論ルールの precision/recall。fixture の行末 HIT/OK が期待値（HIT のみが指摘される）。"""
from pathlib import Path

import pytest

from web.services.docassure.model import (CANDIDATE, DETERMINISTIC, FAIL, NOT_APPLICABLE,
                                          NOT_EVALUATED, PASS, finding_dict_valid)
from web.services.docassure.rules import load_pack, run_rules

FX = Path(__file__).parent / "fixtures" / "docassure"
OTHER = {
    "basic.md": "## 別紙C 帳票\n| SCR-07 | 一覧 |\n",
    "design.md": "設計では REQ-001 と REQ-003 を実現する。\n",
}
CASES = {  # fixture 名 -> (rule_id, other_docs)
    "ambiguity": ("AMB-001", None), "tbd": ("TBD-001", None), "placeholder": ("PLH-001", None),
    "broken_ref": ("REF-001", OTHER), "id_duplicate": ("ID-001", None), "id_gap": ("ID-002", None),
    "id_format": ("ID-003", None), "id_orphan": ("ID-004", {"design.md": "設計では REQ-001 を実現する。\n"}),
    "term_variance": ("TERM-001", None), "number_unit": ("NUM-001", None), "number_range": ("NUM-002", None),
}


def _marks(md: str, tag: str) -> set[int]:
    return {i for i, ln in enumerate(md.splitlines(), 1) if f"<!-- {tag} -->" in ln}


@pytest.mark.parametrize("name", sorted(CASES))
def test_fixture_precision_recall(name):
    rule_id, other = CASES[name]
    md = (FX / f"rules_{name}.md").read_text(encoding="utf-8")
    out = run_rules("DOC-1", md, [], other_docs=other)
    got = {f.location.line_start for f in out["findings"] if f.rule_id == rule_id}
    assert got == _marks(md, "HIT"), f"{name}: 指摘行 {sorted(got)}"
    assert len(_marks(md, "HIT")) >= 3
    res = next(r for r in out["results"] if r["rule_id"] == rule_id)
    assert res["result"] == FAIL and res["checked"] > 0


def test_findings_have_evidence_and_candidate_status():
    md = (FX / "rules_ambiguity.md").read_text(encoding="utf-8")
    fs = run_rules("DOC-1", md, [])["findings"]
    assert fs
    for f in fs:
        assert finding_dict_valid(f.to_dict())
        assert f.source == DETERMINISTIC and f.status == CANDIDATE and f.result == FAIL
        assert f.location.line_start > 0 and f.location.snippet and f.location.snippet_hash
        assert f.how_to_fix and f.why_matters and 0 < f.confidence <= 1


def test_zero_findings_is_pass_with_checked_count_not_bare():
    out = run_rules("D", "# 概要\n応答時間は3秒以内とする。\n", [])
    amb = next(r for r in out["results"] if r["rule_id"] == "AMB-001")
    assert amb["result"] == PASS and amb["checked"] >= 1 and "検査" in amb["reason"]


def test_not_evaluated_when_nothing_to_check():
    out = run_rules("D", "# 概要\nログインできる。\n", [])
    res = {r["rule_id"]: r for r in out["results"]}
    for rid in ("REF-001", "ID-001", "ID-002", "ID-003", "ID-004", "NUM-001", "NUM-002", "REQ-ITEMS"):
        assert res[rid]["result"] == NOT_EVALUATED and res[rid]["reason"], rid
    assert all(r["result"] != PASS for r in out["results"] if r["rule_id"] in res and r["checked"] == 0)


def test_empty_document_is_all_not_evaluated():
    out = run_rules("D", "   \n\n", [])
    assert not out["findings"]
    assert {r["result"] for r in out["results"]} == {NOT_EVALUATED}


def test_orphan_not_evaluated_without_other_docs():
    out = run_rules("D", "| REQ-001 | A |\n| REQ-002 | B |\n", [])
    assert next(r for r in out["results"] if r["rule_id"] == "ID-004")["result"] == NOT_EVALUATED


def test_section_ref_unresolvable_without_numbered_sections():
    out = run_rules("D", "# 概要\n詳細は 3.2 参照。\n", [])
    assert next(r for r in out["results"] if r["rule_id"] == "REF-001")["result"] == NOT_EVALUATED


def test_extra_terms_and_required_items_and_disable():
    pack = load_pack("default", {"ambiguous_terms": ["いい感じに"], "required_items": ["エラー時", ["権限", "認可"]],
                                 "disabled_rules": ["TBD-001"]})
    assert "いい感じに" not in str(load_pack()["params"]["ambiguous_terms"])  # 元 pack は汚染されない
    out = run_rules("D", "# 要件\nいい感じに表示する。\n未定。\n", [], pack=pack)
    res = {r["rule_id"]: r for r in out["results"]}
    assert any(f.rule_id == "AMB-001" and "いい感じに" in f.reason for f in out["findings"])
    assert res["TBD-001"]["result"] == NOT_APPLICABLE
    assert not any(f.rule_id == "TBD-001" for f in out["findings"])
    missing = [f.reason for f in out["findings"] if f.rule_id == "REQ-ITEMS"]
    assert len(missing) == 2 and res["REQ-ITEMS"]["result"] == FAIL


def test_profile_mismatch_is_not_applicable():
    pack = load_pack("default", {"profile": "other"})
    out = run_rules("D", "# a\n適切に処理する。\n", [], pack=pack)
    assert {r["result"] for r in out["results"]} == {NOT_APPLICABLE}


def test_term_group_defined_distinctly_is_not_flagged():
    md = "顧客とは契約者を指す。\n利用者とは画面の操作者を指す。\n"
    out = run_rules("D", md, [])
    assert not [f for f in out["findings"] if f.rule_id == "TERM-001"]
    f = run_rules("D", "顧客が買う。\n利用者が見る。\n", [])["findings"]
    t = [x for x in f if x.rule_id == "TERM-001"][0]
    assert t.status == CANDIDATE and t.counter_evidence and "同義" in t.counter_evidence[0]


def test_requirement_id_linked_from_units():
    from web.services.docassure.model import Location, RequirementUnit
    u = RequirementUnit("REQ-009", "D", Location("D", line_start=2, line_end=2), "x")
    out = run_rules("D", "# a\n適宜対応する。\n", [u])
    f = next(f for f in out["findings"] if f.rule_id == "AMB-001")
    assert f.requirement_id == "REQ-009" and f.finding_id.startswith("AMB-001:REQ-009")


def test_load_pack_rejects_bad_name():
    with pytest.raises(ValueError):
        load_pack("../x")
    d = load_pack()
    for r in d["rules"]:
        for k in ("rule_id", "name", "description", "severity", "scope", "detector", "enabled", "profile", "version", "why", "how_to_fix"):
            assert k in r
