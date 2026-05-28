from __future__ import annotations

from analyzer.html_analyzer import AnalyzedPage


def summarize_forms(pages: list[AnalyzedPage]) -> list[dict[str, str | bool]]:
    return [
        {
            "page_id": page.page_id,
            "url": page.page_data.url,
            "field_type": field.field_type,
            "name": field.name,
            "placeholder": field.placeholder,
            "required": field.required,
        }
        for page in pages
        for form in page.page_data.forms
        for field in form.fields
    ]
