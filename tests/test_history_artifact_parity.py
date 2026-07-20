"""受付経由と履歴経由で、見える成果物が一致することのテスト。

利用者が操作して発見した問題:
  「受付から実施した成果物と履歴からみる成果物が違うのも大問題です」

原因: 履歴は usage_log.jsonl から独自にリンクを再構築しており、
単一HTMLへのリンクしか持っていなかった。仕様17番の専用レポート画面
（ダッシュボード・QA仕様書・計画・分析・設計・ケース・スクリプト・実行結果）
へ繋がっておらず、履歴から入ると成果物のほとんどが消えていた。
"""

from __future__ import annotations

import json
from pathlib import Path

from web.services.usage_tracker import _run_from_record, build_run_history


def _autorun_record(domain: str = "example.com") -> dict:
    return {
        "event": "autorun",
        "domain": domain,
        "timestamp": "2026-07-20T12:00:00+09:00",
        "status": "complete",
        "passed": 10,
        "failed": 0,
        "total": 10,
        "duration_sec": 30,
    }


def _make_artifacts(root: Path, domain: str = "example.com") -> Path:
    domain_dir = root / domain
    (domain_dir / "qa_process").mkdir(parents=True)
    (domain_dir / "report.json").write_text("{}", encoding="utf-8")
    return domain_dir


class TestHistoryLinksToReportPage:
    def test_autorun_history_exposes_the_dedicated_report_page(self, tmp_path: Path) -> None:
        """履歴から専用レポート画面（全成果物）へ辿れること。"""
        _make_artifacts(tmp_path)
        entry = _run_from_record(tmp_path, _autorun_record())
        assert entry["report_url"] == "/autorun/report/example.com"

    def test_report_url_is_absent_when_no_artifacts(self, tmp_path: Path) -> None:
        """成果物が無いのにリンクを捏造しないこと。"""
        entry = _run_from_record(tmp_path, _autorun_record())
        assert "report_url" not in entry

    def test_non_autorun_runs_have_no_report_url(self, tmp_path: Path) -> None:
        record = {"event": "crawl", "domain": "example.com", "timestamp": "2026-07-20T12:00:00"}
        assert "report_url" not in _run_from_record(tmp_path, record)

    def test_build_run_history_carries_report_url(self, tmp_path: Path) -> None:
        _make_artifacts(tmp_path)
        (tmp_path / "usage_log.jsonl").write_text(
            json.dumps(_autorun_record()) + "\n", encoding="utf-8"
        )
        runs = build_run_history(tmp_path)
        autorun = next(r for r in runs if r["type"] == "autorun")
        assert autorun["report_url"] == "/autorun/report/example.com"

    def test_domain_is_required_for_report_url(self, tmp_path: Path) -> None:
        record = _autorun_record(domain="")
        assert "report_url" not in _run_from_record(tmp_path, record)
