"""ファイルプレビューモーダルの Markdown レンダリング E2E テスト（L3 システムテスト）。

対象（実ユーザーのドッグフーディング報告）:
    QAレポート等の .md 成果物をプレビューすると、見出し・表・箇条書き記号を
    含む生のMarkdownテキストがそのまま <pre> 表示されてしまい読みにくい
    → 軽量Markdownレンダラ（static/js/markdown-lite.js）でHTMLに変換して
      表示するよう修正（static/js/file-preview.js）。

実行方法:
    make verify-ui
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")
FIXTURE_DOMAIN = "e2e-md-preview.example.com"
ROOT = Path(__file__).parent.parent.parent
FIXTURE_DIR = ROOT / "output" / FIXTURE_DOMAIN

MARKDOWN_SOURCE = (
    "# 画面一覧\n\n"
    "## トップ画面\n\n"
    "- 見出し: ようこそ\n"
    "- ボタン: ログイン\n\n"
    "| 項目 | 必須 |\n"
    "|---|---|\n"
    "| メール | ○ |\n"
)


@pytest.fixture(scope="module", autouse=True)
def markdown_fixture() -> Generator[Path, None, None]:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    md_path = FIXTURE_DIR / "screens.md"
    md_path.write_text(MARKDOWN_SOURCE, encoding="utf-8")
    yield md_path
    shutil.rmtree(FIXTURE_DIR, ignore_errors=True)


class TestMarkdownPreviewRendering:

    def test_markdown_preview_escapes_html_in_source(self, page: Page) -> None:
        """Markdown ソース中に生HTMLタグが含まれていてもエスケープされ、
        スクリプトタグとして解釈されないこと（XSS安全性）。"""
        xss_path = FIXTURE_DIR / "xss.md"
        xss_path.write_text("# タイトル\n\n<script>window.__xss=1</script>\n", encoding="utf-8")
        try:
            page.goto(f"{BASE_URL}/")
            page.wait_for_selector("#app-content")
            page.evaluate(
                "([path, label]) => openFilePreview(path, label)",
                [str(xss_path.resolve()), "XSSテスト"],
            )
            expect(page.locator("#file-preview-body h1")).to_have_text("タイトル")
            has_script_tag = page.locator("#file-preview-body script").count()
            assert has_script_tag == 0
            xss_triggered = page.evaluate("() => window.__xss === 1")
            assert xss_triggered is not True
        finally:
            xss_path.unlink(missing_ok=True)
