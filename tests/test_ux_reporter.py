"""ux_review.json 出力層（generator.ux_reporter）と report.json 非破壊性（AC-7）のテスト。"""

from __future__ import annotations

import json
from dataclasses import dataclass

from analyzer.html_analyzer import analyze_pages
from crawler.page_crawler import FieldData, FormData, PageData
from generator.json_reporter import generate_json_report
from generator.ux_reporter import (
    build_ux_review,
    build_ux_screen_info,
    save_ux_outputs,
)
from graph.transition_graph import build_graph
from ux.a11y.models import NodeResult, PageA11yResult, RuleResult
from ux.heuristics import pop_hallucination_drop_count


@dataclass(frozen=True)
class _LegacyViolation:
    """旧形式（違反オブジェクトのタプル）入力の互換確認用。"""

    rule_id: str
    impact: str
    description: str
    wcag_tags: tuple
    evidence: object
    help_url: str = ""
    confidence: float = 1.0


def _native_result(url: str) -> PageA11yResult:
    node = NodeResult(status="violation", selector="img.hero", impact="critical", message="alt なし")
    return PageA11yResult(
        url=url,
        rules=(
            RuleResult("name.image", "violation", (node,), {"violation": 1}),
            RuleResult("bp.region", "not_implemented", (), {}),
        ),
    )


def _sample_page(url: str = "https://example.com/") -> PageData:
    field = FieldData(
        field_type="text",
        name="q",
        placeholder="",
        required=False,
        has_visible_label=False,
    )
    form = FormData(action="/search", method="get", fields=(field,))
    return PageData(
        url=url,
        title="Example",
        headings=("Example",),
        links=(),
        forms=(form,),
        screenshot_path=None,
    )


class TestReportJsonUnchangedWithoutUxReview:
    def test_report_json_unchanged_without_ux_review(self) -> None:
        """--ux-review 未指定相当のクロール結果は report.json に UX 関連キーを含まない（AC-7）。"""
        page_data = _sample_page()
        analyzed = analyze_pages([page_data])
        graph = build_graph(analyzed)

        report_json = generate_json_report(analyzed, graph, page_data.url)

        assert "ux_review" not in report_json
        assert "axe_violations" not in report_json
        assert "ux_findings" not in report_json
        # スキーマの JSON としての妥当性も確認する
        parsed = json.loads(report_json)
        assert "meta" in parsed
        assert "screens" in parsed


class TestBuildUxScreenInfo:
    def test_known_selectors_include_field_and_axe_selectors(self) -> None:
        """known_selectors にフィールド・axe 違反双方のセレクタが含まれる（幻覚フィルタの土台）。"""
        page_data = _sample_page()
        field_selector = page_data.forms[0].fields[0].evidence
        assert field_selector is None  # DOM 実測なしのユニットフィクスチャでは evidence 無し

        from crawler.page_crawler import SourceEvidence

        violation = _LegacyViolation(
            rule_id="label",
            impact="serious",
            description="desc",
            wcag_tags=("wcag2a",),
            evidence=SourceEvidence(selector="#axe-target"),
        )

        screen_info = build_ux_screen_info(page_data, (violation,))

        assert "#axe-target" in screen_info["known_selectors"]
        assert screen_info["title"] == "Example"
        assert screen_info["axe_violation_summary"][0]["rule_id"] == "label"


class TestBuildAndSaveUxReview:
    def test_build_ux_review_combines_axe_and_findings_per_screen(self) -> None:
        pop_hallucination_drop_count()
        page_data = _sample_page()
        from crawler.page_crawler import SourceEvidence

        violation = _LegacyViolation(
            rule_id="image-alt",
            impact="critical",
            description="desc",
            wcag_tags=("wcag2a",),
            evidence=SourceEvidence(selector="img"),
        )
        axe_results = {page_data.url: (violation,)}
        ux_findings = {
            page_data.url: [
                {
                    "principle": "N6",
                    "severity": "high",
                    "finding": "所見",
                    "evidence": {"selector": "#q"},
                    "source": "rules",
                    "confidence": 1.0,
                }
            ]
        }
        page_ids = {page_data.url: "P001"}

        review = build_ux_review([page_data], page_ids, axe_results, ux_findings)

        assert review["meta"]["disclaimer"]
        assert review["meta"]["hallucination_dropped_count"] == 0
        assert len(review["screens"]) == 1
        screen = review["screens"][0]
        assert screen["page_id"] == "P001"
        assert len(screen["axe_violations"]) == 1
        assert len(screen["ux_findings"]) == 1

    def test_save_ux_outputs_writes_json_file(self, tmp_path) -> None:
        review = {"meta": {"disclaimer": "d", "hallucination_dropped_count": 0}, "screens": []}

        path = save_ux_outputs(review, tmp_path)

        assert path.exists()
        assert path.name == "ux_review.json"
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded == review


class TestNativeResultInput:
    def test_native_result_fills_new_and_legacy_keys(self) -> None:
        page = _sample_page()
        review = build_ux_review([page], {page.url: "P001"}, {page.url: _native_result(page.url)}, {})
        screen = review["screens"][0]
        assert screen["a11y_violations"] == screen["axe_violations"]
        assert screen["a11y_violations"][0]["rule_id"] == "image-alt"
        assert screen["a11y_violations"][0]["native_rule_id"] == "name.image"
        statuses = {r["rule_id"]: r["status"] for r in screen["a11y_rule_results"]}
        assert statuses["bp.region"] == "not_implemented"

    def test_screen_info_accepts_native_result(self) -> None:
        page = _sample_page()
        info = build_ux_screen_info(page, _native_result(page.url))
        assert "img.hero" in info["known_selectors"]
        assert info["axe_violation_summary"][0]["rule_id"] == "image-alt"
