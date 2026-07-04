"""SPEC-1-2: 業務ルールのテスト観点・境界値注入（Doc Fusion Phase 2）のテスト。

対象:
    - src/analyzer/rule_injector.py::build_rule_conditions / boundary_conditions_from_limit
    - src/ingest/matcher.py::fuse の limit ルール矛盾検出（_rule_mismatches）
    - src/generator/json_reporter.py の rule_conditions 注入（オプトイン）
"""

from __future__ import annotations

from networkx import DiGraph

from analyzer.html_analyzer import analyze_pages
from analyzer.rule_injector import boundary_conditions_from_limit, build_rule_conditions
from analyzer.test_conditions import SOURCE_DOCUMENT
from crawler.page_crawler import FieldData, FormData, PageData, SourceEvidence
from generator.json_reporter import generate_json_report
from ingest.matcher import fuse
from ingest.models import DocumentBundle, DocumentedRule, DocumentedScreen, DocumentEvidence


def _field(
    name: str,
    aria_label: str = "",
    maxlength: int | None = None,
    max_value: str = "",
    field_type: str = "text",
) -> FieldData:
    return FieldData(
        field_type=field_type,
        name=name,
        placeholder="",
        required=False,
        maxlength=maxlength,
        max_value=max_value,
        aria_label=aria_label,
        evidence=SourceEvidence(selector=f"[name='{name}']"),
    )


def _page(url: str, title: str, fields: tuple[FieldData, ...] = ()) -> PageData:
    forms = (FormData(action="/submit", method="post", fields=fields),) if fields else ()
    return PageData(
        url=url, title=title, headings=(title,), links=(), forms=forms, screenshot_path=None
    )


def _rule(
    kind: str,
    expression: str = "",
    screen_name: str = "振込画面",
    field_name: str = "",
    confidence: float = 0.9,
) -> DocumentedRule:
    return DocumentedRule(
        rule_id="RULE-001",
        kind=kind,
        description="振込限度額",
        screen_name=screen_name,
        field_name=field_name,
        expression=expression,
        confidence=confidence,
        evidence=DocumentEvidence(file="spec.pdf", location="line 2", quote="振込限度額は…"),
    )


def _screen(name: str = "振込画面") -> DocumentedScreen:
    return DocumentedScreen(screen_id="GA-001", name=name, url_hint="/transfer")


def _fuse_with(page: PageData, rules: tuple[DocumentedRule, ...]):
    analyzed = analyze_pages([page])
    bundle = DocumentBundle(
        screens=(_screen(),), fields=(), source_files=("spec.pdf",), rules=rules
    )
    result = fuse(analyzed, bundle)
    return analyzed, bundle, result


class TestBoundaryConditionsFromLimit:
    def test_limit_rule_injected_as_boundary(self) -> None:
        """限度値ルール（数値化可能）が境界値 3 点の条件文になる。"""
        rule = _rule(kind="limit", expression="1000000", field_name="振込金額")
        conditions = boundary_conditions_from_limit(rule)
        assert conditions == ("文書ルール境界値(1000000): 999999/1000000/1000001",)

    def test_unit_word_expression_not_guessed(self) -> None:
        """単位語（万円）を伴う expression は推測せず境界値化しない。"""
        rule = _rule(kind="limit", expression="100万円/日", field_name="振込金額")
        assert boundary_conditions_from_limit(rule) == ()

    def test_unparsable_expression(self) -> None:
        rule = _rule(kind="limit", expression="別表参照", field_name="振込金額")
        assert boundary_conditions_from_limit(rule) == ()


class TestBuildRuleConditions:
    def test_limit_rule_injected_to_field(self) -> None:
        """限度値ルールが対応フィールドの (page_id, field_name) キーへ注入される。"""
        page = _page("https://example.com/transfer", "振込画面", (_field("振込金額"),))
        rule = _rule(kind="limit", expression="1000000", field_name="振込金額")
        analyzed, bundle, result = _fuse_with(page, (rule,))
        conditions = build_rule_conditions(result, bundle, analyzed)
        page_id = analyzed[0].page_id
        key = (page_id, "振込金額")
        assert key in conditions
        assert conditions[key][0].source == SOURCE_DOCUMENT
        assert "999999/1000000/1000001" in conditions[key][0].description

    def test_calculation_rule_page_level(self) -> None:
        """field_name 空の計算式ルールは (page_id, "") のページレベルに載る。"""
        page = _page("https://example.com/transfer", "振込画面", ())
        rule = _rule(kind="calculation", expression="税額 = 課税対象額 × 10%", field_name="")
        analyzed, bundle, result = _fuse_with(page, (rule,))
        conditions = build_rule_conditions(result, bundle, analyzed)
        page_id = analyzed[0].page_id
        key = (page_id, "")
        assert key in conditions
        assert "税額 = 課税対象額 × 10%" in conditions[key][0].description

    def test_injected_confidence_capped(self) -> None:
        page = _page("https://example.com/transfer", "振込画面", (_field("振込金額"),))
        rule = _rule(kind="limit", expression="1000000", field_name="振込金額", confidence=0.9)
        analyzed, bundle, result = _fuse_with(page, (rule,))
        conditions = build_rule_conditions(result, bundle, analyzed)
        condition = conditions[(analyzed[0].page_id, "振込金額")][0]
        assert condition.confidence == 0.9
        assert condition.doc_evidence is not None
        assert condition.doc_evidence.file == "spec.pdf"

    def test_unmatched_rule_logged(self, caplog) -> None:
        """対応画面が無いルールは注入されない。"""
        page = _page("https://example.com/transfer", "振込画面", (_field("振込金額"),))
        rule = _rule(kind="limit", expression="1000000", screen_name="実在しない画面")
        analyzed, bundle, result = _fuse_with(page, (rule,))
        with caplog.at_level("WARNING"):
            conditions = build_rule_conditions(result, bundle, analyzed)
        assert conditions == {}
        assert "注入先画面なし" in caplog.text

    def test_rule_without_evidence_excluded(self) -> None:
        """evidence の無いルールは条件を生成しない。"""
        page = _page("https://example.com/transfer", "振込画面", (_field("振込金額"),))
        rule = DocumentedRule(
            rule_id="RULE-002",
            kind="limit",
            description="限度額",
            screen_name="振込画面",
            field_name="振込金額",
            expression="1000000",
            evidence=None,
        )
        analyzed, bundle, result = _fuse_with(page, (rule,))
        conditions = build_rule_conditions(result, bundle, analyzed)
        assert conditions == {}


class TestRuleMismatchDetection:
    def test_limit_mismatch_gap(self) -> None:
        """文書の限度値と実測 maxlength が矛盾すると FieldGap(mismatch) が追加される。"""
        page = _page("https://example.com/transfer", "振込画面", (_field("振込金額", maxlength=7),))
        rule = _rule(kind="limit", expression="1000000", field_name="振込金額")
        _, _, result = _fuse_with(page, (rule,))
        mismatches = [g for g in result.field_gaps if g.kind == "mismatch"]
        assert len(mismatches) == 1
        assert "1000000" in mismatches[0].detail
        assert "7" in mismatches[0].detail

    def test_no_mismatch_when_values_agree(self) -> None:
        page = _page(
            "https://example.com/transfer", "振込画面", (_field("振込金額", maxlength=1000000),)
        )
        rule = _rule(kind="limit", expression="1000000", field_name="振込金額")
        _, _, result = _fuse_with(page, (rule,))
        assert [g for g in result.field_gaps if g.kind == "mismatch"] == []


class TestRuleMismatchUnitSelection:
    """数値型フィールドは max_value、それ以外は maxlength とのみ比較する
    （桁数と値という異なる単位を混同した偽の矛盾検出を防ぐ）。"""

    def test_number_field_matches_via_max_value_ignores_maxlength(self) -> None:
        page = _page(
            "https://example.com/transfer",
            "振込画面",
            (_field("上限額", maxlength=4, max_value="9999", field_type="number"),),
        )
        rule = _rule(kind="limit", expression="9999", field_name="上限額")
        _, _, result = _fuse_with(page, (rule,))
        assert [g for g in result.field_gaps if g.kind == "mismatch"] == []

    def test_number_field_max_value_mismatch_still_detected(self) -> None:
        page = _page(
            "https://example.com/transfer",
            "振込画面",
            (_field("上限額", max_value="5000", field_type="number"),),
        )
        rule = _rule(kind="limit", expression="9999", field_name="上限額")
        _, _, result = _fuse_with(page, (rule,))
        mismatches = [g for g in result.field_gaps if g.kind == "mismatch"]
        assert len(mismatches) == 1
        assert "max_value" in mismatches[0].detail


class TestEmptyScreenNameNotWildcard:
    def test_empty_screen_name_rule_not_matched_to_any_screen(self) -> None:
        """screen_name が空のルールは、screen_id も空の画面へ誤マッチしない。"""
        page = _page("https://example.com/transfer", "振込画面", (_field("振込金額", maxlength=7),))
        screen = DocumentedScreen(screen_id="", name="振込画面", url_hint="/transfer")
        analyzed = analyze_pages([page])
        rule = _rule(kind="limit", expression="1000000", screen_name="", field_name="振込金額")
        bundle = DocumentBundle(
            screens=(screen,), fields=(), source_files=("spec.pdf",), rules=(rule,)
        )
        result = fuse(analyzed, bundle)
        assert [g for g in result.field_gaps if g.kind == "mismatch"] == []


class TestJsonReporterOptIn:
    def _graph_for(self, page_id: str) -> DiGraph:
        graph = DiGraph()
        graph.add_node(page_id)
        return graph

    def test_no_rules_no_schema_change(self) -> None:
        """rule_conditions=None なら report.json が既存実装と同一の構造。"""
        page = _page("https://example.com/transfer", "振込画面", (_field("振込金額"),))
        analyzed = analyze_pages([page])
        graph = self._graph_for(analyzed[0].page_id)
        with_none = generate_json_report(
            analyzed, graph, "https://example.com/", rule_conditions=None
        )
        without_arg = generate_json_report(analyzed, graph, "https://example.com/")
        assert with_none == without_arg
        assert "document_conditions" not in with_none
        assert '"doc_evidence"' not in with_none

    def test_dom_conditions_unchanged_with_injection(self) -> None:
        """文書由来条件の注入があっても DOM 由来条件は件数・内容とも不変。"""
        import json

        page = _page(
            "https://example.com/transfer", "振込画面", (_field("振込金額", maxlength=10),)
        )
        analyzed = analyze_pages([page])
        graph = self._graph_for(analyzed[0].page_id)
        page_id = analyzed[0].page_id

        baseline = json.loads(generate_json_report(analyzed, graph, "https://example.com/"))
        rule = _rule(kind="limit", expression="1000000", field_name="振込金額")
        bundle = DocumentBundle(
            screens=(_screen(),), fields=(), source_files=("spec.pdf",), rules=(rule,)
        )
        result = fuse(analyzed, bundle)
        rule_conditions = build_rule_conditions(result, bundle, analyzed)
        injected = json.loads(
            generate_json_report(
                analyzed, graph, "https://example.com/", rule_conditions=rule_conditions
            )
        )

        baseline_field = baseline["screens"][0]["forms"][0]["fields"][0]
        injected_field = injected["screens"][0]["forms"][0]["fields"][0]
        baseline_dom_conditions = baseline_field["test_conditions_detail"]
        injected_dom_conditions = [
            c for c in injected_field["test_conditions_detail"] if c["source"] != SOURCE_DOCUMENT
        ]
        assert baseline_dom_conditions == injected_dom_conditions

        doc_conditions = [
            c for c in injected_field["test_conditions_detail"] if c["source"] == SOURCE_DOCUMENT
        ]
        assert len(doc_conditions) == 1
        assert doc_conditions[0]["doc_evidence"]["file"] == "spec.pdf"
        assert page_id  # サニティ

    def test_page_level_document_conditions_key(self) -> None:
        """ページレベル条件は screens[].document_conditions にのみ載る。"""
        import json

        page = _page("https://example.com/transfer", "振込画面", ())
        analyzed = analyze_pages([page])
        graph = self._graph_for(analyzed[0].page_id)
        rule = _rule(kind="calculation", expression="税額 = 課税対象額 × 10%", field_name="")
        bundle = DocumentBundle(
            screens=(_screen(),), fields=(), source_files=("spec.pdf",), rules=(rule,)
        )
        result = fuse(analyzed, bundle)
        rule_conditions = build_rule_conditions(result, bundle, analyzed)
        data = json.loads(
            generate_json_report(
                analyzed, graph, "https://example.com/", rule_conditions=rule_conditions
            )
        )
        screen = data["screens"][0]
        assert "document_conditions" in screen
        assert "税額 = 課税対象額 × 10%" in screen["document_conditions"][0]["description"]
