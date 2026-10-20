from __future__ import annotations

import json
from dataclasses import dataclass

from crawler.page_crawler import PageData, SourceEvidence
from generator.accessibility_reporter import (
    build_accessibility_audit,
    coverage_notice,
    save_accessibility_audit,
    unevaluated_rules,
)
from ux.a11y.models import NodeResult, PageA11yResult, RuleResult


@dataclass(frozen=True)
class _LegacyViolation:
    rule_id: str
    impact: str
    description: str
    wcag_tags: tuple
    evidence: SourceEvidence
    help_url: str = ""
    confidence: float = 1.0


def _page() -> PageData:
    return PageData(
        url="https://example.com/",
        title="Example",
        headings=(),
        links=(),
        forms=(),
        screenshot_path="screenshots/P001.png",
    )


def _native(url: str) -> PageA11yResult:
    bad = NodeResult(status="violation", selector="img.hero", impact="critical", message="alt なし")
    ok = NodeResult(status="pass", selector="title")
    return PageA11yResult(
        url=url,
        rules=(
            RuleResult("name.image", "violation", (bad,), {"violation": 1}),
            RuleResult("doc.title", "pass", (ok,), {"pass": 1}),
            RuleResult("visual.contrast", "cant_tell", (), {}),
            RuleResult("bp.region", "not_implemented", (), {}),
        ),
    )


def test_native_result_has_three_states_and_coverage() -> None:
    page = _page()
    audit = build_accessibility_audit([page], {page.url: "P001"}, {page.url: _native(page.url)})
    assert audit["meta"]["engine"] == "webspec2doc-native-a11y"
    assert set(audit["meta"]["coverage"]) == {"implemented", "partial", "not_implemented"}
    assert "axe" not in json.dumps(audit["meta"], ensure_ascii=False).lower()
    summary = audit["summary"]
    assert (summary["violations"], summary["critical"]) == (1, 1)
    assert (summary["passed"], summary["cant_tell"], summary["not_implemented"]) == (1, 1, 1)
    screen = audit["screens"][0]
    assert {r["rule_id"]: r["status"] for r in screen["rule_results"]}["bp.region"] == "not_implemented"
    finding = screen["violations"][0]
    assert finding["rule_id"] == "image-alt"
    assert finding["evidence"]["selector"] == "img.hero"
    assert finding["evidence"]["screenshot_path"] == "screenshots/P001.png"
    assert finding["confidence"] == 1.0


def test_zero_violations_is_not_reported_as_clean() -> None:
    page = _page()
    result = PageA11yResult(
        url=page.url, rules=(RuleResult("bp.region", "not_implemented", (), {}),)
    )
    audit = build_accessibility_audit([page], {}, {page.url: result})
    assert audit["summary"]["violations"] == 0
    assert "未実装" in coverage_notice(audit)
    assert [r["rule_id"] for r in unevaluated_rules(audit)] == ["bp.region"]


def test_error_is_kept_on_screen() -> None:
    page = _page()
    result = PageA11yResult(url=page.url, rules=(), error="取得失敗")
    audit = build_accessibility_audit([page], {}, {page.url: result})
    assert audit["screens"][0]["error"] == "取得失敗"


def test_legacy_tuple_input_still_supported() -> None:
    page = _page()
    violation = _LegacyViolation(
        rule_id="image-alt",
        impact="critical",
        description="Ensures images have alternate text",
        wcag_tags=("wcag2a", "wcag111"),
        evidence=SourceEvidence(selector="img.hero", screenshot_path="screenshots/P001.png"),
    )
    audit = build_accessibility_audit([page], {page.url: "P001"}, {page.url: (violation,)})
    assert audit["summary"]["violations"] == 1
    assert audit["screens"][0]["violations"][0]["rule_id"] == "image-alt"
    assert audit["screens"][0]["rule_results"] == []
    assert "手動確認" in audit["meta"]["disclaimer"]


def test_save_accessibility_audit_writes_independent_json(tmp_path) -> None:
    payload = {
        "meta": {"engine": "webspec2doc-native-a11y", "disclaimer": "手動確認が必要"},
        "summary": {"violations": 0},
        "screens": [],
    }
    path = save_accessibility_audit(payload, tmp_path)
    assert path.name == "accessibility_audit.json"
    assert json.loads(path.read_text(encoding="utf-8")) == payload
