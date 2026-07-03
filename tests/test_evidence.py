"""SourceEvidence / confidence（Layer 1-B）のユニット・受け入れテスト。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import openpyxl
import pytest

from analyzer.html_analyzer import analyze_pages
from analyzer.test_conditions import derive_conditions_with_evidence
from crawler.page_crawler import (
    FieldData,
    FormData,
    PageData,
    SourceEvidence,
    evidence_from_dict,
    evidence_to_dict,
)
from graph.transition_graph import build_graph
from llm.provider import OpenAIProvider, RulesProvider
from llm.viewpoint_generator import (
    TestViewpoint,
    ViewpointValidationError,
    generate_viewpoints_by_rules,
    llm_viewpoint_confidence,
    validate_viewpoint_payload,
)

_EVIDENCE = SourceEvidence(
    selector="#email",
    html_attribute="id",
    screenshot_path="output/screenshots/P001.png",
    bbox=(10, 20, 200, 30),
)


def _field_with_evidence() -> FieldData:
    return FieldData(
        field_type="email",
        name="email",
        placeholder="メール",
        required=True,
        element_id="email",
        evidence=_EVIDENCE,
        confidence=1.0,
    )


def _page_with_evidence() -> PageData:
    form = FormData(action="/send", method="post", fields=(_field_with_evidence(),))
    return PageData(
        url="https://example.com/contact",
        title="お問い合わせ",
        headings=("お問い合わせ",),
        links=(),
        forms=(form,),
        screenshot_path="output/screenshots/P001.png",
    )


# ---------- SourceEvidence シリアライズ ----------


class TestEvidenceSerialization:
    def test_roundtrip(self) -> None:
        data = evidence_to_dict(_EVIDENCE)
        restored = evidence_from_dict(data)
        assert restored == _EVIDENCE

    def test_none_evidence(self) -> None:
        assert evidence_to_dict(None) is None
        assert evidence_from_dict(None) is None
        assert evidence_from_dict("not-a-dict") is None

    def test_bbox_serialized_as_list(self) -> None:
        data = evidence_to_dict(_EVIDENCE)
        assert data is not None
        assert data["bbox"] == [10, 20, 200, 30]


# ---------- テスト条件への根拠付与 ----------


class TestDeriveConditionsWithEvidence:
    def test_conditions_carry_field_evidence(self) -> None:
        conditions = derive_conditions_with_evidence(_field_with_evidence())
        assert conditions
        assert all(c.evidence == _EVIDENCE for c in conditions)
        assert all(c.source == "rules" for c in conditions)
        assert all(c.confidence == 1.0 for c in conditions)


# ---------- ルール由来の観点 ----------


class TestRulesViewpointEvidence:
    def test_all_rule_viewpoints_have_evidence_and_full_confidence(self) -> None:
        from llm.screen_classifier import SCREEN_FORM, ScreenClassification

        sc = ScreenClassification(SCREEN_FORM, 0.9, (), "high")
        viewpoints = generate_viewpoints_by_rules(sc, [_field_with_evidence()])
        assert viewpoints
        assert all(v.confidence == 1.0 for v in viewpoints)
        assert all(v.evidence is not None for v in viewpoints)

    def test_field_viewpoint_uses_field_evidence(self) -> None:
        from llm.screen_classifier import SCREEN_GENERAL, ScreenClassification

        sc = ScreenClassification(SCREEN_GENERAL, 0.5, (), "low")
        viewpoints = generate_viewpoints_by_rules(sc, [_field_with_evidence()])
        required_vp = next(v for v in viewpoints if "必須" in v.viewpoint)
        assert required_vp.evidence is not None
        assert required_vp.evidence.selector == "#email"
        assert required_vp.evidence.html_attribute == "required"


# ---------- 受け入れ条件: evidence なしの観点は出力されない ----------


class TestNoEvidenceViewpointsExcluded:
    def test_provider_filters_viewpoints_without_evidence(self) -> None:
        no_evidence_vp = TestViewpoint(
            category="機能",
            viewpoint="根拠なし観点",
            risk_level="低",
            example_cases=("a", "b"),
            confidence=1.0,
            evidence=None,
        )
        with patch(
            "llm.viewpoint_generator.generate_viewpoints_by_rules",
            return_value=[no_evidence_vp],
        ):
            result = RulesProvider().generate_viewpoints({})
        assert result == []

    def test_provider_outputs_evidence_and_confidence(self) -> None:
        result = RulesProvider().generate_viewpoints(
            {"fields": [{"required": True, "maxlength": 10, "name": "email"}]}
        )
        assert result
        for item in result:
            assert item["evidence"] is not None
            assert item["confidence"] == 1.0
            assert item["source"] == "rules"


# ---------- 受け入れ条件: LLM スキーマ違反時のフォールバック ----------


def _mock_openai_response(content: dict) -> MagicMock:
    response = MagicMock()
    response.read.return_value = json.dumps(
        {"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]}
    ).encode()
    response.__enter__ = lambda r: r
    response.__exit__ = MagicMock(return_value=False)
    return response


class TestLLMFallback:
    def test_invalid_category_falls_back_to_rules(self) -> None:
        bad = {
            "viewpoints": [
                {
                    "category": "存在しないカテゴリ",
                    "viewpoint": "x",
                    "risk_level": "高",
                    "example_cases": ["a", "b"],
                }
            ]
        }
        with patch("urllib.request.urlopen", return_value=_mock_openai_response(bad)):
            result = OpenAIProvider("sk-test").generate_viewpoints({})
        assert result
        assert all(item["source"] == "rules" for item in result)

    def test_missing_viewpoints_key_falls_back(self) -> None:
        with patch("urllib.request.urlopen", return_value=_mock_openai_response({"other": []})):
            result = OpenAIProvider("sk-test").generate_viewpoints({})
        assert all(item["source"] == "rules" for item in result)

    def test_network_error_falls_back(self) -> None:
        with patch("urllib.request.urlopen", side_effect=OSError("接続失敗")):
            result = OpenAIProvider("sk-test").generate_viewpoints({})
        assert all(item["source"] == "rules" for item in result)

    def test_valid_response_returns_openai_source_with_confidence(self) -> None:
        good = {
            "viewpoints": [
                {
                    "category": "機能",
                    "viewpoint": "テスト観点",
                    "risk_level": "中",
                    "example_cases": ["ケース1", "ケース2"],
                }
            ]
        }
        with patch("urllib.request.urlopen", return_value=_mock_openai_response(good)):
            result = OpenAIProvider("sk-test").generate_viewpoints({})
        assert len(result) == 1
        assert result[0]["source"] == "openai"
        assert result[0]["confidence"] == 0.9
        assert result[0]["evidence"] is not None

    def test_rejection_reason_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        bad = {
            "viewpoints": [
                {
                    "category": "不正",
                    "viewpoint": "x",
                    "risk_level": "高",
                    "example_cases": ["a", "b"],
                }
            ]
        }
        with (
            patch("urllib.request.urlopen", return_value=_mock_openai_response(bad)),
            caplog.at_level("WARNING", logger="llm.provider"),
        ):
            OpenAIProvider("sk-test").generate_viewpoints({})
        assert any("棄却" in record.message for record in caplog.records)


# ---------- LLM 応答検証・確信度算出 ----------


class TestViewpointValidation:
    def _item(self, **overrides: object) -> dict:
        base: dict = {
            "category": "機能",
            "viewpoint": "観点",
            "risk_level": "高",
            "example_cases": ["a", "b"],
        }
        base.update(overrides)
        return base

    def test_valid_payload_passes(self) -> None:
        items = validate_viewpoint_payload({"viewpoints": [self._item()]})
        assert len(items) == 1

    def test_invalid_category_raises(self) -> None:
        with pytest.raises(ViewpointValidationError):
            validate_viewpoint_payload({"viewpoints": [self._item(category="謎")]})

    def test_invalid_risk_level_raises(self) -> None:
        with pytest.raises(ViewpointValidationError):
            validate_viewpoint_payload({"viewpoints": [self._item(risk_level="最強")]})

    def test_empty_viewpoint_raises(self) -> None:
        with pytest.raises(ViewpointValidationError):
            validate_viewpoint_payload({"viewpoints": [self._item(viewpoint=" ")]})

    def test_confidence_with_standard_cases(self) -> None:
        assert llm_viewpoint_confidence(self._item()) == 0.9

    def test_confidence_penalized_without_cases(self) -> None:
        assert llm_viewpoint_confidence(self._item(example_cases=[])) == 0.7


# ---------- 受け入れ条件: Excel/JSON/HTML の3形式で根拠情報が一致 ----------


class TestEvidenceConsistencyAcrossFormats:
    def _analyzed(self) -> list:
        return analyze_pages([_page_with_evidence()])

    def test_json_html_excel_share_same_evidence(self, tmp_path: Path) -> None:
        from analyzer.form_analyzer import summarize_forms
        from generator.html_reporter import generate_html_report
        from generator.json_reporter import generate_json_report
        from main import _save_excel_output

        pages = self._analyzed()
        graph = build_graph(pages)
        form_summary = summarize_forms(pages)

        # JSON
        report = json.loads(generate_json_report(pages, graph, "https://example.com/contact"))
        json_field = report["screens"][0]["forms"][0]["fields"][0]
        assert json_field["evidence"]["selector"] == "#email"
        assert json_field["confidence"] == 1.0
        assert json_field["evidence"]["bbox"] == [10, 20, 200, 30]

        # HTML
        html_text = generate_html_report(
            pages, graph, form_summary, "https://example.com/contact", "graph TD;"
        )
        assert "#email" in html_text
        assert "rules 1.0" in html_text
        assert 'data-bbox="10,20,200,30"' in html_text

        # Excel
        _save_excel_output(tmp_path, pages, form_summary)
        wb = openpyxl.load_workbook(tmp_path / "spec.xlsx")
        forms_sheet = wb["Forms"]
        header = [cell.value for cell in forms_sheet[1]]
        assert "根拠" in header
        assert "確信度" in header
        row = [cell.value for cell in forms_sheet[2]]
        evidence_cell = row[header.index("根拠")]
        confidence_cell = row[header.index("確信度")]
        assert "#email" in str(evidence_cell)
        assert float(confidence_cell) == 1.0

        # 3形式の突き合わせ: セレクタと確信度が一致
        assert json_field["evidence"]["selector"] in str(evidence_cell)
        assert json_field["confidence"] == float(confidence_cell)
        assert json_field["evidence"]["selector"] in html_text


# ---------- スナップショット後方互換 ----------


class TestSnapshotEvidenceCompat:
    def test_old_snapshot_without_evidence_loads(self, tmp_path: Path) -> None:
        from diff.snapshot import load_snapshot

        old_payload = [
            {
                "url": "https://example.com/",
                "title": "旧スナップショット",
                "headings": [],
                "links": [],
                "forms": [
                    {
                        "action": "/send",
                        "method": "post",
                        "fields": [
                            {
                                "field_type": "text",
                                "name": "q",
                                "placeholder": "",
                                "required": False,
                            }
                        ],
                    }
                ],
                "screenshot_path": None,
            }
        ]
        path = tmp_path / "old.json"
        path.write_text(json.dumps(old_payload), encoding="utf-8")
        pages = load_snapshot(path)
        field = pages[0].forms[0].fields[0]
        assert field.evidence is None
        assert field.confidence == 1.0

    def test_new_snapshot_roundtrips_evidence(self, tmp_path: Path) -> None:
        from diff.snapshot import load_snapshot, save_snapshot

        page = _page_with_evidence()
        path = save_snapshot([page], tmp_path)
        loaded = load_snapshot(path)
        field = loaded[0].forms[0].fields[0]
        assert field.evidence == _EVIDENCE
