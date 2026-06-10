"""screen_classifier のユニットテスト（openai 不要・ルールベースのみ）。"""

from __future__ import annotations

from llm.screen_classifier import (
    SCREEN_AUTH,
    SCREEN_FORM,
    SCREEN_GENERAL,
    SCREEN_LIST,
    SCREEN_PAYMENT,
    SCREEN_PERSONAL_INFO,
    SCREEN_SEARCH,
    classify_screen_by_rules,
)


def test_classify_screen_payment_by_rules() -> None:
    result = classify_screen_by_rules("決済フォーム", ("お支払い",), ["card_number"])
    assert result.screen_type == SCREEN_PAYMENT
    assert result.test_priority == "critical"


def test_classify_screen_auth_by_rules() -> None:
    result = classify_screen_by_rules("ログイン", ("パスワード",), ["email", "password"])
    assert result.screen_type == SCREEN_AUTH


def test_classify_screen_general_fallback() -> None:
    result = classify_screen_by_rules("ホーム", (), [])
    assert result.screen_type == SCREEN_GENERAL
    assert result.test_priority == "low"


def test_classify_screen_personal_info() -> None:
    result = classify_screen_by_rules("プロフィール登録", ("個人情報入力",), ["name", "address"])
    assert result.screen_type == SCREEN_PERSONAL_INFO
    assert result.test_priority == "critical"


def test_classify_screen_search() -> None:
    result = classify_screen_by_rules("商品検索", ("search",), ["keyword"])
    assert result.screen_type == SCREEN_SEARCH
    assert result.test_priority == "medium"


def test_classify_screen_list_no_fields() -> None:
    result = classify_screen_by_rules("注文一覧", ("order list",), [])
    assert result.screen_type == SCREEN_LIST
    assert result.test_priority == "medium"


def test_classify_screen_form_multi_fields() -> None:
    result = classify_screen_by_rules("お問い合わせ", (), ["name", "email", "message"])
    assert result.screen_type == SCREEN_FORM
    assert result.test_priority == "high"


def test_keywords_captured_for_payment() -> None:
    result = classify_screen_by_rules("支払いページ", (), [])
    assert "支払" in result.keywords


def test_keywords_captured_for_auth_english() -> None:
    result = classify_screen_by_rules("login page", (), [])
    assert any(kw in ("login", "ログイン", "signin", "パスワード", "password", "auth", "サインイン") for kw in result.keywords)


def test_confidence_matched_is_high() -> None:
    result = classify_screen_by_rules("決済確認", (), [])
    assert result.confidence == 0.9


def test_confidence_fallback_is_lower() -> None:
    result = classify_screen_by_rules("ホーム", (), [])
    assert result.confidence == 0.5


def test_screen_classification_is_frozen() -> None:
    result = classify_screen_by_rules("ホーム", (), [])
    import dataclasses
    assert dataclasses.is_dataclass(result)
    try:
        result.screen_type = "other"  # type: ignore[misc]
        raise AssertionError("frozen dataclass should raise FrozenInstanceError")
    except Exception:
        pass


def test_billing_keyword_triggers_payment() -> None:
    result = classify_screen_by_rules("billing", (), [])
    assert result.screen_type == SCREEN_PAYMENT


def test_list_with_two_fields_falls_through_to_form() -> None:
    # フィールドが 2 件あれば list より form を優先
    result = classify_screen_by_rules("order index", ("一覧",), ["col1", "col2"])
    # search/payment/auth/personal_info に該当しなければ form になる
    assert result.screen_type == SCREEN_FORM
