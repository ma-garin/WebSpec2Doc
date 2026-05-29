"""json_reporter.py のユニットテスト"""
from __future__ import annotations

import json

import networkx as nx
import pytest

from analyzer.html_analyzer import analyze_pages
from crawler.page_crawler import FieldData, FormData, PageData
from generator.json_reporter import (
    _field_type_tag,
    _locator_candidates,
    generate_json_report,
)
from graph.transition_graph import build_graph


class TestGenerateJsonReport:
    def test_returns_valid_json(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        result = generate_json_report(analyzed, graph, page_top.url)
        data = json.loads(result)
        assert "meta" in data
        assert "screens" in data

    def test_meta_contains_target_url(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        result = generate_json_report(analyzed, graph, page_top.url)
        data = json.loads(result)
        assert data["meta"]["target_url"] == page_top.url

    def test_meta_page_count(self, page_top: PageData, page_about: PageData) -> None:
        analyzed = analyze_pages([page_top, page_about])
        graph = build_graph(analyzed)
        result = generate_json_report(analyzed, graph, page_top.url)
        data = json.loads(result)
        assert data["meta"]["page_count"] == 2

    def test_screens_have_page_id(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        result = generate_json_report(analyzed, graph, page_top.url)
        data = json.loads(result)
        assert data["screens"][0]["page_id"] == "P001"

    def test_fields_include_test_conditions(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        result = generate_json_report(analyzed, graph, page_top.url)
        data = json.loads(result)
        fields = data["screens"][0]["forms"][0]["fields"]
        assert all("test_conditions" in f for f in fields)

    def test_fields_include_locators(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        result = generate_json_report(analyzed, graph, page_top.url)
        data = json.loads(result)
        fields = data["screens"][0]["forms"][0]["fields"]
        assert all("locators" in f for f in fields)

    def test_transitions_to_included(
        self, page_top: PageData, page_about: PageData
    ) -> None:
        analyzed = analyze_pages([page_top, page_about])
        graph = build_graph(analyzed)
        result = generate_json_report(analyzed, graph, page_top.url)
        data = json.loads(result)
        p001 = next(s for s in data["screens"] if s["page_id"] == "P001")
        assert "P002" in p001["transitions"]["to"]

    def test_crawl_metadata_depth(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        result = generate_json_report(
            analyzed, graph, page_top.url, crawl_depth=2
        )
        data = json.loads(result)
        assert data["meta"]["crawl_depth"] == 2

    def test_crawl_metadata_max_pages(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        result = generate_json_report(
            analyzed, graph, page_top.url, crawl_max_pages=20
        )
        data = json.loads(result)
        assert data["meta"]["max_pages"] == 20

    def test_crawl_metadata_crawled_at(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        result = generate_json_report(
            analyzed, graph, page_top.url, crawled_at="2026-05-29"
        )
        data = json.loads(result)
        assert data["meta"]["crawled_at"] == "2026-05-29"

    def test_empty_pages(self) -> None:
        graph = nx.DiGraph()
        result = generate_json_report([], graph, "https://example.com")
        data = json.loads(result)
        assert data["screens"] == []
        assert data["meta"]["page_count"] == 0

    def test_japanese_characters_preserved(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        result = generate_json_report(analyzed, graph, page_top.url)
        data = json.loads(result)
        assert "テストサイト" in data["screens"][0]["title"]


class TestLocatorCandidates:
    def test_id_produces_hash_selector(self) -> None:
        field = FieldData(
            field_type="text",
            name="q",
            placeholder="",
            required=False,
            element_id="search-input",
        )
        candidates = _locator_candidates(field)
        assert "#search-input" in candidates

    def test_name_produces_attribute_selector(self) -> None:
        field = FieldData(field_type="text", name="q", placeholder="", required=False)
        candidates = _locator_candidates(field)
        assert 'input[name="q"]' in candidates

    def test_no_id_no_hash_selector(self) -> None:
        field = FieldData(field_type="text", name="q", placeholder="", required=False)
        candidates = _locator_candidates(field)
        assert not any(c.startswith("#") for c in candidates)

    def test_empty_name_no_attribute_selector(self) -> None:
        field = FieldData(field_type="text", name="", placeholder="", required=False)
        candidates = _locator_candidates(field)
        assert all('[name=""]' not in c for c in candidates)

    def test_select_tag_in_selector(self) -> None:
        field = FieldData(
            field_type="select", name="color", placeholder="", required=False
        )
        candidates = _locator_candidates(field)
        assert any("select" in c for c in candidates)

    def test_textarea_tag_in_selector(self) -> None:
        field = FieldData(
            field_type="textarea", name="msg", placeholder="", required=False
        )
        candidates = _locator_candidates(field)
        assert any("textarea" in c for c in candidates)


class TestFieldTypeTag:
    def test_select_returns_select(self) -> None:
        assert _field_type_tag("select") == "select"

    def test_textarea_returns_textarea(self) -> None:
        assert _field_type_tag("textarea") == "textarea"

    def test_text_returns_input(self) -> None:
        assert _field_type_tag("text") == "input"

    def test_email_returns_input(self) -> None:
        assert _field_type_tag("email") == "input"

    def test_number_returns_input(self) -> None:
        assert _field_type_tag("number") == "input"
