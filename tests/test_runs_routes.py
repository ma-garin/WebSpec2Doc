"""実行回ごとの成果物を返すルート（web/routes/runs.py）のテスト。

守りたいこと:
  - 実行回ごとに別の中身が返る（最新1件しか無かった問題の解消）
  - 保存されていない実行回は「無い」と返し、最新で代替しない
  - run_id / ドメインで経路トラバーサルできない
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from web.services.run_store import snapshot_run  # noqa: E402

DOMAIN = "example.com"


def _client():
    import app as appmod

    return appmod.app.test_client()


def _make_run(root: Path, *, screens: int, when: datetime, qa: bool = False) -> str:
    d = root / DOMAIN
    d.mkdir(parents=True, exist_ok=True)
    (d / "report.html").write_text(f"<html>{screens}画面</html>", encoding="utf-8")
    (d / "report.json").write_text(
        json.dumps({"screens": [{"page_id": f"P{i:03d}"} for i in range(screens)]}),
        encoding="utf-8",
    )
    if qa:
        qa_dir = d / "qa_process"
        qa_dir.mkdir(exist_ok=True)
        (qa_dir / "playwright_report.json").write_text(
            json.dumps({"summary": {"total": 3, "passed": 3, "failed": 0}}), encoding="utf-8"
        )
    rid = snapshot_run(root, DOMAIN, event="crawl", summary={"screens": screens}, now=when)
    assert rid is not None
    return rid


class TestRunListing:
    def test_lists_runs_newest_first(self, tmp_path: Path) -> None:
        old = _make_run(tmp_path, screens=3, when=datetime(2026, 7, 20, 9, 0, 0))
        new = _make_run(tmp_path, screens=6, when=datetime(2026, 8, 1, 9, 0, 0))
        with patch("web.routes.runs.OUTPUT_DIR", tmp_path):
            res = _client().get(f"/api/runs/{DOMAIN}")
        data = res.get_json()
        assert res.status_code == 200
        assert [r["run_id"] for r in data["runs"]] == [new, old]
        assert data["current_run_id"] == new
        assert data["total"] == 2

    def test_empty_for_site_without_runs(self, tmp_path: Path) -> None:
        (tmp_path / DOMAIN).mkdir(parents=True)
        with patch("web.routes.runs.OUTPUT_DIR", tmp_path):
            res = _client().get(f"/api/runs/{DOMAIN}")
        assert res.get_json() == {
            "domain": DOMAIN,
            "runs": [],
            "current_run_id": "",
            "total": 0,
        }

    def test_rejects_invalid_domain(self, tmp_path: Path) -> None:
        with patch("web.routes.runs.OUTPUT_DIR", tmp_path):
            res = _client().get("/api/runs/..%2F..%2Fetc")
        assert res.status_code == 404


class TestRunDetail:
    def test_each_run_returns_its_own_content(self, tmp_path: Path) -> None:
        """本丸: 7月の実行を開いたら7月の中身が返ること。"""
        old = _make_run(tmp_path, screens=3, when=datetime(2026, 7, 20, 9, 0, 0))
        new = _make_run(tmp_path, screens=6, when=datetime(2026, 8, 1, 9, 0, 0))
        with patch("web.routes.runs.OUTPUT_DIR", tmp_path):
            c = _client()
            old_json = Path(c.get(f"/api/runs/{DOMAIN}/{old}").get_json()["files"]["json"])
            new_json = Path(c.get(f"/api/runs/{DOMAIN}/{new}").get_json()["files"]["json"])
        assert len(json.loads(old_json.read_text(encoding="utf-8"))["screens"]) == 3
        assert len(json.loads(new_json.read_text(encoding="utf-8"))["screens"]) == 6

    def test_artifact_flags(self, tmp_path: Path) -> None:
        rid = _make_run(tmp_path, screens=2, when=datetime(2026, 8, 1, 9, 0, 0))
        with patch("web.routes.runs.OUTPUT_DIR", tmp_path):
            data = _client().get(f"/api/runs/{DOMAIN}/{rid}").get_json()
        assert data["artifacts"] == {"result": True, "analysis": True, "autorun": False}

    def test_autorun_flag_when_qa_artifacts_exist(self, tmp_path: Path) -> None:
        rid = _make_run(tmp_path, screens=2, when=datetime(2026, 8, 1, 9, 0, 0), qa=True)
        with patch("web.routes.runs.OUTPUT_DIR", tmp_path):
            data = _client().get(f"/api/runs/{DOMAIN}/{rid}").get_json()
        assert data["artifacts"]["autorun"] is True

    def test_neighbours_for_selector(self, tmp_path: Path) -> None:
        old = _make_run(tmp_path, screens=3, when=datetime(2026, 7, 20, 9, 0, 0))
        mid = _make_run(tmp_path, screens=4, when=datetime(2026, 7, 25, 9, 0, 0))
        new = _make_run(tmp_path, screens=6, when=datetime(2026, 8, 1, 9, 0, 0))
        with patch("web.routes.runs.OUTPUT_DIR", tmp_path):
            data = _client().get(f"/api/runs/{DOMAIN}/{mid}").get_json()
        assert data["newer_run_id"] == new
        assert data["older_run_id"] == old
        assert data["is_current"] is False
        assert data["position"] == {"index": 2, "total": 3}

    def test_current_run_is_marked(self, tmp_path: Path) -> None:
        _make_run(tmp_path, screens=3, when=datetime(2026, 7, 20, 9, 0, 0))
        new = _make_run(tmp_path, screens=6, when=datetime(2026, 8, 1, 9, 0, 0))
        with patch("web.routes.runs.OUTPUT_DIR", tmp_path):
            data = _client().get(f"/api/runs/{DOMAIN}/{new}").get_json()
        assert data["is_current"] is True
        assert data["newer_run_id"] == ""

    def test_unsaved_run_is_404_and_does_not_fall_back_to_latest(self, tmp_path: Path) -> None:
        """保存されていない実行回で最新を代わりに返さないこと。"""
        _make_run(tmp_path, screens=6, when=datetime(2026, 8, 1, 9, 0, 0))
        with patch("web.routes.runs.OUTPUT_DIR", tmp_path):
            res = _client().get(f"/api/runs/{DOMAIN}/20260101-000000")
        assert res.status_code == 404
        body = res.get_json()
        assert "保存されていません" in body["error"]
        assert "files" not in body

    @pytest.mark.parametrize("rid", ["latest", "..", "20260802"])
    def test_rejects_invalid_run_id(self, tmp_path: Path, rid: str) -> None:
        with patch("web.routes.runs.OUTPUT_DIR", tmp_path):
            res = _client().get(f"/api/runs/{DOMAIN}/{rid}")
        assert res.status_code in (400, 404)


class TestArtifactEndpoint:
    def test_returns_path_for_existing_artifact(self, tmp_path: Path) -> None:
        rid = _make_run(tmp_path, screens=2, when=datetime(2026, 8, 1, 9, 0, 0))
        with patch("web.routes.runs.OUTPUT_DIR", tmp_path):
            res = _client().get(f"/api/runs/{DOMAIN}/{rid}/artifact?name=report.html")
        assert res.status_code == 200
        assert Path(res.get_json()["path"]).is_file()

    def test_404_for_missing_artifact(self, tmp_path: Path) -> None:
        rid = _make_run(tmp_path, screens=2, when=datetime(2026, 8, 1, 9, 0, 0))
        with patch("web.routes.runs.OUTPUT_DIR", tmp_path):
            res = _client().get(f"/api/runs/{DOMAIN}/{rid}/artifact?name=spec.xlsx")
        assert res.status_code == 404

    @pytest.mark.parametrize("name", ["../../../etc/passwd", "screenshots/a.png", ""])
    def test_rejects_paths_outside_allowlist(self, tmp_path: Path, name: str) -> None:
        rid = _make_run(tmp_path, screens=2, when=datetime(2026, 8, 1, 9, 0, 0))
        with patch("web.routes.runs.OUTPUT_DIR", tmp_path):
            res = _client().get(f"/api/runs/{DOMAIN}/{rid}/artifact?name={name}")
        assert res.status_code == 404


class TestRunPage:
    def test_serves_spa_for_existing_run(self, tmp_path: Path) -> None:
        rid = _make_run(tmp_path, screens=2, when=datetime(2026, 8, 1, 9, 0, 0))
        with patch("web.routes.runs.OUTPUT_DIR", tmp_path):
            res = _client().get(f"/runs/{DOMAIN}/{rid}")
        assert res.status_code == 200

    def test_404_for_unknown_run(self, tmp_path: Path) -> None:
        (tmp_path / DOMAIN).mkdir(parents=True)
        with patch("web.routes.runs.OUTPUT_DIR", tmp_path):
            res = _client().get(f"/runs/{DOMAIN}/20260101-000000")
        assert res.status_code == 404
