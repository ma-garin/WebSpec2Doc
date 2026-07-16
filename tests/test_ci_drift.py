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
    assert lines[-1].startswith("CI_SUMMARY:")
    assert summary["error"] == "session_expired"
    assert summary["exit_code"] == 2


def test_ci_missing_target_is_execution_error(tmp_path: Path, capsys) -> None:
    args = _ci_args(tmp_path)
    args.url = None

    with pytest.raises(SystemExit) as exc_info:
        run(args)

    assert exc_info.value.code == 2
    summary = _ci_summary(capsys)
    assert summary["error"] == "missing_target"
    assert summary["exit_code"] == 2


def test_ci_axe_asset_error_ends_with_machine_summary(tmp_path: Path, capsys) -> None:
    from ux.axe_runner import AxeAssetError

    args = _ci_args(tmp_path)
    args.no_a11y_audit = False
    with (
        patch("ux.axe_runner.verify_axe_asset", side_effect=AxeAssetError("missing")),
        pytest.raises(SystemExit) as exc_info,
    ):
        run(args)

    lines = capsys.readouterr().out.splitlines()
    assert exc_info.value.code == 2
    assert "A11Y_AUDIT_ASSET_ERROR" in lines
    assert lines[-1].startswith("CI_SUMMARY:")
    assert json.loads(lines[-1][11:])["error"] == "accessibility_asset_error"


def test_ci_unexpected_exception_is_normalized_to_exit_two(capsys) -> None:
    import main as main_module

    args = argparse.Namespace(ci=True)
    with (
        patch("main.parse_args", return_value=args),
        patch("main.signal.signal"),
        patch("main.run", side_effect=RuntimeError("secret internal detail")),
        pytest.raises(SystemExit) as exc_info,
    ):
        main_module.main()

    assert exc_info.value.code == 2
    summary = _ci_summary(capsys)
    assert summary["error"] == "execution_error"


def test_ci_persists_drift_summary_before_report_generation_can_fail(tmp_path: Path) -> None:
    output_dir = tmp_path / "example.com"
    prior = output_dir / "snapshots" / "old.json"
    prior.parent.mkdir(parents=True)
    prior.write_text("[]", encoding="utf-8")

    with (
        patch("main.latest_snapshot", return_value=prior),
        patch("main.crawl_site", return_value=_fake_pages()),
        patch("main.save_outputs", side_effect=RuntimeError("report failed")),
        pytest.raises(RuntimeError),
    ):
        run(_ci_args(tmp_path))

    summary = json.loads((output_dir / "drift_summary.json").read_text(encoding="utf-8"))
    assert summary["first_run"] is False
    assert summary["has_changes"] is True
