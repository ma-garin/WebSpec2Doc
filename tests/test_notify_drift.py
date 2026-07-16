from __future__ import annotations

import json
from pathlib import Path

import yaml
from scripts import notify_drift


def _summary(path: Path, *, has_changes: bool = True, first_run: bool = False) -> Path:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "site_url": "https://example.com",
                "first_run": first_run,
                "has_changes": has_changes,
                "counts": {
                    "added_pages": 1,
                    "removed_pages": 2,
                    "field_changes": 3,
                    "link_changes": 4,
                    "title_changes": 5,
                    "api_changes": 6,
                },
                "severity_counts": {"breaking": 1, "warning": 2, "info": 3},
                "report_url": "output/example.com/diff_report.html",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_notify_drift_sends_real_summary_counts(tmp_path: Path, monkeypatch) -> None:
    summary_path = _summary(tmp_path / "drift_summary.json")
    captured = []

    def send(_config, notification) -> bool:
        captured.append(notification)
        return True

    monkeypatch.setattr(notify_drift, "send_drift_notification", send)

    exit_code = notify_drift.main(
        [str(summary_path)],
        environ={"SLACK_WEBHOOK_URL": "https://hooks.slack.invalid/private-token"},
    )

    assert exit_code == 0
    assert len(captured) == 1
    notification = captured[0]
    assert notification.added_pages == 1
    assert notification.removed_pages == 2
    assert notification.field_changes == 3
    assert notification.api_changes == 6


def test_notify_drift_skips_first_run_and_no_change(tmp_path: Path, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        notify_drift,
        "send_drift_notification",
        lambda *_args: calls.append(True) or True,
    )
    first = _summary(tmp_path / "first.json", first_run=True)
    unchanged = _summary(tmp_path / "unchanged.json", has_changes=False)

    assert notify_drift.main([str(first)], environ={"SLACK_WEBHOOK_URL": "secret"}) == 0
    assert notify_drift.main([str(unchanged)], environ={"SLACK_WEBHOOK_URL": "secret"}) == 0
    assert calls == []


def test_notify_drift_failure_is_exit_zero_and_does_not_print_secret(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    summary_path = _summary(tmp_path / "drift_summary.json")
    secret_url = "https://hooks.slack.invalid/private-token"
    monkeypatch.setattr(notify_drift, "send_drift_notification", lambda *_args: False)

    exit_code = notify_drift.main(
        [str(summary_path)],
        environ={"SLACK_WEBHOOK_URL": secret_url},
    )

    output = capsys.readouterr()
    assert exit_code == 0
    assert "送信に失敗" in output.err
    assert secret_url not in output.err
    assert secret_url not in output.out


def test_spec_drift_workflow_persists_snapshots_and_preserves_exit_code() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/spec-drift.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["detect-drift"]["steps"]
    by_name = {step["name"]: step for step in steps}

    assert by_name["Restore prior snapshots"]["uses"] == "actions/cache/restore@v4"
    assert by_name["Restore prior snapshots"]["with"]["path"] == "output/**/snapshots"
    assert "restore-keys" in by_name["Restore prior snapshots"]["with"]
    assert by_name["Save current snapshots"]["uses"] == "actions/cache/save@v4"
    assert by_name["Save current snapshots"]["with"]["path"] == "output/**/snapshots"
    assert by_name["Save current snapshots"]["if"] == (
        "env.DRIFT_EXIT_CODE == '0' || env.DRIFT_EXIT_CODE == '1'"
    )
    assert "--ci" in by_name["Run spec drift detection"]["run"]
    assert "DRIFT_EXIT_CODE" in by_name["Run spec drift detection"]["run"]
    assert "python scripts/notify_drift.py" in by_name["Notify drift (Slack)"]["run"]
    assert by_name["Notify drift (Slack)"]["if"] == "env.DRIFT_EXIT_CODE == '1'"
    assert (
        'exit "$DRIFT_EXIT_CODE"' in by_name["Preserve drift or execution failure exit code"]["run"]
    )


def test_generated_spec_workflow_runs_exported_playwright_spec() -> None:
    workflow = yaml.safe_load(
        Path(".github/workflows/generated-spec.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["run-generated-spec"]
    steps = {step["name"]: step for step in job["steps"]}

    assert job["env"]["SPEC_PATH"] == "${{ inputs.spec_path }}"
    assert steps["Checkout repository"]["uses"] == "actions/checkout@v4"
    assert steps["Set up Node.js"]["uses"] == "actions/setup-node@v4"
    assert "@playwright/test@1.61.0" in steps["Install Playwright"]["run"]
    assert 'playwright test "$SPEC_PATH"' in steps["Run generated spec"]["run"]
    assert steps["Upload Playwright report"]["uses"] == "actions/upload-artifact@v4"
