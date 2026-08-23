"""システムテスト L3: メンバー利用ビュー
（docs/system_test_cases.csv ST-018〜ST-021, ST-029, ST-030）。

実行方法:
    make e2e-system
"""

from __future__ import annotations

import re
from dataclasses import replace

from playwright.sync_api import Page, expect
from tests.e2e.system.helpers import (
    MEMBER,
    PW_CHANGE_MEMBER,
    login,
    open_docs_system,
    switch_view,
    switch_view_by_script,
)


class TestStMemberViews:
    """観点・QA品質・トレーサビリティ・フィードバック・個人設定・使用量。"""

    def test_st018_viewpoints_view_renders(self, page: Page, system_server: str) -> None:
        """ST-018: 観点ビューが表示される（編集保存は既存 E2E の範囲）。"""
        open_docs_system(page, system_server, MEMBER)
        switch_view(page, "viewpoints")

    def test_st019_qa_quality_view_renders(self, page: Page, system_server: str) -> None:
        """ST-019: QA 品質ビューが表示され、対象選択 UI が存在する。"""
        open_docs_system(page, system_server, MEMBER)
        switch_view(page, "qa-quality")
        expect(page.locator("#qa-quality-domain-select")).to_be_attached()

    def test_st020_traceability_page_loads(self, page: Page, system_server: str) -> None:
        """ST-020: トレーサビリティページが JS エラーなく表示される。"""
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        login(page, system_server, MEMBER)
        # 現行実装のページ URL は /traceability/view（web/routes/traceability.py:94）。
        # 同ファイルの定義は /traceability/matrix（API・38 行目）と /traceability/view のみで、
        # /traceability というパスは存在しない（＝404 はテストの陳腐化）。
        resp = page.goto(f"{system_server}/traceability/view", wait_until="domcontentloaded")
        assert resp is not None and resp.ok, f"応答: {resp.status if resp else 'なし'}"
        assert not errors, f"JS エラー: {errors}"

    def test_st021_feedback_submission(self, page: Page, system_server: str) -> None:
        """ST-021: フィードバックを送信すると状態表示が更新される。"""
        open_docs_system(page, system_server, MEMBER)
        switch_view_by_script(page, "feedback")
        page.locator("#feedback-message").fill("E2E システムテストからの動作確認です。")
        page.locator("#feedback-submit-btn").click()
        expect(page.locator("#feedback-status")).to_contain_text(re.compile(r"\S"))

    def test_st029_change_own_password(self, page: Page, system_server: str) -> None:
        """ST-029: 個人設定で自分のパスワードを変更し、新パスワードで再ログインできる。"""
        new_password = "st-member2-updated-9"
        login(page, system_server, PW_CHANGE_MEMBER)
        # システム選択画面の個人設定導線は .sysselect-account 内のアンカー
        # <a class="sysselect-text-btn" href="/account">（templates/system-select.html:26）。
        # .sysselect-account 自体はコンテナ div（同 21 行目）で、クリックしても遷移しない。
        page.locator('.sysselect-account a[href="/account"]').click()
        expect(page.locator("#view-account")).to_be_visible()
        page.locator("#pw-current").fill(PW_CHANGE_MEMBER.password)
        page.locator("#pw-new").fill(new_password)
        page.locator('#password-form button[type="submit"]').click()
        expect(page.locator("#password-status")).to_contain_text(re.compile(r"\S"))

        # 新パスワードで実際にログインし直せることまで確認する
        page.request.post(f"{system_server}/auth/logout")
        login(page, system_server, replace(PW_CHANGE_MEMBER, password=new_password))

    def test_st030_usage_view_renders(self, page: Page, system_server: str) -> None:
        """ST-030: 使用量ビューが表示され、集計項目が存在する。"""
        # 使用量ビューはアプリシェル（templates/index.html の include 一覧）に含まれず、
        # /usage が partials/view-usage.html を単体でレンダリングする
        # （web/routes/usage.py:27-30）。よって switchView('usage') では到達できない。
        login(page, system_server, MEMBER)
        resp = page.goto(f"{system_server}/usage", wait_until="domcontentloaded")
        assert resp is not None and resp.ok, f"応答: {resp.status if resp else 'なし'}"
        expect(page.locator("#view-usage")).to_be_visible()
        expect(page.locator("#usage-crawls")).to_be_attached()
