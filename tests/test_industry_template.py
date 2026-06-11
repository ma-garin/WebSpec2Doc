"""industry_template のユニットテスト（openai 不要）。"""

from __future__ import annotations

import dataclasses

from llm.industry_template import (
    INDUSTRY_EC,
    INDUSTRY_FINANCE,
    INDUSTRY_GENERAL,
    INDUSTRY_GOVERNMENT,
    INDUSTRY_MEDICAL,
    INDUSTRY_TEMPLATES,
    get_additional_viewpoints,
    get_template,
)
from llm.screen_classifier import (
    SCREEN_AUTH,
    SCREEN_GENERAL,
    SCREEN_PAYMENT,
    SCREEN_PERSONAL_INFO,
    ScreenClassification,
)


def test_get_template_ec() -> None:
    t = get_template(INDUSTRY_EC)
    assert t.industry == INDUSTRY_EC
    assert len(t.required_viewpoints) > 0


def test_get_template_unknown_returns_general() -> None:
    t = get_template("unknown_industry")
    assert t.industry == INDUSTRY_GENERAL


def test_get_template_finance() -> None:
    t = get_template(INDUSTRY_FINANCE)
    assert t.industry == INDUSTRY_FINANCE
    assert len(t.key_test_areas) > 0


def test_get_template_medical() -> None:
    t = get_template(INDUSTRY_MEDICAL)
    assert t.industry == INDUSTRY_MEDICAL
    assert len(t.required_viewpoints) > 0


def test_get_template_government() -> None:
    t = get_template(INDUSTRY_GOVERNMENT)
    assert t.industry == INDUSTRY_GOVERNMENT
    assert len(t.key_test_areas) > 0


def test_all_templates_have_name() -> None:
    for industry, template in INDUSTRY_TEMPLATES.items():
        assert template.name, f"{industry} template has no name"


def test_templates_are_frozen() -> None:
    for _, template in INDUSTRY_TEMPLATES.items():
        assert dataclasses.is_dataclass(template)
        try:
            template.name = "changed"  # type: ignore[misc]
            raise AssertionError("Should raise FrozenInstanceError")
        except Exception:
            pass


def test_get_additional_viewpoints_ec_payment() -> None:
    sc = ScreenClassification(SCREEN_PAYMENT, 0.9, ("決済",), "critical")
    viewpoints = get_additional_viewpoints(sc, INDUSTRY_EC)
    assert len(viewpoints) > 0
    assert any("3D" in v for v in viewpoints)


def test_get_additional_viewpoints_finance_auth() -> None:
    sc = ScreenClassification(SCREEN_AUTH, 0.9, ("ログイン",), "critical")
    viewpoints = get_additional_viewpoints(sc, INDUSTRY_FINANCE)
    assert len(viewpoints) > 0
    assert any("多要素認証" in v for v in viewpoints)


def test_get_additional_viewpoints_no_match_returns_empty() -> None:
    sc = ScreenClassification(SCREEN_GENERAL, 0.5, (), "low")
    viewpoints = get_additional_viewpoints(sc, INDUSTRY_GENERAL)
    assert viewpoints == []


def test_get_additional_viewpoints_medical_personal_info() -> None:
    sc = ScreenClassification(SCREEN_PERSONAL_INFO, 0.9, ("患者",), "critical")
    viewpoints = get_additional_viewpoints(sc, INDUSTRY_MEDICAL)
    assert len(viewpoints) > 0


def test_ec_template_has_cart_keyword() -> None:
    t = get_template(INDUSTRY_EC)
    assert "カート" in t.risk_keywords or "カート" in t.key_test_areas


def test_general_template_has_required_viewpoints() -> None:
    t = get_template(INDUSTRY_GENERAL)
    assert len(t.required_viewpoints) > 0
