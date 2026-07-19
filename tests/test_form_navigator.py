"""フォーム到達クロールの安全設計（第9弾 ⑧）の契約。

これは送信を伴う例外機能のため、**安全弁が確実に効くこと**を最優先で固定する。
"""

from __future__ import annotations

import pytest

from crawler.form_navigator import (
    ENV_FLAG,
    audit_record_for,
    form_submit_enabled,
    host_allowed,
    is_destructive_button,
    plan_form_submission,
    safe_value_for,
)

# ─────────────────── 二重オプトイン ───────────────────


def test_disabled_without_env_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_FLAG, raising=False)

    assert form_submit_enabled(explicit_flag=True) is False


def test_disabled_without_explicit_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_FLAG, "1")

    assert form_submit_enabled(explicit_flag=False) is False


def test_enabled_only_with_both(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_FLAG, "1")

    assert form_submit_enabled(explicit_flag=True) is True


# ─────────────────── ホスト許可リスト ───────────────────


def test_empty_allowlist_denies_all() -> None:
    assert host_allowed("https://example.com/", []) is False


def test_host_outside_allowlist_denied() -> None:
    assert host_allowed("https://evil.com/", ["example.com"]) is False


def test_host_in_allowlist_permitted() -> None:
    assert host_allowed("https://example.com/path", ["example.com"]) is True


# ─────────────────── 破壊的ボタン ───────────────────


@pytest.mark.parametrize("text", ["削除", "購入する", "Delete", "Pay now", "退会手続き"])
def test_destructive_buttons_detected(text: str) -> None:
    assert is_destructive_button(text) is True


@pytest.mark.parametrize("text", ["検索", "次へ", "Search", "Continue"])
def test_safe_buttons_pass(text: str) -> None:
    assert is_destructive_button(text) is False


def test_plan_skips_destructive_submit() -> None:
    form = {"fields": [{"name": "q", "field_type": "text"}]}

    assert plan_form_submission(form, "削除") is None


# ─────────────────── 入力値・計画 ───────────────────


def test_safe_value_uses_measured_option_first() -> None:
    assert safe_value_for({"field_type": "select", "options": ["A", "B"]}) == "A"


def test_safe_value_by_type() -> None:
    assert safe_value_for({"field_type": "email"}) == "test@example.com"


def test_plan_excludes_hidden_and_submit_fields() -> None:
    form = {
        "fields": [
            {"name": "q", "field_type": "text"},
            {"name": "token", "field_type": "hidden"},
            {"name": "go", "field_type": "submit"},
        ]
    }

    plan = plan_form_submission(form, "検索")

    assert set(plan["fills"]) == {"q"}


# ─────────────────── 監査ログ（値を含めない） ───────────────────


def test_audit_record_excludes_values() -> None:
    form = {"fields": [{"name": "email", "field_type": "email"}]}
    plan = plan_form_submission(form, "登録")

    record = audit_record_for("https://example.com/signup", plan)

    assert record["event"] == "form_submitted"
    assert record["field_names"] == ["email"]
    # 値（test@example.com 等）が監査に載らないこと
    assert "test@example.com" not in str(record)
    assert "fills" not in record
