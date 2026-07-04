"""SPEC-1-1: PDF/Word 自由文からの LLM 意味抽出（Doc Fusion Phase 2）のテスト。

対象:
    - src/ingest/llm_extractor.py::extract_semantics / filter_hallucinations
    - src/ingest/loader.py::load_reference_documents(use_llm=...)
    - src/llm/provider.py::RulesProvider/OpenAIProvider.extract_document_semantics
    - src/generator/fusion_reporter.py の documented_rules 出力（オプトイン）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ingest.llm_extractor import extract_semantics, filter_hallucinations
from ingest.loader import load_reference_documents
from ingest.matcher import fuse
from ingest.models import DocumentBundle
from llm.provider import RulesProvider


class _FakeSemanticsProvider:
    """extract_document_semantics の応答を注入可能にするフェイク provider。"""

    def __init__(self, payload: dict[str, Any] | None = None, error: Exception | None = None):
        self._payload = payload or {"screens": [], "fields": [], "rules": []}
        self._error = error

    def generate_viewpoints(self, screen_info):  # pragma: no cover - 未使用
        raise NotImplementedError

    def generate_qa_process(self, domain, report, viewpoints=None):  # pragma: no cover
        raise NotImplementedError

    def extract_document_semantics(
        self, lines: list[tuple[str, str]], source_file: str
    ) -> dict[str, Any]:
        if self._error is not None:
            raise self._error
        return self._payload


_LINES = [
    ("line 1", "振込画面"),
    ("line 2", "振込限度額は1日100万円までとする。"),
    ("line 3", "その他の説明文。"),
]


class TestExtractRulesFromLines:
    def test_extract_rules_from_pdf_lines(self) -> None:
        """限度値ルールが DocumentedRule として抽出され、evidence.location が該当行になる。"""
        provider = _FakeSemanticsProvider(
            {
                "screens": [],
                "fields": [],
                "rules": [
                    {
                        "kind": "limit",
                        "description": "振込限度額",
                        "screen_name": "",
                        "field_name": "",
                        "expression": "100万円/日",
                        "quote": "振込限度額は1日100万円までとする。",
                    }
                ],
            }
        )
        screens, fields, rules = extract_semantics(_LINES, "spec.pdf", provider)
        assert screens == []
        assert fields == []
        assert len(rules) == 1
        assert rules[0].kind == "limit"
        assert rules[0].evidence is not None
        assert rules[0].evidence.location == "line 2"
        assert rules[0].evidence.file == "spec.pdf"


class TestHallucinationFilter:
    def test_hallucinated_quote_discarded(self, caplog: pytest.LogCaptureFixture) -> None:
        """原文に無い quote を含む応答は破棄され、警告ログに項目名が残る。"""
        payload = {
            "screens": [
                {"name": "存在しない画面", "url_hint": "", "quote": "これは原文に無い文章です"}
            ],
            "fields": [],
            "rules": [],
        }
        with caplog.at_level("WARNING"):
            screens, fields, rules = filter_hallucinations(payload, _LINES, "spec.pdf")
        assert screens == []
        assert "存在しない画面" in caplog.text

    def test_llm_confidence_capped(self) -> None:
        """完全一致 quote は confidence 0.9、正規化一致のみは 0.7（>0.9 は無い）。"""
        payload = {
            "screens": [
                {"name": "振込", "url_hint": "", "quote": "振込限度額は1日100万円までとする。"},
                {
                    "name": "振込2",
                    "url_hint": "",
                    "quote": "振込限度額は１日１００万円までとする。",
                },
            ],
            "fields": [],
            "rules": [],
        }
        screens, _, _ = filter_hallucinations(payload, _LINES, "spec.pdf")
        assert len(screens) == 2
        confidences = {s.name: s.confidence for s in screens}
        assert confidences["振込"] == 0.9
        assert confidences["振込2"] == 0.7
        assert all(c <= 0.9 for c in confidences.values())

    def test_unknown_screen_ref_blanked(self) -> None:
        """実在しない screen_name を持つ項目は screen_name="" に落ちる。"""
        payload = {
            "screens": [],
            "fields": [
                {
                    "name": "振込先口座",
                    "screen_name": "実在しない画面",
                    "field_type": "text",
                    "required": True,
                    "max_length": None,
                    "quote": "振込限度額は1日100万円までとする。",
                }
            ],
            "rules": [],
        }
        _, fields, _ = filter_hallucinations(payload, _LINES, "spec.pdf")
        assert len(fields) == 1
        assert fields[0].screen_name == ""
        assert "確認できず" in fields[0].note


class TestExtractSemanticsErrorHandling:
    def test_no_lines_skips_llm(self) -> None:
        screens, fields, rules = extract_semantics([], "empty.pdf", RulesProvider())
        assert (screens, fields, rules) == ([], [], [])

    def test_rules_provider_returns_empty(self) -> None:
        """RulesProvider（キーなし）は常に空 3-tuple を返す。"""
        screens, fields, rules = extract_semantics(_LINES, "spec.pdf", RulesProvider())
        assert (screens, fields, rules) == ([], [], [])

    def test_llm_error_falls_back(self, caplog: pytest.LogCaptureFixture) -> None:
        """provider が例外を投げても extract_semantics は例外を外に漏らさない。"""
        provider = _FakeSemanticsProvider(error=RuntimeError("network down"))
        with caplog.at_level("WARNING"):
            screens, fields, rules = extract_semantics(_LINES, "spec.pdf", provider)
        assert (screens, fields, rules) == ([], [], [])
        assert "棄却" in caplog.text


class TestLoadReferenceDocumentsWithLlm:
    def test_no_api_key_same_as_phase1(self, tmp_path: Path) -> None:
        """use_llm=True でも api_key が空なら Phase 1 と完全に同一の DocumentBundle。"""
        doc_path = tmp_path / "spec.txt"
        doc_path.write_text("振込限度額は1日100万円までとする。\n", encoding="utf-8")

        phase1 = load_reference_documents([doc_path])
        with_llm_no_key = load_reference_documents([doc_path], use_llm=True, api_key="")
        assert phase1.screens == with_llm_no_key.screens
        assert phase1.fields == with_llm_no_key.fields
        assert phase1.rules == with_llm_no_key.rules == ()

    def test_use_llm_false_ignores_api_key(self, tmp_path: Path) -> None:
        doc_path = tmp_path / "spec.txt"
        doc_path.write_text("振込限度額は1日100万円までとする。\n", encoding="utf-8")
        bundle = load_reference_documents([doc_path], use_llm=False, api_key="sk-test")
        assert bundle.rules == ()


class TestFusionJsonOptIn:
    def test_fusion_json_no_rules_key_when_empty(self, tmp_path: Path) -> None:
        """rules=() の bundle では doc_fusion.json に documented_rules キーが無い。"""
        from generator.fusion_reporter import fusion_to_dict

        bundle = DocumentBundle(screens=(), fields=(), source_files=("spec.txt",), rules=())
        result = fuse([], bundle)
        data = fusion_to_dict(result, bundle)
        assert "documented_rules" not in data

    def test_fusion_json_rules_with_evidence(self) -> None:
        """rules 1 件の bundle では documented_rules に file/location/quote/confidence が載る。"""
        from generator.fusion_reporter import fusion_to_dict
        from ingest.models import DocumentedRule, DocumentEvidence

        rule = DocumentedRule(
            rule_id="RULE-001",
            kind="limit",
            description="振込限度額",
            expression="100万円/日",
            confidence=0.9,
            evidence=DocumentEvidence(file="spec.pdf", location="line 2", quote="振込限度額は…"),
        )
        bundle = DocumentBundle(screens=(), fields=(), source_files=("spec.pdf",), rules=(rule,))
        result = fuse([], bundle)
        data = fusion_to_dict(result, bundle)
        assert "documented_rules" in data
        assert data["documented_rules"][0]["rule_id"] == "RULE-001"
        assert data["documented_rules"][0]["confidence"] == 0.9
        assert data["documented_rules"][0]["doc_evidence"]["file"] == "spec.pdf"


class TestCliIntegration:
    def test_doc_llm_flag_completes_without_key(self, tmp_path: Path, monkeypatch) -> None:
        """--doc-llm 相当（use_llm=True・キーなし環境）で例外なく完走する。"""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        doc_path = tmp_path / "spec.txt"
        doc_path.write_text("振込限度額は1日100万円までとする。\n", encoding="utf-8")
        bundle = load_reference_documents([doc_path], use_llm=True, api_key="")
        result = fuse([], bundle)
        from generator.fusion_reporter import save_fusion_outputs

        save_fusion_outputs(result, bundle, tmp_path / "out")
        assert (tmp_path / "out" / "doc_fusion.md").exists()
        data = json.loads((tmp_path / "out" / "doc_fusion.json").read_text(encoding="utf-8"))
        assert "documented_rules" not in data
