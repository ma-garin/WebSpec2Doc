from __future__ import annotations

import hashlib
import json

import networkx as nx

from analyzer.html_analyzer import AnalyzedPage
from crawler.page_crawler import FieldData, FormData, PageData
from generator.json_reporter import generate_json_report


def _page(url: str, title: str, forms: tuple[FormData, ...] = ()) -> PageData:
    return PageData(url, title, (title,), (), forms, None)


def _analyzed(page: PageData, page_id: str = "P001") -> AnalyzedPage:
    return AnalyzedPage(page_data=page, page_id=page_id, buttons=(), nav_elements=())


def _graph(*page_ids: str) -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_nodes_from(page_ids)
    return graph


def _report(page: PageData) -> dict:
    return json.loads(
        generate_json_report([_analyzed(page)], _graph("P001"), "https://example.com/")
    )


def test_report_hash_exists_in_meta() -> None:
    report = _report(_page("https://example.com/", "Top"))
    report_hash = report["meta"]["report_hash"]
    assert isinstance(report_hash, str)
    assert len(report_hash) == 64


def test_report_hash_is_sha256_of_screens() -> None:
    report = _report(_page("https://example.com/", "Top"))
    canonical = json.dumps(report["screens"], ensure_ascii=False, sort_keys=True)
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert report["meta"]["report_hash"] == expected


def test_report_hash_changes_when_screens_change() -> None:
    first = _report(_page("https://example.com/", "Top"))["meta"]["report_hash"]
    second = _report(_page("https://example.com/about", "About"))["meta"]["report_hash"]
    assert first != second


def test_pii_risk_screens_empty_for_safe_pages() -> None:
    report = _report(_page("https://example.com/search", "検索"))
    assert report["meta"]["pii_risk_screens"] == []


def test_pii_risk_screens_detects_payment_url() -> None:
    report = _report(_page("https://example.com/payment/confirm", "決済確認"))
    assert report["meta"]["pii_risk_screens"] == ["P001"]


def test_pii_risk_screens_detects_sensitive_form_action() -> None:
    field = FieldData("text", "card_number", "", True)
    form = FormData("/checkout/payment", "post", (field,))
    report = _report(_page("https://example.com/cart", "カート", (form,)))
    assert report["meta"]["pii_risk_screens"] == ["P001"]


def test_pii_risk_screens_is_list_in_meta() -> None:
    report = _report(_page("https://example.com/", "Top"))
    assert isinstance(report["meta"]["pii_risk_screens"], list)
