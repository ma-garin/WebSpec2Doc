"""link_extractor.py のユニットテスト（Playwright Page をモック）"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from crawler.link_extractor import (
    _to_field_data,
    _to_form_data,
    compute_dom_signature,
    extract_buttons,
    extract_forms,
    extract_headings,
    extract_internal_links,
    extract_page_title,
    has_password_field,
)

# ---------- has_password_field ----------


def test_has_password_field_true_when_present() -> None:
    page = MagicMock()
    page.query_selector.return_value = MagicMock()
    assert has_password_field(page) is True
    page.query_selector.assert_called_once_with("input[type=password]")


def test_has_password_field_false_when_absent() -> None:
    page = MagicMock()
    page.query_selector.return_value = None
    assert has_password_field(page) is False


def test_has_password_field_false_on_error() -> None:
    page = MagicMock()
    page.query_selector.side_effect = RuntimeError("boom")
    assert has_password_field(page) is False


# ---------- _to_field_data ----------


class TestToFieldData:
    def test_basic_text_field(self) -> None:
        raw = {"field_type": "text", "name": "q", "placeholder": "Search", "required": False}
        result = _to_field_data(raw)
        assert result.field_type == "text"
        assert result.name == "q"
        assert result.placeholder == "Search"
        assert result.required is False

    def test_required_field(self) -> None:
        raw = {"field_type": "email", "name": "email", "placeholder": "", "required": True}
        result = _to_field_data(raw)
        assert result.required is True

    def test_missing_keys_default_to_empty(self) -> None:
        result = _to_field_data({})
        assert result.field_type == ""
        assert result.name == ""
        assert result.placeholder == ""
        assert result.required is False

    def test_none_values_default_to_empty(self) -> None:
        raw: dict = {"field_type": None, "name": None, "placeholder": None}
        result = _to_field_data(raw)
        assert result.field_type == ""
        assert result.name == ""

    def test_element_id_extracted(self) -> None:
        raw = {
            "field_type": "text",
            "name": "q",
            "placeholder": "",
            "required": False,
            "id": "search-box",
        }
        result = _to_field_data(raw)
        assert result.element_id == "search-box"

    def test_element_id_defaults_to_empty(self) -> None:
        raw = {"field_type": "text", "name": "q", "placeholder": "", "required": False}
        result = _to_field_data(raw)
        assert result.element_id == ""

    def test_result_is_frozen(self) -> None:
        raw = {"field_type": "text", "name": "x", "placeholder": "", "required": False}
        result = _to_field_data(raw)
        with pytest.raises((AttributeError, TypeError)):
            result.name = "y"  # type: ignore[misc]


# ---------- _to_form_data ----------


class TestToFormData:
    def test_basic_form(self) -> None:
        raw = {"action": "/search", "method": "get", "fields": []}
        result = _to_form_data(raw)
        assert result.action == "/search"
        assert result.method == "get"
        assert result.fields == ()

    def test_form_with_fields(self) -> None:
        raw = {
            "action": "/send",
            "method": "post",
            "fields": [{"field_type": "text", "name": "name", "placeholder": "", "required": True}],
        }
        result = _to_form_data(raw)
        assert len(result.fields) == 1
        assert result.fields[0].name == "name"

    def test_method_lowercased(self) -> None:
        raw = {"action": "", "method": "POST", "fields": []}
        result = _to_form_data(raw)
        assert result.method == "post"

    def test_missing_method_defaults_to_get(self) -> None:
        raw = {"action": "/", "fields": []}
        result = _to_form_data(raw)
        assert result.method == "get"

    def test_none_action_defaults_to_empty(self) -> None:
        raw = {"action": None, "method": "get", "fields": []}
        result = _to_form_data(raw)
        assert result.action == ""

    def test_result_is_frozen(self) -> None:
        raw = {"action": "/", "method": "get", "fields": []}
        result = _to_form_data(raw)
        with pytest.raises((AttributeError, TypeError)):
            result.action = "/other"  # type: ignore[misc]


# ---------- extract_internal_links ----------


class TestExtractInternalLinks:
    def test_returns_only_internal_links(self) -> None:
        page = MagicMock()
        page.eval_on_selector_all.return_value = [
            "https://example.com/about",
            "https://external.com/page",
        ]
        result = extract_internal_links(page, "https://example.com/")
        assert "https://example.com/about" in result
        assert "https://external.com/page" not in result

    def test_deduplicates_links(self) -> None:
        page = MagicMock()
        page.eval_on_selector_all.return_value = [
            "https://example.com/about",
            "https://example.com/about",
        ]
        result = extract_internal_links(page, "https://example.com/")
        assert len(result) == 1

    def test_returns_empty_on_exception(self) -> None:
        page = MagicMock()
        page.eval_on_selector_all.side_effect = Exception("DOM error")
        result = extract_internal_links(page, "https://example.com/")
        assert result == []

    def test_empty_hrefs(self) -> None:
        page = MagicMock()
        page.eval_on_selector_all.return_value = []
        result = extract_internal_links(page, "https://example.com/")
        assert result == []

    def test_filters_empty_href(self) -> None:
        page = MagicMock()
        page.eval_on_selector_all.return_value = ["", "https://example.com/page"]
        result = extract_internal_links(page, "https://example.com/")
        assert "" not in result
        assert "https://example.com/page" in result


# ---------- extract_forms ----------


class TestExtractForms:
    def test_returns_form_data_objects(self) -> None:
        page = MagicMock()
        page.eval_on_selector_all.return_value = [
            {"action": "/search", "method": "get", "fields": []},
        ]
        result = extract_forms(page)
        assert len(result) == 1
        assert result[0].action == "/search"

    def test_returns_empty_on_exception(self) -> None:
        page = MagicMock()
        page.eval_on_selector_all.side_effect = Exception("error")
        result = extract_forms(page)
        assert result == []

    def test_multiple_forms(self) -> None:
        page = MagicMock()
        page.eval_on_selector_all.return_value = [
            {"action": "/search", "method": "get", "fields": []},
            {"action": "/send", "method": "post", "fields": []},
        ]
        result = extract_forms(page)
        assert len(result) == 2

    def test_form_fields_parsed(self) -> None:
        page = MagicMock()
        page.eval_on_selector_all.return_value = [
            {
                "action": "/send",
                "method": "post",
                "fields": [
                    {"field_type": "email", "name": "email", "placeholder": "", "required": True}
                ],
            }
        ]
        result = extract_forms(page)
        assert result[0].fields[0].field_type == "email"
        assert result[0].fields[0].required is True


# ---------- extract_headings ----------


class TestExtractHeadings:
    def test_returns_heading_list(self) -> None:
        page = MagicMock()
        page.eval_on_selector_all.return_value = ["Heading 1", "Heading 2"]
        result = extract_headings(page)
        assert result == ["Heading 1", "Heading 2"]

    def test_returns_empty_on_exception(self) -> None:
        page = MagicMock()
        page.eval_on_selector_all.side_effect = Exception("error")
        result = extract_headings(page)
        assert result == []

    def test_empty_page_returns_empty(self) -> None:
        page = MagicMock()
        page.eval_on_selector_all.return_value = []
        result = extract_headings(page)
        assert result == []


# ---------- extract_page_title ----------


class TestExtractPageTitle:
    def test_returns_stripped_title(self) -> None:
        page = MagicMock()
        page.title.return_value = "  My Page  "
        result = extract_page_title(page)
        assert result == "My Page"

    def test_returns_empty_string_on_exception(self) -> None:
        page = MagicMock()
        page.title.side_effect = Exception("browser error")
        result = extract_page_title(page)
        assert result == ""

    def test_empty_title(self) -> None:
        page = MagicMock()
        page.title.return_value = ""
        result = extract_page_title(page)
        assert result == ""


# ---------- extract_buttons ----------


class TestExtractButtons:
    def test_returns_button_texts(self) -> None:
        page = MagicMock()
        page.eval_on_selector_all.return_value = ["Submit", "Cancel"]
        result = extract_buttons(page)
        assert "Submit" in result
        assert "Cancel" in result

    def test_deduplicates_buttons(self) -> None:
        page = MagicMock()
        page.eval_on_selector_all.return_value = ["Submit", "Submit", "Cancel"]
        result = extract_buttons(page)
        assert result.count("Submit") == 1

    def test_filters_empty_strings(self) -> None:
        page = MagicMock()
        page.eval_on_selector_all.return_value = ["Submit", ""]
        result = extract_buttons(page)
        assert "" not in result

    def test_returns_empty_on_exception(self) -> None:
        page = MagicMock()
        page.eval_on_selector_all.side_effect = Exception("error")
        result = extract_buttons(page)
        assert result == []

    def test_empty_page(self) -> None:
        page = MagicMock()
        page.eval_on_selector_all.return_value = []
        result = extract_buttons(page)
        assert result == []


# ---------- compute_dom_signature ----------


class TestComputeDomSignature:
    def test_returns_default_for_plain_html(self) -> None:
        html = "<html><body><p>Hello</p></body></html>"
        assert compute_dom_signature(html) == "default"

    def test_detects_open_dialog(self) -> None:
        html = '<div role="dialog" id="modal1" aria-modal="true"><p>content</p></div>'
        result = compute_dom_signature(html)
        assert result != "default"
        assert len(result) == 8

    def test_same_elements_produce_same_hash(self) -> None:
        html_a = '<div role="dialog" id="confirm-dlg"></div>'
        html_b = '<section role="dialog" id="confirm-dlg"><p>Are you sure?</p></section>'
        assert compute_dom_signature(html_a) == compute_dom_signature(html_b)

    def test_different_state_produces_different_hash(self) -> None:
        html_expanded = (
            '<button aria-expanded="true" id="menu-toggle" aria-controls="nav-menu">'
            "Menu</button>"
        )
        html_collapsed = (
            '<button aria-expanded="false" id="menu-toggle" aria-controls="nav-menu">'
            "Menu</button>"
        )
        assert compute_dom_signature(html_expanded) != compute_dom_signature(html_collapsed)

    def test_tabpanel_id_is_detected(self) -> None:
        html = '<div role="tabpanel" id="tab-content-1">Tab 1 content</div>'
        result = compute_dom_signature(html)
        assert result != "default"

    def test_form_id_is_included(self) -> None:
        html = '<form id="login-form" method="post"><input type="text"></form>'
        result = compute_dom_signature(html)
        assert result != "default"

    def test_hash_length_is_eight(self) -> None:
        html = '<div role="dialog" id="x"></div>'
        result = compute_dom_signature(html)
        assert len(result) == 8

    def test_duplicate_identifiers_deduplicated(self) -> None:
        # Same id appearing twice should produce same result as appearing once
        html_once = '<div role="dialog" id="dlg1"></div>'
        html_twice = '<div role="dialog" id="dlg1"></div>' '<span id="dlg1" role="dialog"></span>'
        assert compute_dom_signature(html_once) == compute_dom_signature(html_twice)
