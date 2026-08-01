"""現新比較ワークスペースのデータ整形（P2-2 第2弾）。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web.services.comparison_workspace import (  # noqa: E402
    PAIR_STATE_ADDED,
    PAIR_STATE_MATCHED,
    PAIR_STATE_REMOVED,
    build_workspace,
)

OUT = Path("/tmp/webspec2doc-test-output")


def _comparison(**over):
    base = {
        "pairs": [{"old_page_id": "P001", "new_page_id": "P001", "title": "トップ", "url": "/"}],
        "added_page_ids": [],
        "removed_page_ids": [],
        "findings": [],
        "coverage_summary": {"matched_pairs": 1},
        "screenshot_diffs": [],
    }
    base.update(over)
    return base


def _finding(category="layout_broken", severity="medium", old_id="P001"):
    return {
        "category": category,
        "severity": severity,
        "detail": "見出し領域の余白が変更",
        "page_pair": {"old_page_id": old_id, "new_page_id": old_id},
        "confidence": 1.0,
    }


class TestPairAssembly:
    def test_matched_pair_carries_its_findings(self) -> None:
        ws = build_workspace(_comparison(findings=[_finding()]), OUT)
        pair = ws["pairs"][0]
        assert pair["state"] == PAIR_STATE_MATCHED
        assert pair["finding_count"] == 1
        assert pair["findings"][0]["detail"] == "見出し領域の余白が変更"

    def test_top_finding_is_the_most_severe(self) -> None:
        """レールに出すのは最も重い指摘。軽いものが先頭に来ると危険度を読み違える。"""
        findings = [_finding(severity="low"), _finding(category="inoperable", severity="high")]
        ws = build_workspace(_comparison(findings=findings), OUT)
        assert ws["pairs"][0]["top_severity"] == "high"
        assert ws["pairs"][0]["top_category"] == "inoperable"

    def test_findings_of_other_pairs_are_not_mixed_in(self) -> None:
        comparison = _comparison(
            pairs=[
                {"old_page_id": "P001", "new_page_id": "P001"},
                {"old_page_id": "P002", "new_page_id": "P002"},
            ],
            findings=[_finding(old_id="P002")],
        )
        ws = build_workspace(comparison, OUT)
        by_id = {p["old_page_id"]: p for p in ws["pairs"]}
        assert by_id["P001"]["finding_count"] == 0
        assert by_id["P002"]["finding_count"] == 1


class TestUnmatchedPages:
    def test_added_and_removed_become_pairs_with_reason(self) -> None:
        """追加・削除は「指摘0件」と同じ見た目にしない（比較できていないため）。"""
        ws = build_workspace(
            _comparison(added_page_ids=["P009"], removed_page_ids=["P008"]), OUT
        )
        states = {p["state"]: p for p in ws["pairs"]}
        assert states[PAIR_STATE_ADDED]["unmatched_reason"]
        assert states[PAIR_STATE_REMOVED]["unmatched_reason"]

    def test_counts_separate_matched_from_unmatched(self) -> None:
        ws = build_workspace(
            _comparison(added_page_ids=["P009"], removed_page_ids=["P008"]), OUT
        )
        assert ws["counts"] == {
            "pairs": 3,
            "matched": 1,
            "added": 1,
            "removed": 1,
            "with_findings": 0,
            "findings": 0,
        }


class TestScreenshotPaths:
    def test_paths_are_passed_through_for_preview(self) -> None:
        """/preview?path= はカレントディレクトリ基準で解決するため、保存形をそのまま渡す。

        出力先からの相対パスに直すと /preview が 404 を返す。
        """
        diffs = [
            {
                "page_id": "P001",
                "before_path": str(OUT / "x" / "old" / "P001.png"),
                "after_path": str(OUT / "x" / "new" / "P001.png"),
                "diff_image_path": str(OUT / "x" / "new" / "screenshot_diffs" / "P001.png"),
                "diff_ratio": 0.02,
                "is_significant": True,
            }
        ]
        ws = build_workspace(_comparison(screenshot_diffs=diffs), OUT)
        shots = ws["pairs"][0]["screenshots"]
        assert shots["before"] == str(OUT / "x" / "old" / "P001.png")
        assert shots["diff"] == str(OUT / "x" / "new" / "screenshot_diffs" / "P001.png")
        assert shots["is_significant"] is True

    def test_relative_saved_form_is_kept(self) -> None:
        """保存されている 'output/...' 形式もそのまま通ること。"""
        diffs = [
            {
                "page_id": "P001",
                "before_path": "output/example.com/screenshots/P001.png",
                "after_path": "",
                "diff_image_path": "",
                "diff_ratio": 0.0,
                "is_significant": False,
            }
        ]
        ws = build_workspace(_comparison(screenshot_diffs=diffs), Path("output"))
        assert ws["pairs"][0]["screenshots"]["before"] == "output/example.com/screenshots/P001.png"

    def test_paths_outside_output_dir_are_dropped(self) -> None:
        """出力先の外を指すパスは画面へ渡さない。"""
        diffs = [
            {
                "page_id": "P001",
                "before_path": "/etc/passwd",
                "after_path": "",
                "diff_image_path": "",
                "diff_ratio": 0.0,
                "is_significant": False,
            }
        ]
        ws = build_workspace(_comparison(screenshot_diffs=diffs), OUT)
        assert ws["pairs"][0]["screenshots"]["before"] == ""

    def test_pair_without_screenshots_has_empty_dict(self) -> None:
        ws = build_workspace(_comparison(), OUT)
        assert ws["pairs"][0]["screenshots"] == {}

    def test_same_capture_is_flagged(self) -> None:
        """世代保存より前のスナップショットは両世代が同じ画像を指す。

        並べても同じ絵になるため、「変化が無い」ではなく「比較できない」と
        分かるように印を付ける。
        """
        shot = str(OUT / "example.com" / "screenshots" / "P001.png")
        diffs = [
            {
                "page_id": "P001",
                "before_path": shot,
                "after_path": shot,
                "diff_image_path": "",
                "diff_ratio": 0.0,
                "is_significant": False,
            }
        ]
        ws = build_workspace(_comparison(screenshot_diffs=diffs), OUT)
        assert ws["pairs"][0]["screenshots"]["same_capture"] is True

    def test_different_captures_are_not_flagged(self) -> None:
        diffs = [
            {
                "page_id": "P001",
                "before_path": str(OUT / "a" / "P001.png"),
                "after_path": str(OUT / "b" / "P001.png"),
                "diff_image_path": "",
                "diff_ratio": 0.0,
                "is_significant": False,
            }
        ]
        ws = build_workspace(_comparison(screenshot_diffs=diffs), OUT)
        assert ws["pairs"][0]["screenshots"]["same_capture"] is False


def test_labels_are_carried_through() -> None:
    ws = build_workspace(_comparison(), OUT, from_label="20260801-143846", to_label="20260801-143907")
    assert ws["from"] == "20260801-143846"
    assert ws["to"] == "20260801-143907"
