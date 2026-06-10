"""AutoRun 承認モーダル E2E テスト（L3 システムテスト）。

目的:
    承認モーダルの構造・操作性・視認性をブラウザ上で検証する。
    INC-2026-001 の再発防止のため、モーダル要素の存在・スタイル・
    操作性を機械的に確認する。

テスト方針:
    - TestApprovalModalStructure: JS 直接注入でモーダルの DOM/スタイルを検証
    - TestApprovalModalViaRoute: page.route() で API をモックし実際の JS フロー経由でモーダルを検証
      → 実際のポーリング → _autorunRender() → モーダル自動表示 の経路をテスト

実行方法:
    make verify-ui
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://127.0.0.1:8765"

_MOCK_STATUS_AWAITING = {
    "status": "awaiting_approval",
    "job_id": "test-job-e2e",
    "log": ["仕様書生成完了", "QA成果物生成完了", "スクリプト生成完了"],
    "outputs": {"spec_ts": "/dummy/autorun.spec.ts"},
    "test_results": None,
    "step_data": {"scripts": {"all": 42, "smoke": 14, "transition": 28, "form": 20}},
    "started_at": "2026-06-03T10:00:00",
    "elapsed_sec": 120,
    "error": None,
    "finished_at": None,
    "input_request": None,
    "run_policy": {},
}

_MOCK_PREVIEW = {
    "candidates": [
        {
            "id": "PW-001",
            "title": "画面表示スモーク",
            "automation_status": "auto",
            "trace_id": "P001",
            "steps": ["page.goto('https://example.com/')"],
            "expected": "表示される",
        },
        {
            "id": "PW-002",
            "title": "ログインフォーム",
            "automation_status": "auto",
            "trace_id": "P002",
            "steps": ["page.goto('https://example.com/login')"],
            "expected": "ログインできる",
        },
    ],
    "spec_content": "import { test, expect } from '@playwright/test';",
    "summary": {
        "total": 42,
        "by_status": {"auto": 40, "manual-review": 2},
        "by_title": {"画面表示スモーク": 14, "画面遷移": 28},
        "filter_counts": {"all": 42, "smoke": 14, "transition": 28, "form": 20},
    },
}


@pytest.fixture()
def autorun_page(page: Page) -> Page:
    """AutoRun ビューを開いた状態のページを返す。"""
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    autorun_nav = page.locator(".app-nav-item").filter(has_text="AutoRun").first
    if autorun_nav.count() > 0:
        autorun_nav.click()
    page.wait_for_selector("#view-auto-run", state="attached")
    return page


class TestAutoRunFormExists:
    """AutoRun フォームの基本要素が存在する。"""

    def test_url_input_exists(self, autorun_page: Page) -> None:
        """URL 入力フィールドが存在する。"""
        expect(autorun_page.locator("#autorun-url")).to_be_visible()

    def test_start_button_exists(self, autorun_page: Page) -> None:
        """開始ボタンが存在しクリック可能。"""
        btn = autorun_page.locator("#autorun-start-btn")
        expect(btn).to_be_visible()
        expect(btn).to_be_enabled()

    def test_depth_and_max_pages_inputs_exist(self, autorun_page: Page) -> None:
        """深さ・最大ページ数の入力フィールドが存在する。"""
        expect(autorun_page.locator("#autorun-depth")).to_be_visible()
        expect(autorun_page.locator("#autorun-max-pages")).to_be_visible()

    def test_invalid_url_shows_error(self, autorun_page: Page) -> None:
        """URL 未入力で開始ボタンをクリックするとエラーが表示される。"""
        autorun_page.locator("#autorun-url").fill("")
        autorun_page.locator("#autorun-start-btn").click()
        # エラーメッセージが表示される
        error_el = autorun_page.locator("#autorun-start-status")
        expect(error_el).to_be_visible()
        expect(error_el).not_to_have_text("")


class TestApprovalModalStructure:
    """承認モーダルの構造的完全性（INC-2026-001 防止チェック）。"""

    def _open_modal(self, page: Page) -> None:
        """承認モーダルを JavaScript で直接表示する（E2E テスト用）。"""
        # モーダルを強制表示（実際の awaiting_approval 状態を模擬）
        page.evaluate("""() => {
            const modal = document.getElementById('autorun-approval-modal');
            if (modal) modal.style.display = 'flex';
        }""")
        page.wait_for_selector("#autorun-approval-modal", state="visible")

    def test_modal_element_exists_in_dom(self, autorun_page: Page) -> None:
        """承認モーダルが DOM に存在する。"""
        expect(autorun_page.locator("#autorun-approval-modal")).to_be_attached()

    def test_modal_title_is_present(self, autorun_page: Page) -> None:
        """モーダルタイトルが存在し空でない。"""
        self._open_modal(autorun_page)
        title = autorun_page.locator("#arm-title")
        expect(title).to_be_visible()
        expect(title).not_to_have_text("")

    def test_filter_options_all_four_present(self, autorun_page: Page) -> None:
        """フィルターオプションが4種類全て存在する。"""
        self._open_modal(autorun_page)
        for value in ["all", "smoke", "transition", "form"]:
            radio = autorun_page.locator(f"input[name='arm-filter'][value='{value}']")
            expect(radio).to_be_attached()

    def test_filter_all_is_selected_by_default(self, autorun_page: Page) -> None:
        """デフォルトで「全テスト」が選択されている。"""
        self._open_modal(autorun_page)
        radio_all = autorun_page.locator("input[name='arm-filter'][value='all']")
        expect(radio_all).to_be_checked()

    def test_timeout_dropdown_exists_with_options(self, autorun_page: Page) -> None:
        """タイムアウトドロップダウンが存在し選択肢を持つ。"""
        self._open_modal(autorun_page)
        select = autorun_page.locator("#arm-timeout")
        expect(select).to_be_visible()
        options = autorun_page.locator("#arm-timeout option").all()
        assert len(options) >= 2, "タイムアウト選択肢が不足しています"

    def test_default_timeout_is_30_seconds(self, autorun_page: Page) -> None:
        """デフォルトのタイムアウトが 30 秒である。"""
        self._open_modal(autorun_page)
        value = autorun_page.locator("#arm-timeout").input_value()
        assert value == "30", f"デフォルトタイムアウトが 30 秒ではありません: {value}"

    def test_approve_button_exists_and_visible(self, autorun_page: Page) -> None:
        """「テスト実行を開始」ボタンが存在し視認可能。"""
        self._open_modal(autorun_page)
        btn = autorun_page.locator("#arm-approve-btn")
        expect(btn).to_be_visible()
        expect(btn).to_be_enabled()
        # ボタンのテキストが空でない
        expect(btn).not_to_have_text("")

    def test_close_button_exists(self, autorun_page: Page) -> None:
        """×ボタンが存在する。"""
        self._open_modal(autorun_page)
        expect(autorun_page.locator("#arm-close")).to_be_visible()

    def test_later_button_exists(self, autorun_page: Page) -> None:
        """「後で設定」ボタンが存在する。"""
        self._open_modal(autorun_page)
        expect(autorun_page.locator("#arm-later-btn")).to_be_visible()

    def test_close_button_hides_modal(self, autorun_page: Page) -> None:
        """×ボタンクリックでモーダルが閉じる。"""
        self._open_modal(autorun_page)
        autorun_page.locator("#arm-close").click()
        expect(autorun_page.locator("#autorun-approval-modal")).to_be_hidden()

    def test_later_button_hides_modal(self, autorun_page: Page) -> None:
        """「後で設定」ボタンでモーダルが閉じる。"""
        self._open_modal(autorun_page)
        autorun_page.locator("#arm-later-btn").click()
        expect(autorun_page.locator("#autorun-approval-modal")).to_be_hidden()

    def test_backdrop_click_hides_modal(self, autorun_page: Page) -> None:
        """モーダル外側クリックでモーダルが閉じる。"""
        self._open_modal(autorun_page)
        # モーダルオーバーレイの端をクリック
        modal = autorun_page.locator("#autorun-approval-modal")
        modal.click(position={"x": 10, "y": 10})
        expect(modal).to_be_hidden()

    def test_filter_radio_is_selectable(self, autorun_page: Page) -> None:
        """各フィルターラジオボタンが選択可能。"""
        self._open_modal(autorun_page)
        for value in ["smoke", "transition", "form", "all"]:
            autorun_page.locator(f"input[name='arm-filter'][value='{value}']").check()
            expect(
                autorun_page.locator(f"input[name='arm-filter'][value='{value}']")
            ).to_be_checked()

    def test_cases_detail_element_exists(self, autorun_page: Page) -> None:
        """テストケース一覧の details 要素が存在する。"""
        self._open_modal(autorun_page)
        expect(autorun_page.locator("#arm-cases-detail")).to_be_attached()

    def test_modal_screenshot_for_visual_review(self, autorun_page: Page) -> None:
        """モーダルのスクリーンショットを保存（目視確認用）。"""
        self._open_modal(autorun_page)
        autorun_page.screenshot(
            path="tests/e2e/screenshots/approval_modal.png",
            full_page=False,
        )
        assert True


class TestApprovalModalViaRoute:
    """page.route() で API をモックし、実際の JS フロー経由でモーダルを検証する。

    これは「JS 直接注入」ではなく、実際の autorunStart → polling →
    _autorunRender() → モーダル自動表示 という本番コードパスを通る。
    INC-2026-001 の本質的な改善: 実際のユーザーフローを E2E で保証する。
    """

    def _setup_mock_routes(self, page: Page) -> None:
        """AutoRun API をモックする。"""
        page.route(
            "**/api/autorun/start",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"ok": True, "job_id": "test-job-e2e"}),
            ),
        )
        page.route(
            "**/api/autorun/status**",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(_MOCK_STATUS_AWAITING),
            ),
        )
        page.route(
            "**/api/autorun/preview**",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(_MOCK_PREVIEW),
            ),
        )

    def test_modal_auto_shows_on_awaiting_approval(self, autorun_page: Page) -> None:
        """awaiting_approval ステータス到達時にモーダルが自動表示される。

        実際の JS ポーリング → _autorunRender() → _autorunPrepareAndShowApprovalModal()
        というコードパスを通して検証する。
        """
        self._setup_mock_routes(autorun_page)

        # URL を入力して開始ボタンをクリック（実際のユーザー操作）
        autorun_page.locator("#autorun-url").fill("https://example.com")
        autorun_page.locator("#autorun-start-btn").click()

        # ポーリングが awaiting_approval を受信し、モーダルが自動表示されるまで待機
        expect(autorun_page.locator("#autorun-approval-modal")).to_be_visible(timeout=10_000)

    def test_modal_populates_filter_counts_from_preview(self, autorun_page: Page) -> None:
        """モーダルが preview API からフィルターカウントを正しく表示する。"""
        self._setup_mock_routes(autorun_page)

        autorun_page.locator("#autorun-url").fill("https://example.com")
        autorun_page.locator("#autorun-start-btn").click()

        expect(autorun_page.locator("#autorun-approval-modal")).to_be_visible(timeout=10_000)

        # フィルターカウントが表示されている
        expect(autorun_page.locator("#arm-fc-all")).not_to_have_text("")
        expect(autorun_page.locator("#arm-fc-smoke")).not_to_have_text("")

    def test_approval_step_shows_waiting_state(self, autorun_page: Page) -> None:
        """awaiting_approval 時に左サイドバーの承認ステップが is-waiting スタイルになる。"""
        self._setup_mock_routes(autorun_page)

        autorun_page.locator("#autorun-url").fill("https://example.com")
        autorun_page.locator("#autorun-start-btn").click()

        # 承認ステップが is-waiting クラスを持つ
        step = autorun_page.locator("#ars-approval")
        expect(step).to_have_class("autorun-step-item is-waiting", timeout=10_000)


class TestApprovalModalVisibility:
    """承認モーダルの視認性チェック（INC-2026-001 で発覚した問題の防止）。"""

    def _open_modal(self, page: Page) -> None:
        page.evaluate("""() => {
            const modal = document.getElementById('autorun-approval-modal');
            if (modal) modal.style.display = 'flex';
        }""")
        page.wait_for_selector("#autorun-approval-modal", state="visible")

    def test_filter_labels_are_visible(self, autorun_page: Page) -> None:
        """フィルターオプションのラベルテキストが見える。"""
        self._open_modal(autorun_page)
        filter_opts = autorun_page.locator(".arm-filter-opt").all()
        assert len(filter_opts) == 4, f"フィルターオプションが4件ではありません: {len(filter_opts)}"
        for opt in filter_opts:
            expect(opt).to_be_visible()

    def test_approve_button_is_not_obscured(self, autorun_page: Page) -> None:
        """承認ボタンが他の要素に隠れていない（クリック可能な位置にある）。"""
        self._open_modal(autorun_page)
        btn = autorun_page.locator("#arm-approve-btn")
        expect(btn).to_be_in_viewport()

    def test_modal_does_not_overflow_viewport(self, autorun_page: Page) -> None:
        """モーダルがビューポートからはみ出していない。"""
        autorun_page.set_viewport_size({"width": 1280, "height": 800})
        self._open_modal(autorun_page)
        modal_inner = autorun_page.locator("#autorun-approval-modal > div")
        box = modal_inner.bounding_box()
        assert box is not None
        assert box["y"] >= 0, "モーダルが上端からはみ出しています"
        assert box["y"] + box["height"] <= 800 + 10, "モーダルが下端からはみ出しています"

    def test_timeout_dropdown_not_obscured(self, autorun_page: Page) -> None:
        """タイムアウトドロップダウンが視認可能な位置にある。"""
        self._open_modal(autorun_page)
        expect(autorun_page.locator("#arm-timeout")).to_be_in_viewport()
