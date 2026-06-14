"""technique_recommender のユニットテスト（テスト設計技法の推奨ロジック）。

report.json の screen 辞書を入力とし、ISTQB の 8 技法
（同値分割 / 境界値分析 / デシジョンテーブル / 状態遷移 / 分類木 /
ペアワイズ / ユースケース / 組み合わせ）の推奨・根拠・ケース雛形を返す。
"""

from __future__ import annotations

import json
from typing import Any

from analyzer.technique_recommender import (
    TECHNIQUE_KEYS,
    TechniqueRecommendation,
    recommend_techniques,
    techniques_for_screen,
)


def _field(**kw: Any) -> dict:
    base = {
        "name": "f",
        "field_type": "text",
        "required": False,
        "maxlength": None,
        "minlength": None,
        "min_value": "",
        "max_value": "",
        "pattern": "",
        "options": [],
    }
    base.update(kw)
    return base


def _screen(fields: list[dict] | None = None, *, to=None, frm=None, buttons=None) -> dict:
    return {
        "page_id": "P001",
        "title": "テスト画面",
        "url": "https://example.com/",
        "buttons": list(buttons or []),
        "forms": [{"action": "/submit", "method": "post", "fields": list(fields or [])}]
        if fields
        else [],
        "transitions": {"to": list(to or []), "from": list(frm or [])},
    }


def _keys(recs: tuple[TechniqueRecommendation, ...]) -> set[str]:
    return {r.key for r in recs}


def _by_key(recs: tuple[TechniqueRecommendation, ...], key: str) -> TechniqueRecommendation:
    return next(r for r in recs if r.key == key)


# ---- 基本: 空画面 ----


def test_empty_screen_recommends_nothing() -> None:
    recs = recommend_techniques(_screen())
    assert recs == ()


# ---- 同値分割 (ep) ----


def test_single_text_input_recommends_equivalence_partitioning() -> None:
    recs = recommend_techniques(_screen([_field(name="氏名", field_type="text")]))
    assert "ep" in _keys(recs)
    ep = _by_key(recs, "ep")
    assert ep.label == "同値分割"
    assert any("氏名" in r for r in ep.rationale)
    assert ep.case_stub  # ケース雛形が存在する


# ---- 境界値分析 (bva) ----


def test_maxlength_field_recommends_boundary_value_analysis() -> None:
    recs = recommend_techniques(_screen([_field(name="コメント", maxlength=100)]))
    bva = _by_key(recs, "bva")
    assert "maxlength=100" in " ".join(bva.rationale)
    assert "101" in bva.case_stub  # 上限+1 の異常値


def test_numeric_type_recommends_bva_even_without_explicit_bounds() -> None:
    # 改善: number/date/range は型由来の境界があるため min/max 未指定でも推奨する
    recs = recommend_techniques(_screen([_field(name="年齢", field_type="number")]))
    assert "bva" in _keys(recs)


# ---- デシジョンテーブル (dt) ----


def test_two_required_fields_recommend_decision_table() -> None:
    recs = recommend_techniques(
        _screen(
            [
                _field(name="ID", required=True),
                _field(name="PW", required=True),
            ]
        )
    )
    dt = _by_key(recs, "dt")
    assert "ID" in " ".join(dt.rationale) and "PW" in " ".join(dt.rationale)
    assert dt.case_stub  # 条件組み合わせの雛形


def test_single_required_field_does_not_recommend_decision_table() -> None:
    recs = recommend_techniques(_screen([_field(name="ID", required=True)]))
    assert "dt" not in _keys(recs)


# ---- 状態遷移テスト (st) — 新規ケース雛形 ----


def test_transitions_recommend_state_transition_with_stub() -> None:
    recs = recommend_techniques(_screen([_field(name="x")], to=["P002", "P003"]))
    st = _by_key(recs, "st")
    assert "P002" in " ".join(st.rationale)
    assert st.case_stub  # st のケース雛形が新たに生成される
    assert "P002" in st.case_stub


# ---- 分類木 (ct) — 新規ケース雛形 ----


def test_select_field_recommends_classification_tree_with_stub() -> None:
    recs = recommend_techniques(
        _screen([_field(name="区分", field_type="select", options=[{"value": "a"}, {"value": "b"}])])
    )
    ct = _by_key(recs, "ct")
    assert ct.case_stub
    assert "区分" in ct.case_stub


# ---- ペアワイズ (pw) ----


def test_four_fields_recommend_pairwise() -> None:
    recs = recommend_techniques(_screen([_field(name=f"f{i}") for i in range(4)]))
    assert "pw" in _keys(recs)


# ---- ユースケーステスト (uc) — 新規ケース雛形 ----


def test_form_with_transition_recommends_use_case_with_stub() -> None:
    recs = recommend_techniques(
        _screen([_field(name="x")], to=["P002"], buttons=["送信", "戻る"])
    )
    uc = _by_key(recs, "uc")
    assert uc.case_stub
    assert "P002" in uc.case_stub or "送信" in uc.case_stub


# ---- 組み合わせ (comb) ----


def test_two_option_fields_recommend_combination() -> None:
    recs = recommend_techniques(
        _screen(
            [
                _field(name="性別", field_type="radio", options=[{"value": "m"}, {"value": "f"}]),
                _field(
                    name="年代",
                    field_type="select",
                    options=[{"value": "10"}, {"value": "20"}, {"value": "30"}],
                ),
            ]
        )
    )
    comb = _by_key(recs, "comb")
    assert "6" in " ".join(comb.rationale)  # 2 x 3 = 6 パターン


# ---- メタ ----


def test_all_keys_are_known() -> None:
    recs = recommend_techniques(_screen([_field(name="x", maxlength=10)], to=["P002"]))
    assert _keys(recs).issubset(set(TECHNIQUE_KEYS))


def test_techniques_for_screen_is_json_serializable() -> None:
    payload = techniques_for_screen(_screen([_field(name="x", maxlength=10)], to=["P002"]))
    # report.json に埋め込めること
    dumped = json.dumps(payload, ensure_ascii=False)
    restored = json.loads(dumped)
    assert isinstance(restored, list)
    assert restored
    first = restored[0]
    assert {"key", "label", "abbr", "rationale", "case_stub"} <= set(first)
    assert isinstance(first["rationale"], list)


def test_recommendations_keep_canonical_technique_order() -> None:
    # マトリクス表示の列順を安定させるため、定義順で返す
    recs = recommend_techniques(
        _screen([_field(name="x", maxlength=10, required=True), _field(name="y", required=True)], to=["P002"])
    )
    keys = [r.key for r in recs]
    assert keys == [k for k in TECHNIQUE_KEYS if k in set(keys)]
