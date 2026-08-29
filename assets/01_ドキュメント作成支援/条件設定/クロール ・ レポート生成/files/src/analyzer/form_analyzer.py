from __future__ import annotations

from analyzer.html_analyzer import AnalyzedPage
from crawler.page_crawler import evidence_to_dict


def summarize_forms(pages: list[AnalyzedPage]) -> list[dict[str, object]]:
    return [
        {
            "page_id": page.page_id,
            "url": page.page_data.url,
            "field_type": field.field_type,
            "name": field.name,
            "placeholder": field.placeholder,
            "required": field.required,
            "confidence": field.confidence,
            "evidence": evidence_to_dict(field.evidence),
        }
        for page in pages
        for form in page.page_data.forms
        for field in form.fields
    ]
