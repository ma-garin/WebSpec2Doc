"""web/services/qa/testcase_docs.py のユニットテスト。

決定的な steps→日本語手順変換（捏造なし）と HTML レポート生成を検証する。
"""

from __future__ import annotations

from web.services.qa.testcase_docs import (
    LowLevelCase,
    build_low_level_case,
    build_low_level_cases,
    generate_testcases_html,
    translate_step,
)


class TestTranslateStep:
    def test_goto_translates_to_japanese(self) -> None:
        assert translate_step("page.goto('https://example.com/')") == (
            "ブラウザで https://example.com/ を開く"
        )

    def test_click_translates_to_japanese(self) -> None:
        assert translate_step("page.click('#submit')") == "「#submit」をクリックする"

    def test_fill_translates_to_japanese(self) -> None:
        assert translate_step("page.fill('#email', 'a@example.com')") == (
            "#email に「a@example.com」を入力する"
        )

    def test_wait_for_load_state_translates(self) -> None:
        assert (
            translate_step("page.waitForLoadState('domcontentloaded')")
            == "画面の読み込み完了を待つ"
        )

    def test_check_translates(self) -> None:
        assert translate_step("page.check('#agree')") == "#agree をチェックする"

    def test_select_option_translates(self) -> None:
        assert translate_step("page.selectOption('#plan', 'pro')") == ("#plan で「pro」を選択する")

    def test_unmatched_prose_line_passes_through_unchanged(self) -> None:
        """既に日本語プローズの行は捏造せずそのまま返す。"""
        text = "`メール` に代表値を入力"
        assert translate_step(text) == text


class TestBuildLowLevelCase:
    def test_goto_step_becomes_precondition_not_action(self) -> None:
        candidate = {
            "id": "PW-0001",
            "title": "画面表示スモーク",
            "trace_id": "P001",
            "automation_status": "auto",
            "steps": [
                "page.goto('https://example.com/')",
                "画面タイトルまたは主要見出し `トップ` を確認",
            ],
            "expected": "画面が表示され、主要コンテンツが見える",
        }
        case = build_low_level_case(candidate)
        assert isinstance(case, LowLevelCase)
        assert case.preconditions == ("ブラウザで https://example.com/ を開く",)
        assert case.steps == ("画面タイトルまたは主要見出し `トップ` を確認",)
        assert case.expected_result == "画面が表示され、主要コンテンツが見える"
        assert "page.goto(" not in " ".join(case.preconditions + case.steps)

    def test_no_goto_step_yields_placeholder_precondition(self) -> None:
        candidate = {
            "id": "PW-0002",
            "title": "アクセシビリティ自動確認",
            "trace_id": "A11Y-ALL",
            "automation_status": "review",
            "steps": ["主要画面を開く", "axe-core相当のルールで自動検査する"],
            "expected": "重大なWCAG A/AA違反がない",
        }
        case = build_low_level_case(candidate)
        assert case.preconditions == ("（記録された前提条件なし）",)
        assert case.steps == ("主要画面を開く", "axe-core相当のルールで自動検査する")

    def test_empty_steps_yields_placeholders(self) -> None:
        case = build_low_level_case({"id": "PW-0003", "title": "x", "trace_id": "T", "steps": []})
        assert case.preconditions == ("（記録された前提条件なし）",)
        assert case.steps == ("（記録された手順なし）",)
        assert case.expected_result == ""

    def test_build_low_level_cases_preserves_order_and_count(self) -> None:
        candidates = [
            {"id": "PW-0001", "title": "A", "trace_id": "P001", "steps": []},
            {"id": "PW-0002", "title": "B", "trace_id": "P002", "steps": []},
        ]
        cases = build_low_level_cases(candidates)
        assert [c.test_id for c in cases] == ["PW-0001", "PW-0002"]


class TestGenerateTestcasesHtml:
    def test_html_contains_case_fields_and_no_raw_playwright_code(self) -> None:
        candidate = {
            "id": "PW-0001",
            "title": "画面表示スモーク",
            "trace_id": "P001",
            "automation_status": "auto",
            "steps": [
                "page.goto('https://example.com/')",
                "画面タイトルまたは主要見出し `トップ` を確認",
            ],
            "expected": "画面が表示され、主要コンテンツが見える",
        }
        cases = build_low_level_cases([candidate])
        html_doc = generate_testcases_html("example.com", cases, "2026-07-05 12:00")

        assert "<!doctype html>" in html_doc
        assert "example.com" in html_doc
        assert "PW-0001" in html_doc
        assert "画面表示スモーク" in html_doc
        assert "ブラウザで https://example.com/ を開く" in html_doc
        assert "画面が表示され、主要コンテンツが見える" in html_doc
        assert "page.goto(" not in html_doc

    def test_html_escapes_special_characters(self) -> None:
        candidate = {
            "id": "PW-0001",
            "title": "<script>alert(1)</script>",
            "trace_id": "P001",
            "steps": [],
            "expected": "",
        }
        cases = build_low_level_cases([candidate])
        html_doc = generate_testcases_html("example.com", cases, "2026-07-05 12:00")
        assert "<script>alert(1)</script>" not in html_doc
        assert "&lt;script&gt;" in html_doc
