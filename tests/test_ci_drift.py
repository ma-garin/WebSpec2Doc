"""CI ドリフトモードの終了コードと機械可読出力を検証する。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crawler.page_crawler import PageData
from crawler.session_guard import SessionExpiredError
from main import run


def _fake_pages() -> list[PageData]:
    return [
        PageData(
            url="https://example.com/",
            title="Top",
            headings=(),
            links=(),
            forms=(),
            screenshot_path=None,
        )
    ]


def _ci_args(tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        url="https://example.com/",
        urls=None,
        depth=1,
        max_pages=2,
        output=tmp_path,
        llm=False,
        format="json",
        compare=True,
        fail_on_drift=True,
        ci=True,
        no_a11y_audit=True,
        auth=None,
        login=None,
        login_signal=None,
        discover=False,
        login_simple=False,
        login_scrape=None,
        login_submit=False,
    )


def _ci_summary(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    lines = [
        line for line in capsys.readouterr().out.splitlines() if line.startswith("CI_SUMMARY:")
    ]
    assert len(lines) == 1
    return json.loads(lines[0].removeprefix("CI_SUMMARY:"))


def test_ci_mode_emits_one_line_machine_readable_summary(tmp_path: Path, capsys) -> None:
    output_dir = tmp_path / "example.com"
    with (
        patch("main.latest_snapshot", return_value=None),
        patch("main.crawl_site", return_value=_fake_pages()),
        patch("main.save_snapshot", return_value=output_dir / "snapshots" / "new.json"),
    ):
        run(_ci_args(tmp_path))

    summary = _ci_summary(capsys)
    assert summary["first_run"] is True
    assert summary["has_changes"] is False
    assert summary["exit_code"] == 0


def test_ci_mode_emits_summary_before_drift_exit_one(tmp_path: Path, capsys) -> None:
    output_dir = tmp_path / "example.com"

    def drift(*_args) -> bool:
        (output_dir / "drift_summary.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "first_run": False,
                    "has_changes": True,
                    "counts": {"field_changes": 3},
                }
            ),
            encoding="utf-8",
        )
        return True

    with (
        patch("main.latest_snapshot", return_value=output_dir / "snapshots" / "old.json"),
        patch("main.crawl_site", return_value=_fake_pages()),
        patch("main.save_snapshot", return_value=output_dir / "snapshots" / "new.json"),
        patch("main._save_diff_report", side_effect=drift),
        pytest.raises(SystemExit) as exc_info,
    ):
        run(_ci_args(tmp_path))

    summary = _ci_summary(capsys)
    assert exc_info.value.code == 1
    assert summary["has_changes"] is True
    assert summary["counts"]["field_changes"] == 3
    assert summary["exit_code"] == 1


def test_ci_mode_uses_exit_two_for_execution_failure(tmp_path: Path, capsys) -> None:
    with (
        patch("main.latest_snapshot", return_value=None),
        patch("main.crawl_site", return_value=[]),
        pytest.raises(SystemExit) as exc_info,
    ):
        run(_ci_args(tmp_path))

    assert exc_info.value.code == 2
    assert _ci_summary(capsys) == {
        "error": "no_pages_crawled",
        "exit_code": 2,
        "has_changes": False,
        "version": 1,
    }


def test_ci_session_expired_emits_execution_error_summary(tmp_path: Path, capsys) -> None:
    with (
        patch("main.latest_snapshot", return_value=None),
        patch("main.crawl_site", side_effect=SessionExpiredError("expired")),
        pytest.raises(SystemExit) as exc_info,
    ):
        run(_ci_args(tmp_path))

    lines = capsys.readouterr().out.splitlines()
    summary = json.loads(next(line for line in lines if line.startswith("CI_SUMMARY:"))[11:])
    assert exc_info.value.code == 2
    assert "SESSION_EXPIRED" in lines
    assert summary["error"] == "session_expired"
    assert summary["exit_code"] == 2
