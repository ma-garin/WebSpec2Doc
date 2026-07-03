"""利用実績記録・ROI 集計（usage_tracker）のユニットテスト。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from web.services.usage_tracker import (
    SavingCoefficients,
    load_coefficients,
    load_usage,
    record_crawl_from_report,
    record_usage,
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
