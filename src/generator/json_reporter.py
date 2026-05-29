from __future__ import annotations

import json

import networkx as nx

from analyzer.html_analyzer import AnalyzedPage
from analyzer.test_conditions import derive_conditions
from crawler.page_crawler import DEFAULT_DEPTH, DEFAULT_MAX_PAGES, FieldData, FormData

JSON_INDENT = 2


def generate_json_report(
    pages: list[AnalyzedPage],
    graph: nx.DiGraph,
    target_url: str,
    crawl_depth: int = DEFAULT_DEPTH,
    crawl_max_pages: int = DEFAULT_MAX_PAGES,
    crawled_at: str = "",
) -> str:
    """Serialize crawl results and derived test conditions to structured JSON."""
    return json.dumps(
        {
            "meta": {
                "target_url": target_url,
                "crawl_depth": crawl_depth,
                "max_pages": crawl_max_pages,
                "crawled_at": crawled_at,
                "page_count": len(pages),
            },
            "screens": [_screen_dict(p, graph) for p in pages],
        },
        ensure_ascii=False,
        indent=JSON_INDENT,
    )


def _screen_dict(page: AnalyzedPage, graph: nx.DiGraph) -> dict:
    pd = page.page_data
    pid = page.page_id
    return {
        "page_id": pid,
        "url": pd.url,
        "title": pd.title,
        "headings": list(pd.headings),
        "buttons": list(pd.buttons),
        "forms": [_form_dict(f) for f in pd.forms],
        "transitions": {
            "to": [s for s in graph.successors(pid) if s != pid],
            "from": [p for p in graph.predecessors(pid) if p != pid],
        },
    }


def _form_dict(form: FormData) -> dict:
    return {
        "action": form.action,
        "method": form.method,
        "fields": [_field_dict(f) for f in form.fields],
    }


def _field_dict(field: FieldData) -> dict:
    return {
        "name": field.name,
        "element_id": field.element_id,
        "field_type": field.field_type,
        "required": field.required,
        "maxlength": field.maxlength,
        "minlength": field.minlength,
        "min_value": field.min_value,
        "max_value": field.max_value,
        "pattern": field.pattern,
        "placeholder": field.placeholder,
        "default": field.default,
        "options": list(field.options),
        "locators": _locator_candidates(field),
        "test_conditions": list(derive_conditions(field)),
    }


def _locator_candidates(field: FieldData) -> list[str]:
    candidates: list[str] = []
    if field.element_id:
        candidates.append(f"#{field.element_id}")
    if field.name:
        tag = _field_type_tag(field.field_type)
        candidates.append(f'{tag}[name="{field.name}"]')
    return candidates


def _field_type_tag(field_type: str) -> str:
    if field_type in ("select", "textarea"):
        return field_type
    return "input"
