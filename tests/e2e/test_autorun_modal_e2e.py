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
import os

import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")

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
    """AutoRun ビューを開いた状態のページを返す。

    AutoRun は独立したシステムなので、`/` から辿るのではなく直接開く。
    `/` は「ドキュメント作成」系と判定され、AutoRun のナビ項目は
    system-scope.js によって非表示になるためクリックできない。
    """
    page.goto(f"{BASE_URL}/auto-run")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#view-auto-run", state="attached")
    return page


class TestAutoRunFormExists:
    """AutoRun フォームの基本要素が存在する。"""







class TestApprovalModalStructure:
    """承認モーダルの構造的完全性（INC-2026-001 防止チェック）。"""

    def _open_modal(self, page: Page) -> None:
        """承認モーダルを JavaScript で直接表示する（E2E テスト用）。"""
        # モーダルを強制表示（実際の awaiting_approval 状態を模擬）
        page.evaluate(
            """() => {
            const modal = document.getElementById('autorun-approval-modal');
            if (modal) modal.style.display = 'flex';
        }"""
        )
        page.wait_for_selector("#autorun-approval-modal", state="visible")

















class TestRunningTestsProgressLabel:
    """テスト実行中の「n/188件目」進捗表示（ドッグフーディング指摘: 188件承認・
    実行しても進捗が全く見えない、への対応）。"""




class TestAutoRunCancelButtonStyle:
    """R2-05/S1-8: 中断ボタンをスタイリッシュに。.btn-danger-outline の
    width:100% で全幅の目立つ赤帯になっていた不具合の再発防止。"""



class TestAutoRunLivePreview:
    """R2-07/R2-23: AutoRunのテスト実行中にライブプレビュー画面が見えないという
    指摘への対応。running_tests ステータスの間だけプレビュー枠を表示する。"""





class TestOutputCategorization:
    """成果物一覧のSDLC分類（R2-22: 計画/分析/設計/実装/実行/レポート）。"""



class TestCaseDetailExpand:
    """テストケース一覧の行クリックで手順・期待結果の全文を確認できる
    （ドッグフーディング指摘: テストケースの詳細が見えない、への対応）。"""

    _CANDIDATE = {
        "id": "PW-001",
        "title": "ログインフォーム送信",
        "automation_status": "auto",
        "trace_id": "P002",
        "steps": ["page.goto('https://example.com/login')", "page.click('#submit')"],
        "expected": "ダッシュボード画面に遷移し、ようこそメッセージが表示される。" * 2,
    }

    def _render(self, page: Page) -> None:
        page.evaluate(
            """(candidate) => {
                document.getElementById('autorun-preview-panel').style.display = 'flex';
                _autorunRenderPreview({
                    summary: {total: 1, by_status: {auto: 1}, by_title: {}},
                    candidates: [candidate],
                    spec_content: '',
                });
            }""",
            self._CANDIDATE,
        )



    def test_detail_row_toggles_via_keyboard(self, autorun_page: Page) -> None:
        self._render(autorun_page)
        row = autorun_page.locator(".autorun-case-row").first
        detail_row = autorun_page.locator('[data-case-detail="0"]')
        row.focus()
        row.press("Enter")
        expect(detail_row).to_be_visible()


class TestDeveloperLogToggle:
    """クロールCLIの生ログは既定非表示・「開発者向け詳細を表示」で見える
    （生ログがそのまま表示され読みにくい、というドッグフーディング指摘への
    対応）。"""

    def _render_log(self, page: Page) -> None:
        page.evaluate(
            """() => {
                document.getElementById('ar-log-section').style.display = '';
                _autoRunLogLines = [
                    '[10:00:00] クロール開始: https://example.com/ (depth=2, max=30)',
                    '[10:00:01] [cli] Crawling https://example.com/...',
                    '[10:00:05] クロール完了: example.com',
                ];
                _autorunRenderLog();
            }"""
        )




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





class TestApprovalModalVisibility:
    """承認モーダルの視認性チェック（INC-2026-001 で発覚した問題の防止）。"""

    def _open_modal(self, page: Page) -> None:
        page.evaluate(
            """() => {
            const modal = document.getElementById('autorun-approval-modal');
            if (modal) modal.style.display = 'flex';
        }"""
        )
        page.wait_for_selector("#autorun-approval-modal", state="visible")


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


class TestLiveTestResults:
    """R3-01: テスト実行中に per-test の実況（OK/NG）がリアルタイムで流れる。"""




class TestApprovalModalDeviceSelection:
    """R3-02: 承認モーダルでPC/モバイル実行を選択できる。"""

    def _open_modal(self, page: Page) -> None:
        page.evaluate(
            """() => {
            const modal = document.getElementById('autorun-approval-modal');
            if (modal) modal.style.display = 'flex';
        }"""
        )
        page.wait_for_selector("#autorun-approval-modal", state="visible")





class TestLoginModalVsShortcutHelp:
    """R3-13: ショートカットヘルプ表示中にログイン要求が来ても、入力・Esc閉じが
    全て可能であること（ヘルプのz-index競合・不可視要素へのfocus・Esc分裂の
    再発防止）。"""

    def _show_login_modal(self, page: Page) -> None:
        page.evaluate(
            """() => _autorunShowLoginModal({
                message: 'ログインが必要です。',
                login_url: 'https://example.com/login',
            })"""
        )



    def test_escape_closes_login_modal(self, autorun_page: Page) -> None:
        """Escキーでログインモーダルが閉じる（ヘルプだけが閉じて終わらない）。"""
        self._show_login_modal(autorun_page)
        expect(autorun_page.locator("#autorun-login-modal")).to_be_visible()
        autorun_page.keyboard.press("Escape")
        expect(autorun_page.locator("#autorun-login-modal")).to_be_hidden()

    def test_login_modal_z_index_above_help_overlay(self, autorun_page: Page) -> None:
        """ログインモーダルのz-indexがヘルプオーバーレイ(2100)より前面である回帰確認。"""
        self._show_login_modal(autorun_page)
        z_index = autorun_page.evaluate(
            """() => getComputedStyle(document.getElementById('autorun-login-modal')).zIndex"""
        )
        assert int(z_index) > 2100, f"ログインモーダルのz-indexがヘルプ以下: {z_index}"
