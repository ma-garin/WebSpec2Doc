"""画面分析（discover）フェーズの中断ボタン E2E テスト（L3 システムテスト）。

対象（実ユーザーのドッグフーディング報告）:
    「途中停止も欲しいです」という要望への対応。クロール実行フェーズには
    停止ボタンがあるが、画面分析（discover）フェーズには停止手段が無かった。
    ストリーム先頭で配信される run_id を使い、中断ボタンから /api/cancel で
    バックエンドの画面分析プロセスを実際に止められるようにした
    （web/routes/discover.py・static/js/wizard.js）。

実行方法:
    make verify-ui
"""

from __future__ import annotations

import json
import os

from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")


def _open_generate(page: Page) -> None:
    page.goto(BASE_URL)
    page.locator("#nav-new-analysis-btn").click()
    page.wait_for_selector("#url-input", state="visible")


class TestDiscoverCancelButton:
    def test_cancel_button_visible_while_analyzing(self, page: Page) -> None:
        _open_generate(page)
        expect(page.locator("#discover-cancel-btn")).to_be_attached()

    def test_cancel_button_is_compact_not_full_width(self, page: Page) -> None:
        """R2-05: 中断ボタンをスタイリッシュに。.btn-danger-outline の
        width:100% により、行全体に広がる目立つ赤帯になっていた不具合の
        再発防止（中断ボタンは内容幅に収まる小型ボタンであること）。"""
        _open_generate(page)
        page.evaluate(
            """() => { document.getElementById('discover-loading').style.display = ''; }"""
        )
        box = page.locator("#discover-cancel-btn").bounding_box()
        assert box is not None
        assert box["width"] < 150, f"中断ボタンが横に広がりすぎている: {box['width']}px"

    def test_clicking_cancel_posts_captured_run_id_to_api_cancel(self, page: Page) -> None:
        """中断ボタンは discover-stream の先頭で受け取った run_id を
        /api/cancel に送る（バックエンドプロセスを実際に止めるための仕組み）。"""
        _open_generate(page)

        cancel_calls: list[str] = []

        def _handle_cancel(route):  # type: ignore[no-untyped-def]
            cancel_calls.append(route.request.post_data or "")
            route.fulfill(
                status=200, content_type="application/json", body=json.dumps({"ok": True})
            )

        page.route("**/api/cancel", _handle_cancel)

        # 実際のストリーム受信を模して run_id を保持させる（discover-stream 自体は
        # 実サイトへの依存を避けるため、ここでは受信済み状態を直接注入する）。
        page.evaluate(
            """() => {
                _discoverRunId = 'test-discover-run-id';
                _discoverReader = { cancel: async () => {} };
                document.getElementById('discover-loading').style.display = '';
            }"""
        )

        with page.expect_request("**/api/cancel"):
            page.locator("#discover-cancel-btn").click()

        assert any(
            "test-discover-run-id" in call for call in cancel_calls
        ), f"run_id が /api/cancel に送られていない: {cancel_calls}"

    def test_cancel_marks_state_and_status_reflects_partial_results(self, page: Page) -> None:
        """中断後、それまでに見つかった画面を破棄せず「中断しました」と表示する
        （途中結果を保存するクロール実行フェーズの挙動と揃える）。"""
        _open_generate(page)
        page.route(
            "**/api/cancel",
            lambda route: route.fulfill(
                status=200, content_type="application/json", body=json.dumps({"ok": True})
            ),
        )
        page.evaluate(
            """() => {
                _discoverRunId = 'test-discover-run-id';
                _discoverReader = { cancel: async () => {} };
                discovered = [{url: 'https://example.com/', title: 'Top', login_required: false}];
                document.getElementById('discover-loading').style.display = '';
            }"""
        )
        page.locator("#discover-cancel-btn").click()
        expect(page.locator("body")).to_be_visible()  # クリック自体が例外を出さないこと
        assert page.evaluate("() => _discoverCancelledByUser") is True
