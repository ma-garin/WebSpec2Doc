from __future__ import annotations

import hashlib
import json

import networkx as nx

from analyzer.canonicalizer import CanonicalInfo, group_canonical_screens
from analyzer.html_analyzer import AnalyzedPage
from analyzer.test_conditions import (
    attach_observed_validation,
    derive_conditions,
    derive_conditions_with_evidence,
)
from crawler.page_crawler import (
    DEFAULT_DEPTH,
    DEFAULT_MAX_PAGES,
    FieldData,
    FormData,
    ValidationObservation,
    evidence_to_dict,
)

JSON_INDENT = 2
_PII_KEYWORDS: frozenset[str] = frozenset(
    ("payment", "checkout", "billing", "personal", "private", "credit", "card", "ssn", "passport")
)


def generate_json_report(
    pages: list[AnalyzedPage],
    graph: nx.DiGraph,
    target_url: str,
    crawl_depth: int = DEFAULT_DEPTH,
    crawl_max_pages: int = DEFAULT_MAX_PAGES,
    crawled_at: str = "",
    transition_coverage: dict | None = None,
    business_flows: list[dict] | None = None,
    official_names: dict[str, str] | None = None,
) -> str:
    """Serialize crawl results and derived test conditions to structured JSON."""
    canonical_screens = group_canonical_screens(pages)
    screens_data = [
        _screen_dict(p, graph, canonical_screens[p.page_id], official_names) for p in pages
    ]
    screens_canonical = json.dumps(screens_data, ensure_ascii=False, sort_keys=True)
    report_hash = hashlib.sha256(screens_canonical.encode("utf-8")).hexdigest()
    meta: dict = {
        "target_url": target_url,
        "crawl_depth": crawl_depth,
        "max_pages": crawl_max_pages,
        "crawled_at": crawled_at,
        "page_count": len(pages),
        "screen_count": sum(1 for info in canonical_screens.values() if info.is_canonical),
        "report_hash": report_hash,
        "pii_risk_screens": _find_pii_risk_screens(pages),
    }
    if transition_coverage is not None:
        meta["transition_coverage"] = transition_coverage
    if business_flows is not None:
        meta["business_flows"] = business_flows
    return json.dumps(
        {
            "meta": meta,
            "screens": screens_data,
        },
        ensure_ascii=False,
        indent=JSON_INDENT,
    )


def _screen_dict(
    page: AnalyzedPage,
    graph: nx.DiGraph,
    canonical: CanonicalInfo,
    official_names: dict[str, str] | None = None,
) -> dict:
    pd = page.page_data
    pid = page.page_id
    observations = list(pd.validation_observations)
    screen: dict = {
        "page_id": pid,
        "url": pd.url,
        "title": pd.title,
        "headings": list(pd.headings),
        "buttons": list(pd.buttons),
        "forms": [_form_dict(f, observations) for f in pd.forms],
        "transitions": {
            "to": [s for s in graph.successors(pid) if s != pid],
            "from": [p for p in graph.predecessors(pid) if p != pid],
        },
        "canonical_key": canonical.canonical_key,
        "is_canonical": canonical.is_canonical,
        "variation_count": canonical.variation_count,
        "variation_urls": list(canonical.variation_urls),
        "a11y_issues": list(pd.a11y_issues),
        "state_id": pd.state_id,
        "fingerprint": canonical.fingerprint,
        "fingerprint_version": canonical.fingerprint_version,
        "page_states": [
            {
                "state_id": state.state_id,
                "trigger_selector": state.trigger_selector,
                "kind": state.kind,
                "description": state.description,
            }
            for state in pd.page_states
        ],
        "spa_transitions": [
            {"from_url": t.from_url, "to_url": t.to_url, "kind": t.kind} for t in pd.spa_transitions
        ],
    }
    # 参考文書との突合で正式名称が判明した画面にのみ付与する
    # （未指定時は既存のレポート構造・report_hash を変えない）
    official = (official_names or {}).get(pid, "")
    if official:
        screen["official_name"] = official
    return screen


def _form_dict(form: FormData, observations: list[ValidationObservation] | None = None) -> dict:
    return {
        "action": form.action,
        "method": form.method,
        "fields": [_field_dict(f, observations) for f in form.fields],
    }


def _field_dict(
    field: FieldData,
    observations: list[ValidationObservation] | None = None,
) -> dict:
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
        "test_conditions_detail": [
            {
                "description": condition.description,
                "source": condition.source,
                "confidence": condition.confidence,
                "evidence": evidence_to_dict(condition.evidence),
                "observed_result": condition.observed_result,
            }
            for condition in attach_observed_validation(
                derive_conditions_with_evidence(field), field, observations or []
            )
        ],
        "aria_label": field.aria_label,
        "aria_required": field.aria_required,
        "role": field.role,
        "has_visible_label": field.has_visible_label,
        "confidence": field.confidence,
        "evidence": evidence_to_dict(field.evidence),
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


def _find_pii_risk_screens(pages: list[AnalyzedPage]) -> list[str]:
    """URLまたはフォーム送信先に機密キーワードを含む画面IDを返す。"""
    risk_ids: list[str] = []
    for page in pages:
        page_data = page.page_data
        url_has_pii = any(keyword in page_data.url.lower() for keyword in _PII_KEYWORDS)
        form_has_pii = any(
            any(keyword in (form.action or "").lower() for keyword in _PII_KEYWORDS)
            for form in page_data.forms
        )
        if url_has_pii or form_has_pii:
            risk_ids.append(page.page_id)
    return risk_ids
