"""カバレッジギャップ集計（generator.coverage_gap）のユニットテスト。

audit.jsonl・PageData.embedded_frames・探索カバレッジ・現新比較（comparison.json）の
4 情報源を CoverageGap に正規化する collect_coverage_gaps を検証する（AC-5）。
"""

from __future__ import annotations

import json
from pathlib import Path

from crawler.page_crawler import EmbeddedFrame, PageData
from generator.coverage_gap import (
    KIND_LOGIN_WALL,
    KIND_ROBOTS_SKIPPED,
    KIND_UNCHECKED_LINK,
    KIND_UNEXPLORED_SCREEN,
    KIND_UNREADABLE_FRAME,
    CoverageGap,
    collect_coverage_gaps,
)


def _page(url: str, embedded_frames: tuple[EmbeddedFrame, ...] = ()) -> PageData:
    return PageData(
        url=url,
        title="title",
        headings=(),
        links=(),
        forms=(),
        screenshot_path=None,
        embedded_frames=embedded_frames,
    )


def _write_audit(output_dir: Path, records: list[dict]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "audit.jsonl").open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


class TestCollectCoverageGapsEmpty:
    def test_no_sources_returns_empty(self, tmp_path: Path) -> None:
        assert collect_coverage_gaps(tmp_path, []) == ()

    def test_gap_section_absent_when_empty(self, tmp_path: Path) -> None:
        """test_gap_section_absent_when_empty: ギャップ 0 件 → 呼び出し側は
        既存出力と同一のまま（AC-8 は html_reporter 側で保証。ここでは空タプルを確認）。"""
        _write_audit(tmp_path, [{"event": "crawl_started", "robots_skipped_urls": []}])
        assert collect_coverage_gaps(tmp_path, [_page("https://example.com/")]) == ()


class TestRobotsSkippedGaps:
    def test_robots_skipped_urls_become_gaps(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "event": "crawl_started",
                    "robots_skipped_urls": ["https://example.com/admin"],
                }
            ],
        )
        gaps = collect_coverage_gaps(tmp_path, [])
        assert gaps == (
            CoverageGap(
                kind=KIND_ROBOTS_SKIPPED,
                subject="https://example.com/admin",
                reason="robots.txt により対象外（未確認）",
            ),
        )

    def test_only_latest_crawl_started_is_used(self, tmp_path: Path) -> None:
        """§8 既知の罠: 過去実行の robots_skipped_urls を再表示しない。"""
        _write_audit(
            tmp_path,
            [
                {
                    "event": "crawl_started",
                    "robots_skipped_urls": ["https://example.com/old-skip"],
                },
                {
                    "event": "crawl_started",
                    "robots_skipped_urls": ["https://example.com/new-skip"],
                },
            ],
        )
        gaps = collect_coverage_gaps(tmp_path, [])
        subjects = [g.subject for g in gaps if g.kind == KIND_ROBOTS_SKIPPED]
        assert subjects == ["https://example.com/new-skip"]


class TestLoginWallGaps:
    def test_login_wall_after_latest_crawl_started(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {"event": "crawl_started", "robots_skipped_urls": []},
                {
                    "event": "login_wall_detected",
                    "url": "https://example.com/mypage",
                    "login_url": "https://example.com/login",
                },
            ],
        )
        gaps = collect_coverage_gaps(tmp_path, [])
        assert gaps == (
            CoverageGap(
                kind=KIND_LOGIN_WALL,
                subject="https://example.com/mypage",
                reason="ログインが必要なため未確認",
            ),
        )

    def test_login_wall_before_latest_crawl_started_is_excluded(self, tmp_path: Path) -> None:
        """過去実行の login_wall_detected は最新 crawl_started 以前として除外される。"""
        _write_audit(
            tmp_path,
            [
                {
                    "event": "login_wall_detected",
                    "url": "https://example.com/old-mypage",
                    "login_url": "https://example.com/login",
                },
                {"event": "crawl_started", "robots_skipped_urls": []},
            ],
        )
        gaps = collect_coverage_gaps(tmp_path, [])
        assert gaps == ()


class TestUnreadableFrameGaps:
    def test_unreadable_frame_becomes_gap(self, tmp_path: Path) -> None:
        page = _page(
            "https://example.com/",
            embedded_frames=(
                EmbeddedFrame(
                    src="https://other.example/widget",
                    readable=False,
                    note="クロスオリジンのため未読",
                ),
                EmbeddedFrame(src="https://example.com/same-origin", readable=True),
            ),
        )
        gaps = collect_coverage_gaps(tmp_path, [page])
        assert gaps == (
            CoverageGap(
                kind=KIND_UNREADABLE_FRAME,
                subject="https://other.example/widget",
                reason="クロスオリジンのため未読",
            ),
        )


class TestUnexploredScreenGaps:
    def test_unexplored_screen_becomes_gap(self, tmp_path: Path) -> None:
        coverage = {
            "screens": [
                {"page_id": "P001", "url": "https://example.com/a", "explored": True},
                {"page_id": "P002", "url": "https://example.com/b", "explored": False},
            ]
        }
        gaps = collect_coverage_gaps(tmp_path, [], coverage)
        assert gaps == (
            CoverageGap(
                kind=KIND_UNEXPLORED_SCREEN,
                subject="https://example.com/b",
                reason="探索セッションで未訪問のため未確認",
            ),
        )

    def test_coverage_none_yields_no_unexplored_gaps(self, tmp_path: Path) -> None:
        assert collect_coverage_gaps(tmp_path, [], None) == ()


class TestUncheckedLinkGaps:
    def test_unconfirmed_link_finding_becomes_gap(self, tmp_path: Path) -> None:
        comparison = {
            "findings": [
                {
                    "category": "unclassified",
                    "detail": "未確認（タイムアウト）: https://new.example/broken（リンク元: P001）",
                },
                {"category": "inoperable", "detail": "無関係な指摘"},
            ]
        }
        (tmp_path / "comparison.json").write_text(
            json.dumps(comparison, ensure_ascii=False), encoding="utf-8"
        )
        gaps = collect_coverage_gaps(tmp_path, [])
        assert gaps == (
            CoverageGap(
                kind=KIND_UNCHECKED_LINK,
                subject="https://new.example/broken",
                reason="タイムアウト/接続失敗のため未確認（切れとは断定しない）",
            ),
        )

    def test_no_comparison_json_yields_no_unchecked_link_gaps(self, tmp_path: Path) -> None:
        assert collect_coverage_gaps(tmp_path, []) == ()


class TestGapsFromAllSources:
    def test_gaps_from_all_sources(self, tmp_path: Path) -> None:
        """test_gaps_from_all_sources: audit＋embedded_frames＋coverage の fixture
        → 4 種の CoverageGap が正規化される（AC-5）。"""
        _write_audit(
            tmp_path,
            [
                {
                    "event": "crawl_started",
                    "robots_skipped_urls": ["https://example.com/admin"],
                },
                {
                    "event": "login_wall_detected",
                    "url": "https://example.com/mypage",
                    "login_url": "https://example.com/login",
                },
            ],
        )
        page = _page(
            "https://example.com/",
            embedded_frames=(
                EmbeddedFrame(src="https://ads.example/", readable=False, note="広告枠"),
            ),
        )
        coverage = {
            "screens": [{"page_id": "P002", "url": "https://example.com/deep", "explored": False}]
        }
        gaps = collect_coverage_gaps(tmp_path, [page], coverage)
        kinds = {g.kind for g in gaps}
        assert kinds == {
            KIND_ROBOTS_SKIPPED,
            KIND_LOGIN_WALL,
            KIND_UNREADABLE_FRAME,
            KIND_UNEXPLORED_SCREEN,
        }
        assert len(gaps) == 4


class TestAuditLogResilience:
    def test_corrupt_audit_line_is_skipped(self, tmp_path: Path) -> None:
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "audit.jsonl").write_text(
            '{"event": "crawl_started", "robots_skipped_urls": ["https://example.com/a"]}\n'
            "not-json\n",
            encoding="utf-8",
        )
        gaps = collect_coverage_gaps(tmp_path, [])
        assert len(gaps) == 1

    def test_missing_audit_log_yields_no_error(self, tmp_path: Path) -> None:
        assert collect_coverage_gaps(tmp_path, []) == ()
