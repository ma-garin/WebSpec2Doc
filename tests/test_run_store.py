"""実行回ごとの成果物置き場（web/services/run_store.py）のテスト。

守りたいこと:
  - 実行回ごとに成果物が残る（最新1件しか残らない現状の解消）
  - 無いものを在るように見せない（空の run を作らない・捏造リンクを返さない）
  - run_id で経路トラバーサルできない
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from web.services.run_store import (
    artifact_file,
    latest_run_id,
    list_runs,
    load_meta,
    new_run_id,
    run_dir,
    snapshot_run,
    valid_run_id,
)

DOMAIN = "example.com"


def _make_artifacts(root: Path, *, qa: bool = False, testcases: bool = False) -> Path:
    d = root / DOMAIN
    d.mkdir(parents=True, exist_ok=True)
    (d / "report.html").write_text("<html>report</html>", encoding="utf-8")
    (d / "report.json").write_text(json.dumps({"screens": [{"page_id": "P001"}]}), encoding="utf-8")
    (d / "screens.md").write_text("# 画面一覧", encoding="utf-8")
    if qa:
        qa_dir = d / "qa_process"
        qa_dir.mkdir(exist_ok=True)
        (qa_dir / "playwright_report.json").write_text(
            json.dumps({"summary": {"total": 3, "passed": 3, "failed": 0}}), encoding="utf-8"
        )
        (qa_dir / "test_plan.md").write_text("# 計画", encoding="utf-8")
    if testcases:
        tc = d / "testcases"
        tc.mkdir(exist_ok=True)
        (tc / "run_result.json").write_text(json.dumps({"summary": {"total": 2}}), encoding="utf-8")
    return d


class TestRunIdValidation:
    @pytest.mark.parametrize("rid", ["20260802-113000", "20260802-113000-2"])
    def test_accepts_timestamp_form(self, rid: str) -> None:
        assert valid_run_id(rid)

    @pytest.mark.parametrize(
        "rid", ["", "../etc", "20260802", "latest", "20260802-113000/..", "a" * 20]
    )
    def test_rejects_anything_else(self, rid: str) -> None:
        assert not valid_run_id(rid)

    def test_run_dir_is_none_for_bad_id(self, tmp_path: Path) -> None:
        assert run_dir(tmp_path, DOMAIN, "../../etc") is None


class TestNewRunId:
    def test_uses_timestamp(self, tmp_path: Path) -> None:
        rid = new_run_id(tmp_path, DOMAIN, now=datetime(2026, 8, 2, 11, 30, 0))
        assert rid == "20260802-113000"

    def test_same_second_does_not_collide(self, tmp_path: Path) -> None:
        now = datetime(2026, 8, 2, 11, 30, 0)
        first = new_run_id(tmp_path, DOMAIN, now=now)
        (tmp_path / DOMAIN / "runs" / first).mkdir(parents=True)
        second = new_run_id(tmp_path, DOMAIN, now=now)
        assert second != first
        assert second == "20260802-113000-2"


class TestSnapshot:
    def test_copies_artifacts_and_returns_run_id(self, tmp_path: Path) -> None:
        _make_artifacts(tmp_path)
        rid = snapshot_run(tmp_path, DOMAIN, event="crawl", now=datetime(2026, 8, 2, 11, 30, 0))
        assert rid == "20260802-113000"
        target = tmp_path / DOMAIN / "runs" / rid
        assert (target / "report.html").is_file()
        assert (target / "report.json").is_file()
        assert (target / "screens.md").is_file()
        assert (target / "meta.json").is_file()

    def test_each_run_keeps_its_own_copy(self, tmp_path: Path) -> None:
        """最新1件しか残らない問題が解消されていること（これが本丸）。"""
        d = _make_artifacts(tmp_path)
        (d / "report.json").write_text(json.dumps({"screens": [1, 2, 3]}), encoding="utf-8")
        first = snapshot_run(tmp_path, DOMAIN, event="crawl", now=datetime(2026, 8, 1, 10, 0, 0))
        # 2回目のクロールで現物が上書きされる（従来どおりの挙動）
        (d / "report.json").write_text(json.dumps({"screens": [1]}), encoding="utf-8")
        second = snapshot_run(tmp_path, DOMAIN, event="crawl", now=datetime(2026, 8, 2, 10, 0, 0))

        assert first != second
        first_json = json.loads(
            (tmp_path / DOMAIN / "runs" / first / "report.json").read_text(encoding="utf-8")
        )
        second_json = json.loads(
            (tmp_path / DOMAIN / "runs" / second / "report.json").read_text(encoding="utf-8")
        )
        assert len(first_json["screens"]) == 3
        assert len(second_json["screens"]) == 1

    def test_no_run_created_when_nothing_to_copy(self, tmp_path: Path) -> None:
        """成果物が1件も無いなら run を作らない（空の器を残さない）。"""
        (tmp_path / DOMAIN).mkdir(parents=True)
        assert snapshot_run(tmp_path, DOMAIN, event="crawl") is None
        assert not (tmp_path / DOMAIN / "runs").exists()

    def test_returns_none_for_unknown_domain(self, tmp_path: Path) -> None:
        assert snapshot_run(tmp_path, "nope.example", event="crawl") is None

    def test_artifact_flags_reflect_what_exists(self, tmp_path: Path) -> None:
        _make_artifacts(tmp_path)
        rid = snapshot_run(tmp_path, DOMAIN, event="crawl")
        meta = load_meta(tmp_path, DOMAIN, str(rid))
        assert meta is not None
        assert meta["artifacts"] == {"result": True, "analysis": True, "autorun": False}

    def test_autorun_flag_set_when_qa_artifacts_exist(self, tmp_path: Path) -> None:
        _make_artifacts(tmp_path, qa=True)
        rid = snapshot_run(tmp_path, DOMAIN, event="autorun")
        meta = load_meta(tmp_path, DOMAIN, str(rid))
        assert meta is not None
        assert meta["artifacts"]["autorun"] is True

    def test_summary_is_carried(self, tmp_path: Path) -> None:
        _make_artifacts(tmp_path)
        rid = snapshot_run(
            tmp_path, DOMAIN, event="crawl", summary={"screen_count": 6, "test_condition_count": 21}
        )
        meta = load_meta(tmp_path, DOMAIN, str(rid))
        assert meta is not None
        assert meta["summary"]["screen_count"] == 6

    def test_screenshots_are_not_copied(self, tmp_path: Path) -> None:
        """容量が上限なく膨らまないよう、スクリーンショットは退避しない。"""
        d = _make_artifacts(tmp_path)
        shots = d / "screenshots"
        shots.mkdir()
        (shots / "P001.png").write_bytes(b"\x89PNG")
        rid = snapshot_run(tmp_path, DOMAIN, event="crawl")
        assert not (tmp_path / DOMAIN / "runs" / str(rid) / "screenshots").exists()


class TestListing:
    def test_lists_newest_first(self, tmp_path: Path) -> None:
        _make_artifacts(tmp_path)
        snapshot_run(tmp_path, DOMAIN, event="crawl", now=datetime(2026, 7, 20, 9, 0, 0))
        snapshot_run(tmp_path, DOMAIN, event="crawl", now=datetime(2026, 8, 1, 9, 0, 0))
        runs = list_runs(tmp_path, DOMAIN)
        assert [r["run_id"] for r in runs] == ["20260801-090000", "20260720-090000"]

    def test_empty_when_no_runs(self, tmp_path: Path) -> None:
        assert list_runs(tmp_path, DOMAIN) == []

    def test_ignores_directories_without_meta(self, tmp_path: Path) -> None:
        _make_artifacts(tmp_path)
        snapshot_run(tmp_path, DOMAIN, event="crawl", now=datetime(2026, 8, 1, 9, 0, 0))
        (tmp_path / DOMAIN / "runs" / "20260101-000000").mkdir(parents=True)
        runs = list_runs(tmp_path, DOMAIN)
        assert [r["run_id"] for r in runs] == ["20260801-090000"]

    def test_latest_run_id(self, tmp_path: Path) -> None:
        _make_artifacts(tmp_path)
        snapshot_run(tmp_path, DOMAIN, event="crawl", now=datetime(2026, 7, 20, 9, 0, 0))
        snapshot_run(tmp_path, DOMAIN, event="crawl", now=datetime(2026, 8, 1, 9, 0, 0))
        assert latest_run_id(tmp_path, DOMAIN) == "20260801-090000"

    def test_latest_is_none_when_empty(self, tmp_path: Path) -> None:
        assert latest_run_id(tmp_path, DOMAIN) is None


class TestArtifactFile:
    def test_returns_path_for_existing_artifact(self, tmp_path: Path) -> None:
        _make_artifacts(tmp_path, qa=True)
        rid = str(snapshot_run(tmp_path, DOMAIN, event="autorun"))
        path = artifact_file(tmp_path, DOMAIN, rid, "qa_process/playwright_report.json")
        assert path is not None and path.is_file()

    def test_returns_none_for_missing_artifact(self, tmp_path: Path) -> None:
        _make_artifacts(tmp_path)
        rid = str(snapshot_run(tmp_path, DOMAIN, event="crawl"))
        assert artifact_file(tmp_path, DOMAIN, rid, "spec.xlsx") is None

    @pytest.mark.parametrize(
        "relative", ["../../etc/passwd", "screenshots/P001.png", "qa_process/../../secret"]
    )
    def test_rejects_paths_outside_the_allowlist(self, tmp_path: Path, relative: str) -> None:
        _make_artifacts(tmp_path)
        rid = str(snapshot_run(tmp_path, DOMAIN, event="crawl"))
        assert artifact_file(tmp_path, DOMAIN, rid, relative) is None

    def test_rejects_bad_run_id(self, tmp_path: Path) -> None:
        _make_artifacts(tmp_path)
        snapshot_run(tmp_path, DOMAIN, event="crawl")
        assert artifact_file(tmp_path, DOMAIN, "../..", "report.json") is None
