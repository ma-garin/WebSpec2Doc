"""L3 原因特定 / L1 部分変異体のテスト（設計計画 rev.3 Phase 2）。

仮説カタログは机上の想定ではなく、本セッションで人が実サイト検証で
突き止めた実在の原因を知識化したもの。その対応関係を検証する。
"""

from __future__ import annotations

from pathlib import Path

from web.services.failure_hypothesis import (
    HYPOTHESES,
    MAX_HYPOTHESES_PER_FAILURE,
    match_hypotheses,
    triage,
)
from web.services.mutation_verifier import (
    MUTANT_OPTIONS,
    MUTANT_REQUIRED,
    MUTANT_TEXT,
    MUTANT_TOTAL,
    build_mutant_spec,
    mutant_kinds,
)

_SPEC = """import { test, expect } from './_autorun_egress';

test('PW-0001 必須入力 [P011-F01-I01]', async ({ page }) => {
  await page.goto('https://example.com/');
  await page.locator('#date').fill('');
  const v = await page.locator('#date').evaluate((el) => el.checkValidity());
  expect(v).toBe(false);
});

test.skip('PW-0002 手動 [A11Y-ALL]', async () => {});
"""


class TestHypothesisCatalog:
    def test_environment_hypothesis_is_checked_first(self) -> None:
        """落ちている対象を他の仮説で叩き続けないこと。"""
        assert max(HYPOTHESES, key=lambda h: h.priority).hypothesis_id == "H7"

    def test_every_hypothesis_carries_real_evidence(self) -> None:
        """机上の想定ではなく実観測に基づくこと。"""
        for h in HYPOTHESES:
            assert h.evidence.strip()
            assert h.probe.strip()

    def test_catalog_covers_the_five_real_causes(self) -> None:
        ids = {h.hypothesis_id for h in HYPOTHESES}
        assert {"H1", "H2", "H3", "H4", "H5"} <= ids


class TestMatching:
    def test_overlay_interception_matches_h3(self) -> None:
        error = "Timeout: <table class='ui-datepicker-calendar'> intercepts pointer events"
        assert "H3" in {h.hypothesis_id for h in match_hypotheses(error)}

    def test_disabled_field_matches_h4(self) -> None:
        error = "locator.fill: Timeout 20000ms exceeded. element is not editable, disabled"
        assert "H4" in {h.hypothesis_id for h in match_hypotheses(error)}

    def test_network_error_matches_h7_first(self) -> None:
        matched = match_hypotheses("net::ERR_CONNECTION_REFUSED at https://example.com/")
        assert matched[0].hypothesis_id == "H7"

    def test_validity_failure_matches_value_hypotheses(self) -> None:
        ids = {h.hypothesis_id for h in match_hypotheses("expected true, received false checkValidity")}
        assert ids & {"H1", "H2", "H5"}

    def test_hypotheses_are_capped(self) -> None:
        """予算と対象への配慮。全仮説を無差別に試さない。"""
        matched = match_hypotheses("Timeout checkValidity disabled intercepts pointer events valid")
        assert len(matched) <= MAX_HYPOTHESES_PER_FAILURE

    def test_unknown_error_matches_nothing(self) -> None:
        assert match_hypotheses("完全に未知の事象") == ()


class TestTriage:
    def test_explains_known_failures(self) -> None:
        result = triage(
            [{"title": "PW-0061 フォーム入力", "error": "intercepts pointer events"}]
        )
        assert result["triaged"][0]["explained"] is True
        assert result["triaged"][0]["candidates"][0]["hypothesis_id"] == "H3"

    def test_unexplained_failures_are_never_hidden(self) -> None:
        """「全部原因が分かった」と装わない（条件2）。"""
        result = triage([{"title": "PW-0099", "error": "未知の事象"}])
        assert result["unexplained_count"] == 1
        assert result["triaged"] == []
        assert result["unexplained"][0]["title"] == "PW-0099"

    def test_notice_states_candidates_are_not_confirmation(self) -> None:
        result = triage([{"title": "x", "error": "Timeout"}])
        assert "原因の確定を意味せず" in result["notice"]
        assert "原因が無いことを意味しません" in result["notice"]

    def test_no_failures_is_not_applicable(self) -> None:
        assert triage([])["applicable"] is False

    def test_large_failure_set_is_truncated_and_declared(self) -> None:
        failures = [{"title": f"T{i}", "error": "Timeout"} for i in range(100)]
        result = triage(failures)
        assert result["truncated_count"] > 0


class TestPartialMutants:
    def test_all_kinds_are_available(self) -> None:
        kinds = mutant_kinds()
        for kind in (MUTANT_TOTAL, MUTANT_REQUIRED, MUTANT_TEXT, MUTANT_OPTIONS):
            assert kind in kinds

    def test_required_mutant_removes_required_attribute(self, tmp_path: Path) -> None:
        """必須入力テストが required 除去を検出できなければ、それは形だけのテスト。"""
        spec = tmp_path / "spec.ts"
        spec.write_text(_SPEC, encoding="utf-8")
        out = tmp_path / "mutant.spec.ts"
        assert build_mutant_spec(spec, out, kind=MUTANT_REQUIRED) == 1
        body = out.read_text(encoding="utf-8")
        assert "removeAttribute('required')" in body
        assert "addInitScript" in body

    def test_text_mutant_alters_headings(self, tmp_path: Path) -> None:
        spec = tmp_path / "spec.ts"
        spec.write_text(_SPEC, encoding="utf-8")
        out = tmp_path / "mutant.spec.ts"
        build_mutant_spec(spec, out, kind=MUTANT_TEXT)
        assert "MUTATED_TITLE" in out.read_text(encoding="utf-8")

    def test_options_mutant_reduces_select_choices(self, tmp_path: Path) -> None:
        spec = tmp_path / "spec.ts"
        spec.write_text(_SPEC, encoding="utf-8")
        out = tmp_path / "mutant.spec.ts"
        build_mutant_spec(spec, out, kind=MUTANT_OPTIONS)
        assert "sel.remove(1)" in out.read_text(encoding="utf-8")

    def test_skip_tests_are_never_mutated(self, tmp_path: Path) -> None:
        spec = tmp_path / "spec.ts"
        spec.write_text(_SPEC, encoding="utf-8")
        out = tmp_path / "mutant.spec.ts"
        build_mutant_spec(spec, out, kind=MUTANT_REQUIRED)
        content = out.read_text(encoding="utf-8")
        skip_at = content.index("test.skip(")
        assert "addInitScript" not in content[skip_at : skip_at + 100]

    def test_total_mutant_is_still_the_default(self, tmp_path: Path) -> None:
        spec = tmp_path / "spec.ts"
        spec.write_text(_SPEC, encoding="utf-8")
        out = tmp_path / "mutant.spec.ts"
        build_mutant_spec(spec, out)
        assert "route.fulfill" in out.read_text(encoding="utf-8")
