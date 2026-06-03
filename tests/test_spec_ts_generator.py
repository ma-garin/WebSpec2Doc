from __future__ import annotations

import json
from pathlib import Path

from web.services.spec_ts_generator import (
    FORM_TITLES,
    SMOKE_TITLES,
    TRANSITION_TITLES,
    _apply_filter,
    _esc,
    _extract_url,
    _safe_str,
    compute_filter_counts,
    generate_spec_ts,
)

# ─────────────────────── フィクスチャ ───────────────────────


def _candidates_json(candidates: list[dict]) -> str:
    return json.dumps({"candidates": candidates})


def _candidate(
    title: str = "画面表示スモーク",
    test_id: str = "TC001",
    trace_id: str = "T01",
    steps: list[str] | None = None,
    expected: str = "画面が表示される",
    automation_status: str = "automated",
) -> dict:
    return {
        "title": title,
        "id": test_id,
        "trace_id": trace_id,
        "steps": steps or ["page.goto('https://example.com/')"],
        "expected": expected,
        "automation_status": automation_status,
    }


# ─────────────────────── generate_spec_ts ───────────────────────


class TestGenerateSpecTs:
    def test_empty_candidates_generates_header(self, tmp_path: Path) -> None:
        src = tmp_path / "candidates.json"
        src.write_text(_candidates_json([]), encoding="utf-8")
        out = tmp_path / "spec.ts"

        generate_spec_ts("example.com", src, out)

        content = out.read_text()
        assert "import { test, expect } from '@playwright/test';" in content
        assert "example.com" in content

    def test_normal_candidate_generates_test_block(self, tmp_path: Path) -> None:
        src = tmp_path / "candidates.json"
        src.write_text(
            _candidates_json([_candidate(title="ログイン画面表示", test_id="TC001")]),
            encoding="utf-8",
        )
        out = tmp_path / "spec.ts"

        generate_spec_ts("example.com", src, out)

        content = out.read_text()
        assert "test(" in content
        assert "ログイン画面表示" in content
        assert "TC001" in content
        assert "await expect(page.locator('body')).toBeVisible();" in content

    def test_manual_review_generates_test_skip(self, tmp_path: Path) -> None:
        src = tmp_path / "candidates.json"
        src.write_text(
            _candidates_json([_candidate(automation_status="manual-review")]),
            encoding="utf-8",
        )
        out = tmp_path / "spec.ts"

        generate_spec_ts("example.com", src, out)

        content = out.read_text()
        assert "test.skip(" in content
        assert "manual-review: skip in CI" in content

    def test_url_extracted_from_steps(self, tmp_path: Path) -> None:
        steps = ["page.goto('https://example.com/login')"]
        src = tmp_path / "candidates.json"
        src.write_text(_candidates_json([_candidate(steps=steps)]), encoding="utf-8")
        out = tmp_path / "spec.ts"

        generate_spec_ts("example.com", src, out)

        content = out.read_text()
        assert "await page.goto('https://example.com/login');" in content

    def test_no_url_in_steps_skips_goto(self, tmp_path: Path) -> None:
        src = tmp_path / "candidates.json"
        src.write_text(_candidates_json([_candidate(steps=["クリックする"])]), encoding="utf-8")
        out = tmp_path / "spec.ts"

        generate_spec_ts("example.com", src, out)

        content = out.read_text()
        assert "page.goto" not in content

    def test_filter_smoke_includes_only_smoke(self, tmp_path: Path) -> None:
        candidates = [
            _candidate(title="画面表示スモーク"),
            _candidate(title="フォーム入力"),
            _candidate(title="画面遷移"),
        ]
        src = tmp_path / "candidates.json"
        src.write_text(_candidates_json(candidates), encoding="utf-8")
        out = tmp_path / "spec.ts"

        generate_spec_ts("example.com", src, out, filter_mode="smoke")

        content = out.read_text()
        assert "candidates: 1/3" in content
        assert "フォーム入力" not in content

    def test_filter_transition_includes_smoke_and_transition(self, tmp_path: Path) -> None:
        candidates = [
            _candidate(title="画面表示スモーク"),
            _candidate(title="画面遷移"),
            _candidate(title="フォーム入力"),
        ]
        src = tmp_path / "candidates.json"
        src.write_text(_candidates_json(candidates), encoding="utf-8")
        out = tmp_path / "spec.ts"

        generate_spec_ts("example.com", src, out, filter_mode="transition")

        content = out.read_text()
        assert "candidates: 2/3" in content

    def test_filter_form_includes_smoke_form_required(self, tmp_path: Path) -> None:
        candidates = [
            _candidate(title="画面表示スモーク"),
            _candidate(title="フォーム入力"),
            _candidate(title="必須入力"),
            _candidate(title="画面遷移"),
        ]
        src = tmp_path / "candidates.json"
        src.write_text(_candidates_json(candidates), encoding="utf-8")
        out = tmp_path / "spec.ts"

        generate_spec_ts("example.com", src, out, filter_mode="form")

        content = out.read_text()
        assert "candidates: 3/4" in content

    def test_filter_all_includes_all(self, tmp_path: Path) -> None:
        candidates = [_candidate(), _candidate(title="フォーム入力"), _candidate(title="画面遷移")]
        src = tmp_path / "candidates.json"
        src.write_text(_candidates_json(candidates), encoding="utf-8")
        out = tmp_path / "spec.ts"

        generate_spec_ts("example.com", src, out, filter_mode="all")

        content = out.read_text()
        assert "candidates: 3/3" in content

    def test_missing_file_generates_empty_spec(self, tmp_path: Path) -> None:
        out = tmp_path / "spec.ts"
        generate_spec_ts("example.com", tmp_path / "nonexistent.json", out)

        content = out.read_text()
        assert "import { test, expect }" in content

    def test_invalid_json_generates_empty_spec(self, tmp_path: Path) -> None:
        src = tmp_path / "bad.json"
        src.write_text("not-json", encoding="utf-8")
        out = tmp_path / "spec.ts"

        generate_spec_ts("example.com", src, out)

        content = out.read_text()
        assert "import { test, expect }" in content

    def test_single_quote_in_title_is_escaped(self, tmp_path: Path) -> None:
        src = tmp_path / "candidates.json"
        src.write_text(_candidates_json([_candidate(title="O'Brien のログイン")]), encoding="utf-8")
        out = tmp_path / "spec.ts"

        generate_spec_ts("example.com", src, out)

        content = out.read_text()
        assert "O\\'Brien" in content
        assert "O'Brien" not in content.split("test(")[1]

    def test_expected_comment_included(self, tmp_path: Path) -> None:
        src = tmp_path / "candidates.json"
        src.write_text(
            _candidates_json([_candidate(expected="エラーメッセージが表示される")]),
            encoding="utf-8",
        )
        out = tmp_path / "spec.ts"

        generate_spec_ts("example.com", src, out)

        assert "エラーメッセージが表示される" in out.read_text()

    def test_returns_output_path(self, tmp_path: Path) -> None:
        src = tmp_path / "candidates.json"
        src.write_text(_candidates_json([]), encoding="utf-8")
        out = tmp_path / "spec.ts"

        returned = generate_spec_ts("example.com", src, out)
        assert returned == out


# ─────────────────────── compute_filter_counts ───────────────────────


class TestComputeFilterCounts:
    def test_counts_by_filter(self) -> None:
        candidates = [
            {"title": "画面表示スモーク"},
            {"title": "画面表示スモーク"},
            {"title": "フォーム入力"},
            {"title": "必須入力"},
            {"title": "画面遷移"},
            {"title": "その他"},
        ]
        counts = compute_filter_counts(candidates)

        assert counts["all"] == 6
        assert counts["smoke"] == 2
        assert counts["transition"] == 3  # smoke(2) + 画面遷移(1)
        assert counts["form"] == 4  # smoke(2) + フォーム(1) + 必須(1)

    def test_empty_candidates(self) -> None:
        counts = compute_filter_counts([])
        assert all(v == 0 for v in counts.values())


# ─────────────────────── _apply_filter ───────────────────────


class TestApplyFilter:
    def test_smoke_filter(self) -> None:
        candidates = [{"title": "画面表示スモーク"}, {"title": "フォーム入力"}]
        result = _apply_filter(candidates, "smoke")
        assert len(result) == 1
        assert result[0]["title"] == "画面表示スモーク"

    def test_all_filter_returns_all(self) -> None:
        candidates = [{"title": "A"}, {"title": "B"}, {"title": "C"}]
        assert _apply_filter(candidates, "all") == candidates

    def test_unknown_mode_returns_all(self) -> None:
        candidates = [{"title": "A"}]
        assert _apply_filter(candidates, "unknown_mode") == candidates


# ─────────────────────── _extract_url ───────────────────────


class TestExtractUrl:
    def test_extracts_url_from_goto(self) -> None:
        steps = ["page.goto('https://example.com/login')"]
        assert _extract_url(steps) == "https://example.com/login"

    def test_extracts_double_quote_url(self) -> None:
        steps = ['page.goto("https://example.com/register")']
        assert _extract_url(steps) == "https://example.com/register"

    def test_returns_empty_if_no_url(self) -> None:
        assert _extract_url(["クリックする", "入力する"]) == ""

    def test_returns_empty_for_empty_steps(self) -> None:
        assert _extract_url([]) == ""

    def test_returns_first_url(self) -> None:
        steps = [
            "page.goto('https://first.example.com/')",
            "page.goto('https://second.example.com/')",
        ]
        assert _extract_url(steps) == "https://first.example.com/"


# ─────────────────────── _esc / _safe_str ───────────────────────


class TestEscAndSafeStr:
    def test_esc_escapes_single_quote(self) -> None:
        assert _esc("it's a test") == "it\\'s a test"

    def test_esc_escapes_backslash(self) -> None:
        assert _esc("C:\\path") == "C:\\\\path"

    def test_esc_no_special_chars(self) -> None:
        assert _esc("hello world") == "hello world"

    def test_safe_str_none_returns_empty(self) -> None:
        assert _safe_str(None) == ""

    def test_safe_str_value(self) -> None:
        assert _safe_str("abc") == "abc"
        assert _safe_str(123) == "123"


# ─────────────────────── 定数確認 ───────────────────────


def test_title_constants_are_frozensets() -> None:
    assert isinstance(SMOKE_TITLES, frozenset)
    assert isinstance(TRANSITION_TITLES, frozenset)
    assert isinstance(FORM_TITLES, frozenset)


def test_smoke_titles_subset_of_transition() -> None:
    assert SMOKE_TITLES.issubset(TRANSITION_TITLES)


def test_smoke_titles_subset_of_form() -> None:
    assert SMOKE_TITLES.issubset(FORM_TITLES)
