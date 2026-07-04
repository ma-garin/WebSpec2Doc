"""ニールセン10原則ヒューリスティック（rules フォールバック・幻覚フィルタ）のユニットテスト。"""

from __future__ import annotations

from crawler.page_crawler import SourceEvidence, evidence_to_dict
from ux.heuristics import (
    UX_REVIEW_JSON_SCHEMA,
    UxReviewValidationError,
    filter_hallucinated_findings,
    generate_ux_findings_by_rules,
    pop_hallucination_drop_count,
    ux_finding_to_dict,
    validate_ux_payload,
)


def _field(
    *,
    name: str = "email",
    has_visible_label: bool = True,
    aria_label: str = "",
    placeholder: str = "",
    required: bool = False,
    aria_required: bool = False,
    selector: str = "[name='email']",
) -> dict:
    return {
        "name": name,
        "has_visible_label": has_visible_label,
        "aria_label": aria_label,
        "placeholder": placeholder,
        "required": required,
        "aria_required": aria_required,
        "evidence": evidence_to_dict(SourceEvidence(selector=selector)),
    }


class TestRulesFallback:
    def test_rules_fallback_generates_findings(self) -> None:
        """ラベルなしフィールドから evidence 付きの rules 所見が生成される（AC-5）。"""
        screen_info = {
            "title": "お問い合わせ",
            "headings": ["お問い合わせ"],
            "fields": [
                _field(
                    name="unlabeled",
                    has_visible_label=False,
                    aria_label="",
                    placeholder="",
                    selector="[name='unlabeled']",
                )
            ],
        }

        findings = generate_ux_findings_by_rules(screen_info)

        assert findings, "ラベルなし入力からニールセン所見が生成されていない"
        assert all(f.source == "rules" for f in findings)
        assert all(f.confidence == 1.0 for f in findings)
        assert all(f.evidence is not None for f in findings)
        assert any(f.principle == "N6" for f in findings)

    def test_placeholder_only_label_generates_n5_finding(self) -> None:
        """placeholder のみに依存したラベル代替は N5（エラー防止）として検出される。"""
        screen_info = {
            "headings": ["画面"],
            "fields": [
                _field(
                    name="q",
                    has_visible_label=False,
                    aria_label="",
                    placeholder="キーワード",
                    selector="[name='q']",
                )
            ],
        }

        findings = generate_ux_findings_by_rules(screen_info)

        assert any(f.principle == "N5" for f in findings)

    def test_required_without_aria_required_generates_n1_finding(self) -> None:
        """required だが aria-required 未設定のフィールドは N1 として検出される。"""
        screen_info = {
            "headings": ["画面"],
            "fields": [
                _field(
                    name="name",
                    has_visible_label=True,
                    required=True,
                    aria_required=False,
                    selector="[name='name']",
                )
            ],
        }

        findings = generate_ux_findings_by_rules(screen_info)

        assert any(f.principle == "N1" for f in findings)

    def test_no_headings_generates_screen_level_finding(self) -> None:
        """見出しが1つも無い画面は N1（状態の可視性）として検出される。"""
        screen_info = {"headings": [], "fields": []}

        findings = generate_ux_findings_by_rules(screen_info)

        assert len(findings) == 1
        assert findings[0].principle == "N1"
        assert findings[0].evidence.selector == "body"

    def test_field_without_evidence_is_skipped(self) -> None:
        """evidence の無いフィールドは対象外とする（evidence-only 原則。根拠のない所見を出さない）。"""
        screen_info = {
            "headings": ["画面"],
            "fields": [
                {
                    "name": "x",
                    "has_visible_label": False,
                    "aria_label": "",
                    "placeholder": "",
                    "required": False,
                    "aria_required": False,
                    "evidence": None,
                }
            ],
        }

        findings = generate_ux_findings_by_rules(screen_info)

        # evidence が無いフィールドはラベル欠落所見の対象にならない（見出しはあるため N1 も出ない）
        assert findings == []

    def test_ux_finding_to_dict_includes_source_and_confidence(self) -> None:
        """UxFinding の dict 化に source・confidence・evidence が含まれる。"""
        screen_info = {
            "headings": [],
            "fields": [],
        }
        finding = generate_ux_findings_by_rules(screen_info)[0]

        data = ux_finding_to_dict(finding)

        assert data["source"] == "rules"
        assert data["confidence"] == 1.0
        assert data["evidence"]["selector"] == "body"


class TestValidateUxPayload:
    def test_validate_ux_payload_accepts_well_formed_response(self) -> None:
        payload = {
            "findings": [
                {
                    "principle": "N6",
                    "severity": "high",
                    "finding": "ラベルがありません。",
                    "selector": "#foo",
                }
            ]
        }

        items = validate_ux_payload(payload)

        assert len(items) == 1

    def test_validate_ux_payload_rejects_missing_findings(self) -> None:
        try:
            validate_ux_payload({})
            raise AssertionError("UxReviewValidationError が送出されるはずです")
        except UxReviewValidationError:
            pass

    def test_validate_ux_payload_rejects_invalid_principle(self) -> None:
        payload = {
            "findings": [
                {
                    "principle": "N99",
                    "severity": "high",
                    "finding": "不正な原則",
                    "selector": "#foo",
                }
            ]
        }
        try:
            validate_ux_payload(payload)
            raise AssertionError("UxReviewValidationError が送出されるはずです")
        except UxReviewValidationError:
            pass

    def test_validate_ux_payload_rejects_missing_selector(self) -> None:
        payload = {
            "findings": [
                {"principle": "N1", "severity": "low", "finding": "セレクタなし", "selector": ""}
            ]
        }
        try:
            validate_ux_payload(payload)
            raise AssertionError("UxReviewValidationError が送出されるはずです")
        except UxReviewValidationError:
            pass

    def test_schema_has_required_keys(self) -> None:
        item_schema = UX_REVIEW_JSON_SCHEMA["properties"]["findings"]["items"]
        assert set(item_schema["required"]) == {"principle", "severity", "finding", "selector"}
        assert item_schema["additionalProperties"] is False


class TestHallucinationFilter:
    def test_hallucination_selector_dropped(self) -> None:
        """known_selectors 外の selector を含む所見は破棄され、破棄件数が記録される（AC-4）。"""
        pop_hallucination_drop_count()  # 前テストの残留をクリア
        items = [
            {"principle": "N6", "severity": "high", "finding": "実在", "selector": "#real"},
            {"principle": "N1", "severity": "low", "finding": "幻覚", "selector": "#ghost"},
        ]

        kept = filter_hallucinated_findings(items, known_selectors={"#real"})

        assert len(kept) == 1
        assert kept[0]["selector"] == "#real"
        assert pop_hallucination_drop_count() == 1

    def test_pop_hallucination_drop_count_resets(self) -> None:
        """pop_hallucination_drop_count は呼び出し後にカウンタをリセットする。"""
        pop_hallucination_drop_count()
        filter_hallucinated_findings(
            [{"principle": "N1", "severity": "low", "finding": "x", "selector": "#ghost"}],
            known_selectors=set(),
        )

        assert pop_hallucination_drop_count() == 1
        assert pop_hallucination_drop_count() == 0

    def test_all_selectors_known_drops_nothing(self) -> None:
        pop_hallucination_drop_count()
        items = [{"principle": "N1", "severity": "low", "finding": "x", "selector": "#real"}]

        kept = filter_hallucinated_findings(items, known_selectors={"#real"})

        assert len(kept) == 1
        assert pop_hallucination_drop_count() == 0
