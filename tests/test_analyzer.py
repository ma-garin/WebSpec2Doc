"""html_analyzer.py / form_analyzer.py のユニットテスト"""

from __future__ import annotations

import pytest

from analyzer.form_analyzer import summarize_forms
from analyzer.html_analyzer import AnalyzedPage, analyze_pages, assign_page_ids
from crawler.page_crawler import PageData

# ---------- assign_page_ids ----------


class TestAssignPageIds:
    def test_ids_are_sequential(self, page_top: PageData, page_about: PageData) -> None:
        result = assign_page_ids([page_top, page_about])
        assert result[page_top.url] == "P001"
        assert result[page_about.url] == "P002"

    def test_returns_dict_keyed_by_url(self, page_top: PageData) -> None:
        result = assign_page_ids([page_top])
        assert page_top.url in result

    def test_empty_list(self) -> None:
        assert assign_page_ids([]) == {}

    def test_unique_ids(
        self, page_top: PageData, page_about: PageData, page_contact: PageData
    ) -> None:
        result = assign_page_ids([page_top, page_about, page_contact])
        ids = list(result.values())
        assert len(ids) == len(set(ids))


# ---------- analyze_pages ----------


class TestAnalyzePages:
    def test_returns_analyzed_page_list(self, page_top: PageData, page_about: PageData) -> None:
        result = analyze_pages([page_top, page_about])
        assert len(result) == 2
        assert all(isinstance(p, AnalyzedPage) for p in result)

    def test_page_ids_match_sequence(self, page_top: PageData, page_about: PageData) -> None:
        result = analyze_pages([page_top, page_about])
        assert result[0].page_id == "P001"
        assert result[1].page_id == "P002"

    def test_page_data_preserved(self, page_top: PageData) -> None:
        result = analyze_pages([page_top])
        assert result[0].page_data is page_top

    def test_nav_elements_from_links(self, page_top: PageData) -> None:
        result = analyze_pages([page_top])
        nav = result[0].nav_elements
        assert any("/about.html" in elem for elem in nav)
        assert any("/contact.html" in elem for elem in nav)

    def test_empty_list(self) -> None:
        assert analyze_pages([]) == []

    def test_immutable_result(self, page_top: PageData) -> None:
        result = analyze_pages([page_top])
        with pytest.raises((AttributeError, TypeError)):
            result[0].page_id = "X999"  # type: ignore[misc]


# ---------- summarize_forms ----------


class TestSummarizeForms:
    def test_returns_one_row_per_field(
        self,
        page_top: PageData,
        page_contact: PageData,
    ) -> None:
        analyzed = analyze_pages([page_top, page_contact])
        result = summarize_forms(analyzed)
        # page_top: 1 field (q), page_contact: 3 fields (name, email, message)
        assert len(result) == 4

    def test_row_has_expected_keys(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        result = summarize_forms(analyzed)
        assert len(result) == 1
        row = result[0]
        assert "page_id" in row
        assert "url" in row
        assert "field_type" in row
        assert "name" in row
        assert "placeholder" in row
        assert "required" in row

    def test_page_id_correct(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        result = summarize_forms(analyzed)
        assert result[0]["page_id"] == "P001"

    def test_required_field_flagged(self, page_contact: PageData) -> None:
        analyzed = analyze_pages([page_contact])
        result = summarize_forms(analyzed)
        required_fields = [r for r in result if r["required"] is True]
        assert len(required_fields) >= 1

    def test_no_forms_returns_empty(self, page_about: PageData) -> None:
        analyzed = analyze_pages([page_about])
        assert summarize_forms(analyzed) == []

    def test_empty_pages_returns_empty(self) -> None:
        assert summarize_forms([]) == []
