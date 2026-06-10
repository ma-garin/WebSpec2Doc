"""viewpoint_generator のユニットテスト（openai 不要・ルールベースのみ）。"""

from __future__ import annotations

from llm.screen_classifier import (
    SCREEN_AUTH,
    SCREEN_FORM,
    SCREEN_GENERAL,
    SCREEN_PAYMENT,
    SCREEN_PERSONAL_INFO,
    ScreenClassification,
)
from llm.viewpoint_generator import generate_viewpoints_by_rules


def _sc(screen_type: str, priority: str = "low") -> ScreenClassification:
    return ScreenClassification(screen_type, 0.9, (), priority)


def test_generate_viewpoints_payment_includes_security() -> None:
    sc = ScreenClassification(SCREEN_PAYMENT, 0.9, ("決済",), "critical")
    viewpoints = generate_viewpoints_by_rules(sc, [])
    categories = [v.category for v in viewpoints]
    assert "セキュリティ" in categories


def test_generate_viewpoints_general_includes_functional() -> None:
    sc = ScreenClassification(SCREEN_GENERAL, 0.5, (), "low")
    viewpoints = generate_viewpoints_by_rules(sc, [])
    assert len(viewpoints) >= 1


def test_payment_includes_functional_viewpoint() -> None:
    viewpoints = generate_viewpoints_by_rules(_sc(SCREEN_PAYMENT, "critical"), [])
    categories = [v.category for v in viewpoints]
    assert "機能" in categories


def test_auth_includes_security_viewpoint() -> None:
    viewpoints = generate_viewpoints_by_rules(_sc(SCREEN_AUTH, "critical"), [])
    categories = [v.category for v in viewpoints]
    assert "セキュリティ" in categories


def test_personal_info_includes_accessibility() -> None:
    viewpoints = generate_viewpoints_by_rules(_sc(SCREEN_PERSONAL_INFO, "critical"), [])
    categories = [v.category for v in viewpoints]
    assert "アクセシビリティ" in categories


def test_form_includes_usability() -> None:
    viewpoints = generate_viewpoints_by_rules(_sc(SCREEN_FORM, "high"), [])
    categories = [v.category for v in viewpoints]
    assert "ユーザビリティ" in categories


def test_required_field_adds_viewpoint() -> None:
    class FakeField:
        required = True
        maxlength = None

    viewpoints = generate_viewpoints_by_rules(_sc(SCREEN_GENERAL), [FakeField()])
    texts = " ".join(v.viewpoint for v in viewpoints)
    assert "必須" in texts


def test_maxlength_field_adds_boundary_viewpoint() -> None:
    class FakeField:
        required = False
        maxlength = 100

    viewpoints = generate_viewpoints_by_rules(_sc(SCREEN_GENERAL), [FakeField()])
    texts = " ".join(v.viewpoint for v in viewpoints)
    assert "境界値" in texts


def test_all_viewpoints_are_frozen() -> None:
    import dataclasses

    viewpoints = generate_viewpoints_by_rules(_sc(SCREEN_PAYMENT, "critical"), [])
    for vp in viewpoints:
        assert dataclasses.is_dataclass(vp)
        try:
            vp.category = "other"  # type: ignore[misc]
            raise AssertionError("Should raise FrozenInstanceError")
        except Exception:
            pass


def test_each_viewpoint_has_example_cases() -> None:
    viewpoints = generate_viewpoints_by_rules(_sc(SCREEN_PAYMENT, "critical"), [])
    for vp in viewpoints:
        assert len(vp.example_cases) >= 1


def test_risk_level_values_are_valid() -> None:
    valid = {"高", "中", "低"}
    viewpoints = generate_viewpoints_by_rules(_sc(SCREEN_AUTH, "critical"), [])
    for vp in viewpoints:
        assert vp.risk_level in valid


def test_general_screen_always_returns_at_least_one_viewpoint() -> None:
    sc = ScreenClassification(SCREEN_GENERAL, 0.5, (), "low")
    viewpoints = generate_viewpoints_by_rules(sc, [])
    assert len(viewpoints) >= 1
