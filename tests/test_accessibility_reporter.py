from __future__ import annotations

import json

from crawler.page_crawler import PageData, SourceEvidence
from generator.accessibility_reporter import (
    build_accessibility_audit,
    save_accessibility_audit,
)
from ux.axe_runner import AxeViolation


def test_build_accessibility_audit_is_rules_only_with_disclaimer() -> None:
    page = PageData(
        url="https://example.com/",
        title="Example",
        headings=(),
        links=(),
        forms=(),
        screenshot_path="screenshots/P001.png",
    )
    violation = AxeViolation(
        rule_id="image-alt",
        impact="critical",
        description="Ensures images have alternate text",
        wcag_tags=("wcag2a", "wcag111"),
        evidence=SourceEvidence(selector="img.hero", screenshot_path="screenshots/P001.png"),
        help_url="https://dequeuniversity.com/rules/axe/image-alt",
    )
    audit = build_accessibility_audit([page], {page.url: "P001"}, {page.url: (violation,)})
    assert audit["summary"]["violations"] == 1
    assert audit["summary"]["critical"] == 1
    assert audit["meta"]["engine"] == "axe-core"
    assert "手動確認" in audit["meta"]["disclaimer"]
    finding = audit["screens"][0]["violations"][0]
    assert finding["rule_id"] == "image-alt"
    assert finding["evidence"]["selector"] == "img.hero"
    assert finding["help_url"] == "https://dequeuniversity.com/rules/axe/image-alt"
    assert finding["confidence"] == 1.0


def test_save_accessibility_audit_writes_independent_json(tmp_path) -> None:
    payload = {
        "meta": {"engine": "axe-core", "disclaimer": "手動確認が必要"},
        "summary": {"violations": 0},
        "screens": [],
    }
    path = save_accessibility_audit(payload, tmp_path)
    assert path.name == "accessibility_audit.json"
    assert json.loads(path.read_text(encoding="utf-8")) == payload
