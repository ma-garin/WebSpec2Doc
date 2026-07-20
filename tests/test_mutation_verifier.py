"""AutoRun の自己検証（ミューテーションテスト）機構のテスト。

背景: 監査で、生成テストが expect(body).toBeVisible() のみで実質的な検証を
していないこと（対象を破壊しても全件PASSする＝ミューテーションスコア0%）が
判明した。この機構は、AutoRun自身がそれを毎回の実行で検出できるようにする。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from web.services.mutation_verifier import build_mutant_spec, run_self_check

_REAL_ASSERTION_SPEC = """import { test, expect } from '@playwright/test';

test('PW-0001 画面表示スモーク [P001]', async ({ page }) => {
  await page.goto('https://example.com/');
  await page.waitForLoadState('domcontentloaded');
  const title = await page.title();
  expect(title.length).toBeGreaterThan(0);
});

test.skip('PW-0002 アクセシビリティ自動確認 [A11Y-ALL]', async () => {
  // manual-review: skip in CI
});

test('PW-0003 必須入力 [P011-F01-I01]', async ({ page }) => {
  await page.goto('https://example.com/reserve.html');
  await page.waitForLoadState('domcontentloaded');
  await page.locator('#date').fill('');
  const fieldValid = await page.locator('#date').evaluate((el) => el.checkValidity());
  expect(fieldValid).toBe(false);
});
"""

_WEAK_SPEC = """import { test, expect } from '@playwright/test';

test('PW-0001 画面表示スモーク [P001]', async ({ page }) => {
  await page.goto('https://example.com/');
  await expect(page.locator('body')).toBeVisible();
});
"""


def test_build_mutant_spec_injects_route_into_every_real_test(tmp_path: Path) -> None:
    spec_path = tmp_path / "autorun.spec.ts"
    spec_path.write_text(_REAL_ASSERTION_SPEC, encoding="utf-8")
    mutant_path = tmp_path / "mutant.spec.ts"

    injected = build_mutant_spec(spec_path, mutant_path)

    assert injected == 2  # test.skip は対象外
    content = mutant_path.read_text(encoding="utf-8")
    assert content.count("page.route('**/*'") == 2
    # test.skip 自体は書き換えない
    assert "manual-review: skip in CI" in content


def test_build_mutant_spec_never_touches_test_skip(tmp_path: Path) -> None:
    spec_path = tmp_path / "autorun.spec.ts"
    spec_path.write_text(_REAL_ASSERTION_SPEC, encoding="utf-8")
    mutant_path = tmp_path / "mutant.spec.ts"

    build_mutant_spec(spec_path, mutant_path)

    content = mutant_path.read_text(encoding="utf-8")
    skip_block_start = content.index("test.skip(")
    skip_block = content[skip_block_start : skip_block_start + 120]
    assert "page.route" not in skip_block


def test_run_self_check_reports_zero_score_for_weak_spec(tmp_path: Path) -> None:
    spec_path = tmp_path / "autorun.spec.ts"
    spec_path.write_text(_WEAK_SPEC, encoding="utf-8")

    fake_result = {
        "ok": True,
        "passed": 1,
        "failed": 0,
        "skipped": 0,
        "total": 1,
        "duration_ms": 100,
        "tests": [{"title": "PW-0001 画面表示スモーク [P001]", "status": "passed"}],
    }
    with patch(
        "web.services.mutation_verifier.run_playwright", return_value=fake_result
    ) as mock_run:
        result = run_self_check(spec_path, tmp_path, per_test_timeout_sec=5)

    assert mock_run.called
    assert result["applicable"] is True
    assert result["score"] == 0.0
    assert result["survivor_count"] == 1
    assert "PW-0001 画面表示スモーク [P001]" in result["survivors"]


def test_run_self_check_reports_full_score_for_real_assertions(tmp_path: Path) -> None:
    spec_path = tmp_path / "autorun.spec.ts"
    spec_path.write_text(_REAL_ASSERTION_SPEC, encoding="utf-8")

    fake_result = {
        "ok": True,
        "passed": 0,
        "failed": 2,
        "skipped": 0,
        "total": 2,
        "duration_ms": 200,
        "tests": [
            {"title": "PW-0001 画面表示スモーク [P001]", "status": "failed"},
            {"title": "PW-0003 必須入力 [P011-F01-I01]", "status": "failed"},
        ],
    }
    with patch("web.services.mutation_verifier.run_playwright", return_value=fake_result):
        result = run_self_check(spec_path, tmp_path, per_test_timeout_sec=5)

    assert result["score"] == 100.0
    assert result["survivor_count"] == 0


def test_run_self_check_not_applicable_when_no_real_tests(tmp_path: Path) -> None:
    spec_path = tmp_path / "autorun.spec.ts"
    spec_path.write_text(
        "import { test } from '@playwright/test';\n\n"
        "test.skip('PW-0001 x [P001]', async () => {});\n",
        encoding="utf-8",
    )

    result = run_self_check(spec_path, tmp_path)

    assert result["applicable"] is False
