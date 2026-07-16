from __future__ import annotations

import json
from pathlib import Path

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
    workflow = Path(".github/workflows/spec-drift.yml").read_text(encoding="utf-8")

    assert "actions/cache/restore@v4" in workflow
    assert "actions/cache/save@v4" in workflow
    assert "output/**/snapshots" in workflow
    assert "--ci" in workflow
    assert "python scripts/notify_drift.py" in workflow
    assert "DRIFT_EXIT_CODE" in workflow
    assert 'exit "$DRIFT_EXIT_CODE"' in workflow
