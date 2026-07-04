"""現新比較レポート（comparison_reporter）の網羅性サマリ（AC-6）のユニットテスト。"""

from __future__ import annotations

from pathlib import Path

from diff.comparison import ComparisonFinding, ComparisonResult
from diff.pair_matcher import ScreenPair
from generator.comparison_reporter import (
    comparison_result_to_dict,
    compute_coverage_summary,
    generate_comparison_html,
    save_comparison_outputs,
)


def _pair(old_id: str, new_id: str) -> ScreenPair:
    return ScreenPair(old_page_id=old_id, new_page_id=new_id, score=1.0, method="path")


def _unclassified_unconfirmed_finding(url: str, source_page_id: str) -> ComparisonFinding:
    return ComparisonFinding(
        category="unclassified",
        page_pair=None,
        detail=f"未確認（タイムアウト）: {url}（リンク元: {source_page_id}）",
        old_evidence=None,
        new_evidence=None,
        severity="info",
    )


class TestComputeCoverageSummary:
    def test_matches_pairs_added_removed_and_unchecked_links(self) -> None:
        result = ComparisonResult(
            pairs=(_pair("P001", "P001"), _pair("P002", "P002")),
            added_page_ids=("P010",),
            removed_page_ids=("P020", "P021"),
            findings=(
                _unclassified_unconfirmed_finding("https://new.example/broken", "P001"),
                ComparisonFinding(
                    category="inoperable",
                    page_pair=None,
                    detail="無関係な指摘",
                    old_evidence=None,
                    new_evidence=None,
                    severity="breaking",
                ),
            ),
            screenshot_diffs=(),
        )
        summary = compute_coverage_summary(result)
        assert summary == {
            "matched_pairs": 2,
            "old_only": 2,
            "new_only": 1,
            "unchecked_links": 1,
        }

    def test_zero_when_no_findings(self) -> None:
        result = ComparisonResult(
            pairs=(), added_page_ids=(), removed_page_ids=(), findings=(), screenshot_diffs=()
        )
        summary = compute_coverage_summary(result)
        assert summary == {
            "matched_pairs": 0,
            "old_only": 0,
            "new_only": 0,
            "unchecked_links": 0,
        }


class TestComparisonHtmlCoverageSummary:
    def test_html_contains_coverage_summary_tiles(self) -> None:
        result = ComparisonResult(
            pairs=(_pair("P001", "P001"),),
            added_page_ids=("P010",),
            removed_page_ids=(),
            findings=(_unclassified_unconfirmed_finding("https://new.example/broken", "P001"),),
            screenshot_diffs=(),
        )
        html_text = generate_comparison_html(result)
        assert "網羅性サマリ" in html_text
        assert "対応付け（組）" in html_text
        assert "検査できなかったリンク" in html_text


class TestComparisonJsonCoverageSummary:
    def test_json_dict_contains_coverage_summary(self) -> None:
        result = ComparisonResult(
            pairs=(_pair("P001", "P001"),),
            added_page_ids=(),
            removed_page_ids=(),
            findings=(),
            screenshot_diffs=(),
        )
        data = comparison_result_to_dict(result)
        assert data["coverage_summary"] == {
            "matched_pairs": 1,
            "old_only": 0,
            "new_only": 0,
            "unchecked_links": 0,
        }


class TestSaveComparisonOutputs:
    def test_html_and_json_written(self, tmp_path: Path) -> None:
        result = ComparisonResult(
            pairs=(_pair("P001", "P001"),),
            added_page_ids=(),
            removed_page_ids=(),
            findings=(),
            screenshot_diffs=(),
        )
        json_path, html_path = save_comparison_outputs(result, tmp_path)
        assert json_path.is_file()
        assert html_path.is_file()
        assert "網羅性サマリ" in html_path.read_text(encoding="utf-8")
