"""利用実績記録・ROI 集計（usage_tracker）のユニットテスト。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from web.services.usage_tracker import (
    SavingCoefficients,
    build_run_history,
    load_coefficients,
    load_usage,
    record_autorun,
    record_comparison_from_report,
    record_crawl_from_report,
    record_usage,
    record_ux_review_from_report,
    summarize_usage,
)


class TestRecordUsage:
    def test_appends_jsonl(self, tmp_path: Path) -> None:
        path = record_usage(tmp_path, event="crawl", domain="example.com", screen_count=5)
        assert path is not None
        records = load_usage(tmp_path)
        assert len(records) == 1
        assert records[0]["event"] == "crawl"
        assert records[0]["domain"] == "example.com"
        assert records[0]["screen_count"] == 5
        assert "timestamp" in records[0]

    def test_multiple_records_accumulate(self, tmp_path: Path) -> None:
        record_usage(tmp_path, event="crawl", domain="a.com", screen_count=3)
        record_usage(tmp_path, event="crawl", domain="b.com", screen_count=7)
        assert len(load_usage(tmp_path)) == 2

    def test_load_usage_missing_returns_empty(self, tmp_path: Path) -> None:
        assert load_usage(tmp_path) == []

    def test_load_usage_skips_corrupt_lines(self, tmp_path: Path) -> None:
        log = tmp_path / "usage_log.jsonl"
        log.write_text(
            '{"event": "crawl", "screen_count": 2}\nnot-json\n{"event": "crawl"}\n',
            encoding="utf-8",
        )
        assert len(load_usage(tmp_path)) == 2


class TestRecordCrawlFromReport:
    def _write_report(self, domain_dir: Path) -> None:
        domain_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "meta": {"screen_count": 2},
            "screens": [
                {
                    "is_canonical": True,
                    "forms": [
                        {
                            "fields": [
                                {"test_conditions": ["a", "b", "c"]},
                                {"test_conditions": ["d"]},
                            ]
                        }
                    ],
                },
                {"is_canonical": True, "forms": []},
            ],
        }
        (domain_dir / "report.json").write_text(
            json.dumps(report, ensure_ascii=False), encoding="utf-8"
        )
        (domain_dir / "report.html").write_text("<html></html>", encoding="utf-8")

    def test_counts_screens_and_conditions(self, tmp_path: Path) -> None:
        self._write_report(tmp_path / "example.com")
        record_crawl_from_report(tmp_path, "example.com")
        records = load_usage(tmp_path)
        assert records[0]["screen_count"] == 2
        assert records[0]["test_condition_count"] == 4
        assert records[0]["document_count"] >= 2  # report.json + report.html

    def test_missing_report_records_crawl_with_zero(self, tmp_path: Path) -> None:
        record_crawl_from_report(tmp_path, "noreport.com")
        records = load_usage(tmp_path)
        assert records[0]["event"] == "crawl"
        assert records[0]["screen_count"] == 0

    def test_diff_run_flag_recorded(self, tmp_path: Path) -> None:
        self._write_report(tmp_path / "example.com")
        record_crawl_from_report(tmp_path, "example.com", diff_run=True)
        assert load_usage(tmp_path)[0]["diff_run"] is True


class TestRecordComparisonAndUxReviewEvents:
    """AC-1・AC-2・AC-3: comparison / ux_review イベントの実績計上と後方互換。"""

    def test_record_comparison_event(self, tmp_path: Path) -> None:
        """test_record_comparison_event: event="comparison", pairs=5, findings=12
        → JSONL に新キー付き 1 行（AC-1）。"""
        record_usage(
            tmp_path,
            event="comparison",
            domain="example.com",
            compare_screen_count=5,
            finding_count=12,
        )
        records = load_usage(tmp_path)
        assert len(records) == 1
        assert records[0]["event"] == "comparison"
        assert records[0]["compare_screen_count"] == 5
        assert records[0]["finding_count"] == 12

    def test_record_ux_review_event(self, tmp_path: Path) -> None:
        """AC-2: event="ux_review" で対象画面数・指摘数が計上される。"""
        record_usage(
            tmp_path,
            event="ux_review",
            domain="example.com",
            compare_screen_count=3,
            finding_count=7,
        )
        records = load_usage(tmp_path)
        assert records[0]["event"] == "ux_review"
        assert records[0]["compare_screen_count"] == 3
        assert records[0]["finding_count"] == 7

    def test_record_crawl_has_no_new_keys(self, tmp_path: Path) -> None:
        """test_record_crawl_has_no_new_keys: event="crawl" → 行に
        compare_screen_count キーが無い（AC-3・オプトイン）。"""
        record_usage(tmp_path, event="crawl", domain="example.com", screen_count=3)
        records = load_usage(tmp_path)
        assert "compare_screen_count" not in records[0]
        assert "finding_count" not in records[0]

    def test_summarize_mixed_old_and_new_lines(self, tmp_path: Path) -> None:
        """test_summarize_mixed_old_and_new_lines: 旧形式行＋新形式行が混在しても
        例外なく集計され、旧集計値は不変・比較分が加算される（AC-3）。"""
        log = tmp_path / "usage_log.jsonl"
        log.write_text(
            '{"event": "crawl", "screen_count": 4, "test_condition_count": 2}\n'
            '{"event": "comparison", "compare_screen_count": 5, "finding_count": 12}\n',
            encoding="utf-8",
        )
        summary = summarize_usage(load_usage(tmp_path))
        assert summary["total_screens"] == 4
        assert summary["total_test_conditions"] == 2
        assert summary["total_compare_screens"] == 5
        assert summary["total_findings"] == 12

    def test_ux_coefficient_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """test_ux_coefficient_env_override: WEBSPEC2DOC_MIN_PER_UX_FINDING=30
        → 係数反映・不正値は既定 15.0（AC-2）。"""
        monkeypatch.setenv("WEBSPEC2DOC_MIN_PER_UX_FINDING", "30")
        assert load_coefficients().minutes_per_ux_finding == 30.0
        monkeypatch.setenv("WEBSPEC2DOC_MIN_PER_UX_FINDING", "not-a-number")
        assert load_coefficients().minutes_per_ux_finding == 15.0

    def test_compare_screen_coefficient_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WEBSPEC2DOC_MIN_PER_COMPARE_SCREEN", "25")
        assert load_coefficients().minutes_per_compare_screen == 25.0

    def test_saved_hours_include_comparison_and_ux_terms(self) -> None:
        """比較・UX 分の推定削減時間が既存の crawl 分に加算される。"""
        records = [
            {"event": "comparison", "compare_screen_count": 5, "finding_count": 12},
        ]
        coef = SavingCoefficients(minutes_per_compare_screen=20.0, minutes_per_ux_finding=15.0)
        summary = summarize_usage(records, coef)
        # 5*20 + 12*15 = 100 + 180 = 280分 = 4.7時間
        assert summary["estimated_saved_hours"] == round(280 / 60.0, 1)


class TestRecordComparisonFromReport:
    def test_counts_pairs_and_findings(self, tmp_path: Path) -> None:
        comparison_dir = tmp_path / "compare_a_vs_b"
        comparison_dir.mkdir()
        comparison_json = comparison_dir / "comparison.json"
        comparison_json.write_text(
            json.dumps(
                {
                    "pairs": [{"old_page_id": "P001", "new_page_id": "P001"}] * 5,
                    "findings": [{"category": "unclassified", "detail": ""}] * 12,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        record_comparison_from_report(tmp_path, "example.com", comparison_json)
        records = load_usage(tmp_path)
        assert records[0]["event"] == "comparison"
        assert records[0]["compare_screen_count"] == 5
        assert records[0]["finding_count"] == 12

    def test_missing_file_skips_recording(self, tmp_path: Path) -> None:
        result = record_comparison_from_report(
            tmp_path, "example.com", tmp_path / "not_found" / "comparison.json"
        )
        assert result is None
        assert load_usage(tmp_path) == []


class TestRecordUxReviewFromReport:
    def test_counts_screens_and_findings(self, tmp_path: Path) -> None:
        ux_review_json = tmp_path / "ux_review.json"
        ux_review_json.write_text(
            json.dumps(
                {
                    "screens": [
                        {"axe_violations": [{"rule_id": "a"}], "ux_findings": [{"principle": "b"}]},
                        {"axe_violations": [], "ux_findings": []},
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        record_ux_review_from_report(tmp_path, "example.com", ux_review_json)
        records = load_usage(tmp_path)
        assert records[0]["event"] == "ux_review"
        assert records[0]["compare_screen_count"] == 2
        assert records[0]["finding_count"] == 2

    def test_missing_file_skips_recording(self, tmp_path: Path) -> None:
        result = record_ux_review_from_report(tmp_path, "example.com", tmp_path / "ux_review.json")
        assert result is None
        assert load_usage(tmp_path) == []


class TestRecordAutorun:
    def test_appends_autorun_event(self, tmp_path: Path) -> None:
        path = record_autorun(
            tmp_path,
            "example.com",
            status="complete",
            passed=3,
            failed=1,
            total=4,
            duration_sec=120,
        )
        assert path is not None
        records = load_usage(tmp_path)
        assert len(records) == 1
        assert records[0]["event"] == "autorun"
        assert records[0]["domain"] == "example.com"
        assert records[0]["status"] == "complete"
        assert records[0]["passed"] == 3
        assert records[0]["failed"] == 1
        assert records[0]["total"] == 4
        assert records[0]["duration_sec"] == 120

    def test_records_failed_status(self, tmp_path: Path) -> None:
        record_autorun(tmp_path, "example.com", status="failed")
        records = load_usage(tmp_path)
        assert records[0]["status"] == "failed"
        assert records[0]["passed"] == 0


class TestBuildRunHistory:
    def test_merges_log_and_running_jobs_newest_first(self, tmp_path: Path) -> None:
        record_usage(tmp_path, event="crawl", domain="a.com", screen_count=5)
        record_autorun(tmp_path, "b.com", status="complete", passed=2, failed=0, total=2)
        running = [
            {
                "job_id": "job-1",
                "domain": "c.com",
                "status": "running_tests",
                "started_at": "2099-01-01T00:00:00+00:00",
                "test_results": {},
                "elapsed_sec": 10,
            }
        ]
        runs = build_run_history(tmp_path, running)
        assert len(runs) == 3
        # 実行中ジョブは未来日時のためソート後の先頭に来る
        assert runs[0]["source"] == "running"
        assert runs[0]["domain"] == "c.com"
        assert runs[0]["status"] == "running_tests"
        types = {run["type"] for run in runs}
        assert types == {"crawl", "autorun"}

    def test_terminal_running_jobs_excluded_to_avoid_duplication(self, tmp_path: Path) -> None:
        """終端状態のジョブはusage_log側に記録済みのため、実行中一覧からは除外する。"""
        running = [
            {
                "job_id": "job-1",
                "domain": "c.com",
                "status": "complete",
                "started_at": "2026-01-01T00:00:00+00:00",
            }
        ]
        runs = build_run_history(tmp_path, running)
        assert runs == []

    def test_link_only_included_when_file_exists(self, tmp_path: Path) -> None:
        record_usage(tmp_path, event="crawl", domain="example.com", screen_count=1)
        runs = build_run_history(tmp_path)
        assert runs[0]["link"] == ""
        (tmp_path / "example.com").mkdir(parents=True)
        (tmp_path / "example.com" / "report.html").write_text("<html></html>", encoding="utf-8")
        runs = build_run_history(tmp_path)
        assert runs[0]["link"].endswith("report.html")

    def test_empty_when_no_records_or_jobs(self, tmp_path: Path) -> None:
        assert build_run_history(tmp_path) == []


class TestSummarizeUsage:
    def test_computes_saved_hours_from_coefficients(self) -> None:
        # 画面10枚(45分) + 条件12件(10分) + 差分2回(30分)
        #   = 450 + 120 + 60 = 630分 = 10.5時間
        records = [
            {"event": "crawl", "screen_count": 10, "test_condition_count": 12, "diff_run": True},
            {"event": "crawl", "screen_count": 0, "test_condition_count": 0, "diff_run": True},
        ]
        coef = SavingCoefficients(
            minutes_per_screen=45.0,
            minutes_per_condition=10.0,
            minutes_per_diff=30.0,
            hourly_rate_yen=5000.0,
        )
        summary = summarize_usage(records, coef)
        assert summary["total_crawls"] == 2
        assert summary["total_screens"] == 10
        assert summary["total_test_conditions"] == 12
        assert summary["total_diff_runs"] == 2
        assert summary["estimated_saved_hours"] == 10.5
        assert summary["estimated_saved_yen"] == 52500

    def test_empty_records_gives_zero(self) -> None:
        summary = summarize_usage([])
        assert summary["total_crawls"] == 0
        assert summary["estimated_saved_hours"] == 0.0
        assert summary["estimated_saved_yen"] == 0

    def test_disclaimer_states_estimate(self) -> None:
        summary = summarize_usage([])
        assert "推定値" in summary["disclaimer"]

    def test_coefficients_exposed_for_transparency(self) -> None:
        summary = summarize_usage([])
        assert "minutes_per_screen" in summary["coefficients"]
        assert "hourly_rate_yen" in summary["coefficients"]


class TestCoefficientsFromEnv:
    def test_env_overrides_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WEBSPEC2DOC_MIN_PER_SCREEN", "60")
        monkeypatch.setenv("WEBSPEC2DOC_HOURLY_RATE_YEN", "8000")
        coef = load_coefficients()
        assert coef.minutes_per_screen == 60.0
        assert coef.hourly_rate_yen == 8000.0

    def test_invalid_env_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WEBSPEC2DOC_MIN_PER_SCREEN", "abc")
        assert load_coefficients().minutes_per_screen == 45.0
