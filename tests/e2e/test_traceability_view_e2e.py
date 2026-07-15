"""E2E: トレーサビリティマトリクスの描画（C-3 でトークン化したバッジ・バー）。

view-traceability.html は /traceability/view で単独描画される（SPA ナビ外・
JS/CSS は未配線のフラグメント）。本テストは同ページに traceability.js を注入し、
/traceability/matrix を mock して描画を検証する。C-3 の主眼は「色を CSS クラス
（coverage-*）で付与し、生 hex のインライン style を持たない」ことなので、
CSS を読み込まずとも生成 HTML の class / style を検証すれば十分。

実行方法: make verify-ui
"""

from __future__ import annotations

import json
import os

from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")

MATRIX = {
    "total_requirements": 3,
    "covered_count": 1,
    "coverage_rate": 0.333,
    "requirements": [
        {
            "req_id": "R-001",
            "req_title": "トップ画面",
            "page_url": "https://x/",
            "test_ids": ["TC-1"],
            "coverage": "covered",
        },
        {
            "req_id": "R-002",
            "req_title": "検索画面",
            "page_url": "https://x/s",
            "test_ids": ["TC-2"],
            "coverage": "partial",
        },
        {
            "req_id": "R-003",
            "req_title": "決済画面",
            "page_url": "https://x/c",
            "test_ids": [],
            "coverage": "uncovered",
        },
    ],
}

# traceability.js は escHtml（本来 core.js 定義）に依存するため注入する。
_DEFINE_ESC = """() => {
  window.escHtml = (s) => String(s)
    .split('&').join('&amp;').split('<').join('&lt;').split('>').join('&gt;');
}"""


def _open(page: Page) -> None:
    page.route(
        "**/traceability/matrix**",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(MATRIX)
        ),
    )
    page.goto(f"{BASE_URL}/traceability/view?domain=x")
    page.evaluate(_DEFINE_ESC)
    page.add_script_tag(url="/static/js/traceability.js")
    page.evaluate("() => loadTraceabilityMatrix('x')")
    page.wait_for_selector("#traceability-tbody tr")


class TestTraceabilityView:
    def test_rows_and_badge_classes(self, page: Page) -> None:
        _open(page)
        expect(page.locator("#traceability-tbody tr")).to_have_count(3)
        expect(page.locator(".coverage-badge.coverage-covered")).to_have_count(1)
        expect(page.locator(".coverage-badge.coverage-partial")).to_have_count(1)
        expect(page.locator(".coverage-badge.coverage-uncovered")).to_have_count(1)

    def test_badges_have_no_inline_background_hex(self, page: Page) -> None:
        """C-3: 色は CSS クラスで付与し、生 hex のインライン背景色を持たない。"""
        _open(page)
        for cov in ("covered", "partial", "uncovered"):
            style = (
                page.locator(f".coverage-badge.coverage-{cov}").first.get_attribute("style") or ""
            )
            assert "background" not in style and "#" not in style, (
                f"coverage-{cov} バッジに生の背景色が残っている: {style!r}"
            )

    def test_coverage_bar_segments_present(self, page: Page) -> None:
        _open(page)
        bar = page.locator("#traceability-coverage-bar")
        expect(bar.locator(".coverage-bar-covered")).to_be_attached()
        expect(bar.locator(".coverage-bar-partial")).to_be_attached()
        expect(bar.locator(".coverage-bar-uncovered")).to_be_attached()
        # セグメントの inline style は width のみ（色は CSS クラス由来）
        seg_style = bar.locator(".coverage-bar-covered").first.get_attribute("style") or ""
        assert "#" not in seg_style, f"バー要素に生 hex が残っている: {seg_style!r}"
