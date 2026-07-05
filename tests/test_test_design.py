"""src/generator/test_design.py（MBT テスト設計エンジン）のユニットテスト。"""

from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from generator.test_design import (  # noqa: E501
    EVIDENCE_CATALOG,
    EVIDENCE_MEASURED,
    SUPPORTED_TECHNIQUES,
    build_test_design,
    load_params_from_file,
)
from generator.test_design import TestDesignParams as DesignParams


# ---- テストフィクスチャ生成ヘルパ ----
def _field(name: str, field_type: str = "text", **kw: object) -> dict:
    base = {
        "name": name,
        "field_type": field_type,
        "required": False,
        "maxlength": None,
        "minlength": None,
        "min_value": None,
        "max_value": None,
        "pattern": None,
        "options": [],
    }
    base.update(kw)
    return base


def _screen(page_id: str, *, fields: list[dict] | None = None, to: list[str] | None = None) -> dict:
    forms = [{"action": "/submit", "method": "post", "fields": fields}] if fields else []
    return {
        "page_id": page_id,
        "title": f"画面 {page_id}",
        "buttons": [],
        "forms": forms,
        "transitions": {"to": to or [], "from": []},
    }


def _report(screens: list[dict]) -> dict:
    return {"screens": screens}


CATALOG = {
    "email": [
        {"label": "上限値", "value": "a@b.com", "note": ""},
        {"label": "上限値+1", "value": "aa@b.com", "note": ""},
        {"label": "空白", "value": "", "note": ""},
        {"label": "RFC違反", "value": "x", "note": ""},
        {"label": "未登録", "value": "y@z.com", "note": ""},
    ],
}


# =========================================================================
# パラメータ正規化
# =========================================================================
class TestParamsNormalization:
    def test_defaults_enable_all_supported(self) -> None:
        p = DesignParams()
        assert set(p.enabled_techniques) == set(SUPPORTED_TECHNIQUES)

    def test_pairwise_strength_clamped_to_two_or_three(self) -> None:
        assert DesignParams(pairwise_strength=5).pairwise_strength == 3
        assert DesignParams(pairwise_strength=1).pairwise_strength == 2

    def test_n_switch_clamped(self) -> None:
        assert DesignParams(n_switch=9).n_switch == 1
        assert DesignParams(n_switch=-3).n_switch == 0

    def test_unknown_technique_dropped(self) -> None:
        p = DesignParams(enabled_techniques=("bva", "bogus"))
        assert p.enabled_techniques == ("bva",)

    def test_is_frozen(self) -> None:
        p = DesignParams()
        try:
            p.bva_offset = 5  # type: ignore[misc]
        except Exception as exc:  # noqa: BLE001
            assert "FrozenInstance" in type(exc).__name__ or "frozen" in str(exc).lower()
        else:
            raise AssertionError("frozen dataclass should reject mutation")


# =========================================================================
# 空・非対象
# =========================================================================
class TestEmpty:
    def test_no_screens_yields_empty(self) -> None:
        design = build_test_design(_report([]), DesignParams())
        assert design.screens == ()

    def test_screen_without_forms_or_transitions_is_skipped(self) -> None:
        report = _report([_screen("P001")])
        design = build_test_design(report, DesignParams())
        assert design.screens == ()

    def test_missing_screens_key_is_safe(self) -> None:
        design = build_test_design({}, DesignParams())
        assert design.screens == ()


# =========================================================================
# 境界値分析（BVA）
# =========================================================================
class TestBva:
    def test_maxlength_generates_on_and_off_point(self) -> None:
        report = _report([_screen("P1", fields=[_field("comment", maxlength=100)])])
        design = build_test_design(report, DesignParams(enabled_techniques=("bva",)))
        cases = design.screens[0].bva[0].cases
        labels = {c.label for c in cases}
        assert "上限ちょうど" in labels and "上限超過" in labels
        on = next(c for c in cases if c.label == "上限ちょうど")
        off = next(c for c in cases if c.label == "上限超過")
        assert on.expected == "有効" and off.expected == "無効"
        assert on.confidence == EVIDENCE_MEASURED
        assert off.value == "101文字"  # offset=1 → 100+1

    def test_bva_offset_respected(self) -> None:
        report = _report([_screen("P1", fields=[_field("n", "number", max_value=10)])])
        design = build_test_design(report, DesignParams(enabled_techniques=("bva",), bva_offset=5))
        off = next(c for c in design.screens[0].bva[0].cases if c.label == "最大超過")
        assert off.value == "15"

    def test_min_max_numeric_boundaries(self) -> None:
        report = _report([_screen("P1", fields=[_field("q", "number", min_value=1, max_value=99)])])
        design = build_test_design(report, DesignParams(enabled_techniques=("bva",)))
        labels = {c.label for c in design.screens[0].bva[0].cases}
        assert {"最小ちょうど", "最小未満", "最大ちょうど", "最大超過"} <= labels

    def test_email_uses_catalog_with_lower_confidence(self) -> None:
        report = _report([_screen("P1", fields=[_field("mail", "email")])])
        params = DesignParams(enabled_techniques=("bva",), value_catalog=CATALOG)
        design = build_test_design(report, params)
        cases = design.screens[0].bva[0].cases
        assert cases, "email はカタログからケースが出るはず"
        assert all(c.confidence == EVIDENCE_CATALOG for c in cases)
        assert next(c for c in cases if c.label == "上限値+1").expected == "無効"
        assert next(c for c in cases if c.label == "上限値").expected == "有効"

    def test_field_without_constraints_yields_no_bva(self) -> None:
        report = _report([_screen("P1", fields=[_field("free", "text")], to=["P2"])])
        design = build_test_design(report, DesignParams(enabled_techniques=("bva",)))
        # 制約なし text は BVA 対象外 → bva 空
        assert design.screens == () or design.screens[0].bva == ()


# =========================================================================
# デシジョンテーブル
# =========================================================================
class TestDecisionTable:
    def test_two_required_fields_yield_four_rules(self) -> None:
        fields = [_field("a", required=True), _field("b", required=True)]
        design = build_test_design(
            _report([_screen("P1", fields=fields)]),
            DesignParams(enabled_techniques=("dt",)),
        )
        dt = design.screens[0].decision_table
        assert dt is not None
        assert len(dt.rules) == 4  # 2^2
        all_true = next(r for r in dt.rules if all(r.conditions))
        assert all_true.action == "送信成功"

    def test_single_required_field_no_table(self) -> None:
        fields = [_field("a", required=True), _field("b", required=False)]
        design = build_test_design(
            _report([_screen("P1", fields=fields)]),
            DesignParams(enabled_techniques=("dt",)),
        )
        assert design.screens == () or design.screens[0].decision_table is None

    def test_max_conditions_caps_table_size(self) -> None:
        fields = [_field(f"f{i}", required=True) for i in range(6)]
        design = build_test_design(
            _report([_screen("P1", fields=fields)]),
            DesignParams(enabled_techniques=("dt",), max_dt_conditions=3),
        )
        dt = design.screens[0].decision_table
        assert dt is not None
        assert len(dt.conditions) == 3
        assert len(dt.rules) == 8  # 2^3


# =========================================================================
# ペアワイズ
# =========================================================================
def _covers_all_pairs(params, rows, strength: int) -> bool:
    domains = [p.values for p in params]
    for idxs in combinations(range(len(domains)), strength):
        from itertools import product as _p

        for values in _p(*(domains[i] for i in idxs)):
            found = any(
                all(row[i] == v for i, v in zip(idxs, values, strict=False)) for row in rows
            )
            if not found:
                return False
    return True


class TestPairwise:
    def test_all_pairs_covered_strength_two(self) -> None:
        fields = [
            _field("cat", "select", options=["A", "B", "C"]),
            _field("price", "select", options=["low", "high"]),
            _field("stock", "select", options=["yes", "no"]),
            _field("ship", "select", options=["std", "exp"]),
        ]
        design = build_test_design(
            _report([_screen("P1", fields=fields)]),
            DesignParams(enabled_techniques=("pw",), pairwise_strength=2),
        )
        pw = design.screens[0].pairwise
        assert pw is not None
        assert _covers_all_pairs(pw.params, pw.rows, 2)
        # ペアワイズは全数（3*2*2*2=24）より少ない
        assert len(pw.rows) < 24

    def test_all_triples_covered_strength_three(self) -> None:
        fields = [_field(f"f{i}", "select", options=["0", "1"]) for i in range(4)]
        design = build_test_design(
            _report([_screen("P1", fields=fields)]),
            DesignParams(enabled_techniques=("pw",), pairwise_strength=3),
        )
        pw = design.screens[0].pairwise
        assert pw is not None
        assert _covers_all_pairs(pw.params, pw.rows, 3)

    def test_deterministic_output(self) -> None:
        fields = [_field(f"f{i}", "select", options=["a", "b", "c"]) for i in range(4)]
        report = _report([_screen("P1", fields=fields)])
        params = DesignParams(enabled_techniques=("pw",))
        first = build_test_design(report, params).screens[0].pairwise
        second = build_test_design(report, params).screens[0].pairwise
        assert first is not None and second is not None
        assert first.rows == second.rows

    def test_too_few_params_no_pairwise(self) -> None:
        fields = [_field("a", "select", options=["1", "2"])]
        design = build_test_design(
            _report([_screen("P1", fields=fields, to=["P2"])]),
            DesignParams(enabled_techniques=("pw",)),
        )
        assert design.screens == () or design.screens[0].pairwise is None

    def test_non_option_fields_use_equivalence_classes(self) -> None:
        fields = [_field(f"t{i}", "text") for i in range(4)]
        design = build_test_design(
            _report([_screen("P1", fields=fields)]),
            DesignParams(enabled_techniques=("pw",)),
        )
        pw = design.screens[0].pairwise
        assert pw is not None
        assert all(p.values == ("有効値", "無効値") for p in pw.params)
        assert _covers_all_pairs(pw.params, pw.rows, 2)


# =========================================================================
# 状態遷移テスト（N スイッチ）
# =========================================================================
class TestStateTransitions:
    def test_zero_switch_lists_each_edge(self) -> None:
        screens = [_screen("P1", to=["P2", "P3"]), _screen("P2", to=[]), _screen("P3", to=[])]
        design = build_test_design(
            _report(screens), DesignParams(enabled_techniques=("st",), n_switch=0)
        )
        st = design.screens[0].state_transitions
        assert st is not None
        seqs = {s.steps for s in st.sequences}
        assert seqs == {("P1", "P2"), ("P1", "P3")}

    def test_one_switch_enumerates_two_edge_paths(self) -> None:
        screens = [_screen("P1", to=["P2"]), _screen("P2", to=["P3"]), _screen("P3", to=[])]
        design = build_test_design(
            _report(screens), DesignParams(enabled_techniques=("st",), n_switch=1)
        )
        st = design.screens[0].state_transitions
        assert st is not None
        assert any(s.steps == ("P1", "P2", "P3") for s in st.sequences)

    def test_self_loop_excluded(self) -> None:
        # P1→P1 の自己ループは遷移として数えない（succ 構築時に除外）
        screens = [_screen("P1", to=["P1", "P2"]), _screen("P2", to=[])]
        design = build_test_design(
            _report(screens), DesignParams(enabled_techniques=("st",), n_switch=0)
        )
        st = next(s for s in design.screens if s.page_id == "P1").state_transitions
        assert st is not None
        seqs = {s.steps for s in st.sequences}
        assert seqs == {("P1", "P2")}  # (P1,P1) は含まれない

    def test_cycle_does_not_loop_forever(self) -> None:
        # 相互リンクのサイクルでも経路列挙は有限（同一ノード再訪を禁止）
        screens = [_screen("P1", to=["P2"]), _screen("P2", to=["P1"])]
        design = build_test_design(
            _report(screens), DesignParams(enabled_techniques=("st",), n_switch=1)
        )
        for sc in design.screens:
            if sc.state_transitions:
                for seq in sc.state_transitions.sequences:
                    assert len(set(seq.steps)) == len(seq.steps)  # 重複ノードなし

    def test_screen_without_transitions_no_st(self) -> None:
        design = build_test_design(
            _report(
                [_screen("P1", fields=[_field("a", required=True), _field("b", required=True)])]
            ),
            DesignParams(enabled_techniques=("st",)),
        )
        assert design.screens == () or design.screens[0].state_transitions is None


# =========================================================================
# 技法の有効/無効
# =========================================================================
class TestTechniqueGating:
    def test_disabled_technique_absent(self) -> None:
        fields = [
            _field("comment", maxlength=100),
            _field("a", required=True),
            _field("b", required=True),
        ]
        design = build_test_design(
            _report([_screen("P1", fields=fields, to=["P2"])]),
            DesignParams(enabled_techniques=("dt",)),
        )
        sc = design.screens[0]
        assert sc.decision_table is not None
        assert sc.bva == ()
        assert sc.state_transitions is None


# =========================================================================
# load_params_from_file（B-2: web/services 非依存のローダ）
# =========================================================================
class TestLoadParamsFromFile:
    def test_load_params_from_file_defaults_on_missing(self, tmp_path: Path) -> None:
        """ファイルが存在しない場合は既定値の TestDesignParams を返す（解析を止めない）。"""
        missing = tmp_path / "does_not_exist.json"
        params = load_params_from_file(missing)
        assert params == DesignParams()

    def test_load_params_from_file_defaults_on_corrupt_json(self, tmp_path: Path) -> None:
        broken = tmp_path / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        params = load_params_from_file(broken)
        assert params == DesignParams()

    def test_load_params_from_file_defaults_on_non_dict_json(self, tmp_path: Path) -> None:
        not_dict = tmp_path / "list.json"
        not_dict.write_text("[1, 2, 3]", encoding="utf-8")
        params = load_params_from_file(not_dict)
        assert params == DesignParams()

    def test_load_params_from_file_round_trips_valid_settings(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "enabled_techniques": ["bva", "dt"],
                    "bva_offset": 2,
                    "pairwise_strength": 3,
                    "n_switch": 1,
                    "max_dt_conditions": 5,
                    "value_catalog": {"email": [{"label": "上限値", "value": "a@b.com"}]},
                }
            ),
            encoding="utf-8",
        )
        params = load_params_from_file(path)
        assert params.enabled_techniques == ("bva", "dt")
        assert params.bva_offset == 2
        assert params.pairwise_strength == 3
        assert params.n_switch == 1
        assert params.max_dt_conditions == 5
        assert params.value_catalog["email"][0]["label"] == "上限値"

    def test_load_params_from_file_caps_max_dt_conditions_at_six(self, tmp_path: Path) -> None:
        """max_dt_conditions は 2^6=64 ルール上限のガード（負荷予算・D-3で固定）。"""
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"max_dt_conditions": 20}), encoding="utf-8")
        params = load_params_from_file(path)
        assert params.max_dt_conditions == 6

    def test_load_params_from_file_defaults_on_type_error(self, tmp_path: Path) -> None:
        """フィールドの型が不正でも例外を投げず既定値へフォールバックする。"""
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"bva_offset": "not-an-int"}), encoding="utf-8")
        params = load_params_from_file(path)
        assert params == DesignParams()
