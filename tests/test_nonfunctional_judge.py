"""L4 非機能判定 / L0 観測完全性のテスト（設計計画 rev.3 Phase 1）。

監査で判明した欠落: a11y 違反 635 件を観測しながら判定へ接続していなかった。
基準線方式（初回は基準線確立のみ、以降は増加分を不合格）で
オオカミ少年化を避けつつ回帰を捕まえることを確認する。
"""

from __future__ import annotations

from typing import Any

from web.services.nonfunctional_judge import (
    VERDICT_BASELINE,
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_UNKNOWN,
    judge_accessibility,
    judge_all,
    judge_performance,
    judge_technical_health,
)
from web.services.observation_coverage import analyze


def _report(lcp: float = 300.0, cls: float = 0.0, ttfb: float = 100.0) -> dict[str, Any]:
    return {
        "meta": {"page_count": 24, "screen_count": 12, "crawl_depth": 10, "max_pages": 500},
        "screens": [
            {
                "page_id": "P001",
                "url": "https://example.com/",
                "performance": {
                    "lcp_ms": lcp,
                    "cls": cls,
                    "ttfb_ms": ttfb,
                    "claim_scope": "lab_single_run_this_environment",
                },
                "transitions": {"to": []},
            }
        ],
    }


def _a11y(critical: int = 0, serious: int = 253, moderate: int = 382) -> dict[str, Any]:
    return {
        "summary": {
            "violations": critical + serious + moderate,
            "critical": critical,
            "serious": serious,
            "moderate": moderate,
            "minor": 0,
        }
    }


class TestPerformance:
    def test_within_thresholds_passes(self) -> None:
        assert judge_performance(_report()).verdict == VERDICT_PASS

    def test_lcp_over_threshold_fails(self) -> None:
        j = judge_performance(_report(lcp=4000.0))
        assert j.verdict == VERDICT_FAIL
        assert "LCP" in j.details[0]["exceeded"][0]

    def test_cls_over_threshold_fails(self) -> None:
        assert judge_performance(_report(cls=0.5)).verdict == VERDICT_FAIL

    def test_lab_measurement_limit_is_stated(self) -> None:
        """ラボ単回計測を実利用性能と誤読させない（claim_scope）。"""
        assert "実利用環境" in judge_performance(_report()).claim_scope

    def test_missing_data_is_unknown_not_pass(self) -> None:
        j = judge_performance({"screens": [{"page_id": "P001"}]})
        assert j.verdict == VERDICT_UNKNOWN
        assert "未検証" in j.claim_scope


class TestAccessibilityBaseline:
    def test_first_run_establishes_baseline_without_failing(self) -> None:
        """635件を即不合格にするとオオカミ少年になる。初回は基準線のみ。"""
        j = judge_accessibility(_a11y(), baseline=None)
        assert j.verdict == VERDICT_BASELINE
        assert "基準線" in j.summary

    def test_critical_fails_even_on_first_run(self) -> None:
        """重大な障壁は基準線を待たない。"""
        j = judge_accessibility(_a11y(critical=3), baseline=None)
        assert j.verdict == VERDICT_FAIL

    def test_increase_from_baseline_fails(self) -> None:
        first = judge_all(None, _a11y(), None, baseline=None)
        second = judge_accessibility(_a11y(serious=260), baseline=first)
        assert second.verdict == VERDICT_FAIL
        assert "増えました" in second.summary

    def test_no_increase_passes_without_claiming_no_problem(self) -> None:
        first = judge_all(None, _a11y(), None, baseline=None)
        second = judge_accessibility(_a11y(), baseline=first)
        assert second.verdict == VERDICT_PASS
        # 「問題なし」ではなく「悪化なし」（条件2）
        assert "悪化はありません" in second.summary
        assert "問題なし" not in second.summary

    def test_decrease_passes(self) -> None:
        first = judge_all(None, _a11y(), None, baseline=None)
        second = judge_accessibility(_a11y(serious=100), baseline=first)
        assert second.verdict == VERDICT_PASS

    def test_automated_check_limit_is_stated(self) -> None:
        j = judge_accessibility(_a11y(), baseline=None)
        assert "適合の証明にはなりません" in j.claim_scope

    def test_missing_data_is_unknown(self) -> None:
        assert judge_accessibility(None, None).verdict == VERDICT_UNKNOWN


class TestTechnicalHealth:
    def test_clean_passes(self) -> None:
        health = {
            "summary": {
                "page_http_errors": 0,
                "broken_links": 0,
                "console_errors": 0,
                "mixed_content": 0,
            }
        }
        assert judge_technical_health(health).verdict == VERDICT_PASS

    def test_problems_fail_with_detail(self) -> None:
        health = {"summary": {"page_http_errors": 2, "broken_links": 5}}
        j = judge_technical_health(health)
        assert j.verdict == VERDICT_FAIL
        assert any(d["kind"] == "リンク切れ" for d in j.details)


class TestJudgeAll:
    def test_notice_never_claims_no_problem(self) -> None:
        result = judge_all(_report(), _a11y(), None)
        assert "証明ではありません" in result["notice"]

    def test_any_failure_makes_overall_fail(self) -> None:
        result = judge_all(_report(lcp=9999.0), _a11y(), None)
        assert result["overall"] == VERDICT_FAIL


class TestObservationCoverage:
    def test_records_scope(self) -> None:
        c = analyze(_report())
        assert c.observed_pages == 24
        assert c.canonical_screens == 12

    def test_login_wall_is_recorded_as_gap(self) -> None:
        """認証後を見ていないなら、それは未検証であって問題なしではない。"""
        c = analyze(_report(), job_log=["画面分析完了: 28件 (要ログイン: 4件)"])
        gap = next(g for g in c.gaps if "認証" in g.kind)
        assert gap.count == 4
        assert not c.is_complete

    def test_page_limit_truncation_is_recorded(self) -> None:
        report = _report()
        report["meta"]["page_count"] = 500
        report["meta"]["max_pages"] = 500
        c = analyze(report)
        assert any("件数上限" in g.kind for g in c.gaps)

    def test_unreadable_frame_is_recorded(self) -> None:
        report = _report()
        report["screens"][0]["embedded_frames"] = [
            {"src": "https://other.example/widget", "readable": False}
        ]
        c = analyze(report)
        assert any("フレーム" in g.kind for g in c.gaps)

    def test_unreached_transition_target_is_recorded(self) -> None:
        report = _report()
        report["screens"][0]["transitions"] = {"to": ["P999"]}
        c = analyze(report)
        assert any("遷移先" in g.kind for g in c.gaps)

    def test_scope_statement_declares_unverified(self) -> None:
        c = analyze(_report(), job_log=["画面分析完了: 28件 (要ログイン: 4件)"])
        statement = c.scope_statement()
        assert "観測できていません" in statement
        assert "「問題なし」を意味しません" in statement

    def test_complete_observation_still_notes_limits(self) -> None:
        statement = analyze(_report()).scope_statement()
        assert "観測手段の限界" in statement
