"""AutoRun 実行条件ダイアログ E2E テスト（L3 システムテスト）。

目的:
    段階承認を廃止し、実行条件の確定に集約した導線が壊れていないことを守る。

    このセッションで、承認が段階へ反映されず実行に進めない致命バグが発生した。
    原因は「確定する」が承認 API を呼んでいなかったことで、E2E が無かったため
    誰も気づけなかった。同種の再発を検知するためのテスト。

検証すること:
    - 「実行する」で実行条件ダイアログが開く
    - 推奨が最初から選択済みで、何も触らずに確定できる
    - 推奨以外を選ぶと、その選択が API へ送られる
    - 自由入力が必要な選択肢では入力欄が出る
    - 8段階のサイドメニューが表示されない（順番に承認させないため）

実行方法:
    make verify-ui
"""

from __future__ import annotations

import json
import os

import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")

_DOMAIN = "decisions-e2e.example.com"

_MOCK_DECISIONS = {
    "domain": _DOMAIN,
    "decisions": [
        {
            "decision_id": "auth_scope",
            "source_item_id": "plan-assume-auth",
            "question": "ログインが必要な画面もテストしますか？",
            "context": "ロール別の期待結果が指定されていません。",
            "recommended": "public_only",
            "choices": [
                {
                    "key": "public_only",
                    "label": "未ログインの範囲だけ",
                    "detail": "認証情報が未登録のため、到達できる画面だけを対象にします。",
                    "needs_text": False,
                },
                {
                    "key": "authenticated",
                    "label": "ログインしてテスト",
                    "detail": "認証情報の登録が必要です。",
                    "needs_text": False,
                },
            ],
        },
        {
            "decision_id": "exit_criteria",
            "source_item_id": "plan-assume-exit",
            "question": "合否はどう判定しますか？",
            "context": "リリース判定基準の指定がありません。",
            "recommended": "severity",
            "choices": [
                {
                    "key": "severity",
                    "label": "重大度で整理して人が判断",
                    "detail": "高・中・低に分けて提示します。",
                    "needs_text": False,
                },
                {
                    "key": "custom",
                    "label": "基準を指定する",
                    "detail": "例: 高リスクが0件なら合格",
                    "needs_text": True,
                },
            ],
        },
    ],
    "facts": [
        {
            "title": "基準の確立",
            "detail": "前回スナップショットが無いため比較の基準を作る回になります",
        }
    ],
}

_MOCK_STAGES = {
    "domain": _DOMAIN,
    "current_stage_id": "test_objective",
    "all_approved": False,
    "approved_stage_count": 0,
    "stage_total": 1,
    "is_rerun": False,
    "audit": [],
    "stages": [
        {
            "stage_id": "test_objective",
            "step_no": 1,
            "name": "テスト目的",
            "purpose": "テストの目的を定める",
            "note": "",
            "status": "generated",
            "can_approve": True,
            "requires_item_approval": False,
            "items": [
                {
                    "item_id": "obj-defect",
                    "title": "欠陥の摘出",
                    "detail": "故障を誘発して欠陥を見つける",
                    "approved": False,
                    "assumed": False,
                    "source": "observed",
                }
            ],
        }
    ],
}


@pytest.fixture
def decisions_page(page: Page) -> Page:
    """実行条件ダイアログを開ける状態のページを返す。

    段階 API と実行条件 API をモックし、UI の導線だけを検証する。
    """
    captured: list[dict] = []
    page.decisions_payloads = captured  # type: ignore[attr-defined]

    page.route(
        "**/api/autorun/stages?**",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(_MOCK_STAGES)
        ),
    )
    page.route(
        "**/api/autorun/decisions?**",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(_MOCK_DECISIONS)
        ),
    )

    def _capture(route) -> None:
        captured.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({**_MOCK_STAGES, "released": True, "detail": "ok"}),
        )

    page.route("**/api/autorun/decisions", _capture)

    page.goto(f"{BASE_URL}/auto-run", wait_until="domcontentloaded")
    page.wait_for_timeout(400)
    page.evaluate(f"() => window.autorunStages.load('{_DOMAIN}', {{open: true}})")
    page.wait_for_timeout(700)
    return page


class TestDecisionsDialog:
    """実行条件ダイアログの導線。"""

    def test_run_button_opens_dialog(self, decisions_page: Page) -> None:
        """「実行する」で実行条件ダイアログが開く。"""
        decisions_page.click("#autorun-leadbar button")
        expect(decisions_page.locator("#autorun-decisions")).to_be_visible()
        expect(decisions_page.locator(".ard-question").first).to_contain_text(
            "ログインが必要な画面"
        )

    def test_recommended_is_preselected(self, decisions_page: Page) -> None:
        """推奨が最初から選択済みで、何も触らずに確定できる。"""
        decisions_page.click("#autorun-leadbar button")
        selected = decisions_page.locator(".ard-choice.is-selected")
        expect(selected).to_have_count(len(_MOCK_DECISIONS["decisions"]))
        expect(selected.first).to_contain_text("未ログインの範囲だけ")
        # 推奨バッジが選択済みの側に付いている
        expect(selected.first.locator(".ard-tag")).to_have_text("推奨")

    def test_submitting_without_touching_sends_recommendations(self, decisions_page: Page) -> None:
        """何も触らずに確定すると、推奨がそのまま送られる。"""
        decisions_page.click("#autorun-leadbar button")
        decisions_page.click("#autorun-decisions-go")
        decisions_page.wait_for_timeout(600)

        payloads = decisions_page.decisions_payloads  # type: ignore[attr-defined]
        assert payloads, "確定 API が呼ばれていません（押しても何も起きない状態）"
        answers = payloads[-1]["answers"]
        assert answers["auth_scope"]["choice"] == "public_only"
        assert answers["exit_criteria"]["choice"] == "severity"

    def test_non_recommended_choice_is_sent(self, decisions_page: Page) -> None:
        """推奨以外を選ぶと、その選択が送られる。"""
        decisions_page.click("#autorun-leadbar button")
        decisions_page.locator(".ard-choice", has_text="ログインしてテスト").click()
        decisions_page.click("#autorun-decisions-go")
        decisions_page.wait_for_timeout(600)

        payloads = decisions_page.decisions_payloads  # type: ignore[attr-defined]
        assert payloads[-1]["answers"]["auth_scope"]["choice"] == "authenticated"

    def test_free_text_appears_for_custom_choice(self, decisions_page: Page) -> None:
        """自由入力が必要な選択肢を選ぶと、入力欄が出る。"""
        decisions_page.click("#autorun-leadbar button")
        before = decisions_page.locator(".ard-text").count()
        decisions_page.locator(".ard-choice", has_text="基準を指定する").click()
        decisions_page.wait_for_timeout(300)
        assert decisions_page.locator(".ard-text").count() > before

    def test_facts_are_shown_not_asked(self, decisions_page: Page) -> None:
        """選択の余地がない前提は、質問ではなく事実として出る。"""
        decisions_page.click("#autorun-leadbar button")
        expect(decisions_page.locator(".ard-fact")).to_contain_text("基準の確立")


class TestStageListRemoved:
    """段階リストを出さないこと（順番に承認させる導線を作らない）。"""

    def test_stage_nav_is_hidden(self, decisions_page: Page) -> None:
        """8段階のサイドメニューが表示されない。"""
        expect(decisions_page.locator("#autorun-phase-nav")).to_be_hidden()
        expect(decisions_page.locator("#autorun-phase-group")).to_be_hidden()

    def test_no_per_stage_approve_button(self, decisions_page: Page) -> None:
        """段階ごとの「承認して次へ」がパネルに残っていない。"""
        panel = decisions_page.locator("#autorun-stage-panel")
        assert panel.get_by_role("button", name="承認して次へ").count() == 0
