"""カタログと集約の契約テスト（AC-W0-1 / AC-W0-2）。"""

from __future__ import annotations

import pytest

from ux.a11y import (
    CATALOG, CATALOG_BY_ID, Finding, Implementation, PageA11yResult, Status,
    aggregate_status, build_page_result, ui_group,
)
from ux.a11y.catalog import coverage, critical_aa_rules, declared_rules, validate_catalog


def _f(rule, status):
    return Finding(rule, status)


def test_catalog_consistent():
    assert validate_catalog() == []


def test_unimplemented_have_reason_and_never_declared():
    for r in CATALOG:
        if r.implementation is Implementation.NONE:
            assert r.reason_if_unimplemented
            assert not r.declared


def test_legacy_example_mapping():
    assert CATALOG_BY_ID["name.image"].legacy_axe_ids[0] == "image-alt"
    assert len(CATALOG_BY_ID["name.aria-role-required"].legacy_axe_ids) == 7


def test_critical_aa_subset_of_declared():
    ids = {r.rule_id for r in critical_aa_rules()}
    assert {"name.image", "name.form-field", "name.button", "aria.roles"} <= ids
    assert ids <= {r.rule_id for r in declared_rules()}
    assert "visual.contrast" in ids and "bp.tabindex" not in ids


def test_coverage_counts_total():
    assert sum(coverage().values()) == len(CATALOG)


@pytest.mark.parametrize(
    "statuses,expected",
    [
        ([Status.PASS, Status.VIOLATION], Status.VIOLATION),
        ([Status.PASS, Status.PASS], Status.PASS),
        ([], Status.INAPPLICABLE),
        ([Status.CANT_TELL], Status.CANT_TELL),
        ([Status.PASS, Status.CANT_TELL], Status.CANT_TELL),
        ([Status.NOT_IMPLEMENTED], Status.CANT_TELL),
    ],
)
def test_aggregate_implemented(statuses, expected):
    spec = CATALOG_BY_ID["name.image"]
    assert aggregate_status(spec, [_f(spec.rule_id, s) for s in statuses]) is expected


def test_not_implemented_never_pass():
    spec = next(r for r in CATALOG if r.implementation is Implementation.NONE)
    assert aggregate_status(spec, [_f(spec.rule_id, Status.PASS)]) is Status.NOT_IMPLEMENTED
    real = CATALOG_BY_ID["name.image"]
    assert aggregate_status(real, [_f(real.rule_id, Status.PASS)], executed=False) is Status.NOT_IMPLEMENTED
    assert Status.NOT_EVALUATED is Status.NOT_IMPLEMENTED
    assert ui_group(Status.NOT_IMPLEMENTED) == ui_group(Status.CANT_TELL) == "unevaluated"


def test_page_result_has_every_rule_and_error_is_not_clean():
    res = build_page_result("u", CATALOG, [_f("name.image", Status.VIOLATION)])
    assert [r.rule_id for r in res.rules] == [r.rule_id for r in CATALOG]
    assert CATALOG_BY_ID and res.violations()[0].rule_id == "name.image"
    failed = build_page_result("u", CATALOG, [_f("name.image", Status.PASS)], error="timeout")
    assert failed.error == "timeout"
    assert all(r.status is Status.NOT_IMPLEMENTED for r in failed.rules)
    assert isinstance(failed, PageA11yResult)


def test_legacy_conversion():
    from ux.a11y import to_legacy_violations

    res = build_page_result("u", CATALOG, [Finding("name.image", Status.VIOLATION, selector="img", impact="critical")])
    v = to_legacy_violations(res, CATALOG_BY_ID)[0]
    assert v.rule_id == "image-alt" and v.evidence.selector == "img"
    assert "wcag111" in v.wcag_tags
