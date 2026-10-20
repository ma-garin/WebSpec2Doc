"""usage_tracker: ux_review.json の新旧キー互換（AC-W7b-1）。"""

from __future__ import annotations

import json

from web.services import usage_tracker


def _count(tmp_path, screens) -> int:
    path = tmp_path / "ux_review.json"
    path.write_text(json.dumps({"screens": screens}), encoding="utf-8")
    captured = {}

    def fake_record(root, **kw):
        captured.update(kw)
        return path

    original = usage_tracker.record_usage
    usage_tracker.record_usage = fake_record
    try:
        usage_tracker.record_ux_review_from_report(tmp_path, "d", path)
    finally:
        usage_tracker.record_usage = original
    return captured["finding_count"]


def test_new_key_preferred_without_double_count(tmp_path) -> None:
    v = [{"rule_id": "x"}]
    assert _count(tmp_path, [{"a11y_violations": v, "axe_violations": v, "ux_findings": [{}]}]) == 2


def test_old_key_only_still_counted(tmp_path) -> None:
    assert _count(tmp_path, [{"axe_violations": [{}, {}], "ux_findings": []}]) == 2


def test_missing_keys_do_not_raise(tmp_path) -> None:
    assert _count(tmp_path, [{}]) == 0
