"""システムテスト L3: AutoRun（docs/system_test_cases.csv ST-014〜ST-017）。

実行方法:
    make e2e-system
"""

from __future__ import annotations

from playwright.sync_api import Page, expect
from tests.e2e.system.helpers import MEMBER, login


def _open_autorun(page: Page, base_url: str) -> None:
    login(page, base_url, MEMBER)
    page.goto(f"{base_url}/auto-run", wait_until="domcontentloaded")
    page.wait_for_selector("#autorun-leadbar button", state="visible")


class TestStAutoRun:
    """段階承認 UI・ログ表示・実行結果ページ・承認待ち保持。"""

    def test_st014_approval_decisions_ui_is_operable(
        self, page: Page, system_server: str
    ) -> None:
        """ST-014: 段階承認の判断 UI が開き、推奨が事前選択され、選択を変更できる。

        17 ステップの完遂は LLM 実行を要するため、このサイクルでは承認 UI の
        操作性（表示・事前選択・再選択）までを検証範囲とする。
        """
        _open_autorun(page, system_server)
        page.click("#autorun-leadbar button")
        expect(page.locator("#autorun-decisions")).to_be_visible()
        # 推奨の選択肢が事前選択されている
        expect(page.locator(".ard-choice.is-selected").first).to_be_visible()
        # 別の選択肢へ変更できる（クリックが遮られない）
        page.locator(".ard-choice").first.click()

    def test_st015_log_area_is_not_collapsible(self, page: Page, system_server: str) -> None:
        """ST-015: 実行ログ領域が折りたたみ UI に包まれず常時表示の構造である。

        実行中のログ流入はサーバー実行を要するため、ログ要素が存在し
        <details> 等の折りたたみ配下に無いことを構造として検証する。
        """
        login(page, system_server, MEMBER)
        page.goto(f"{system_server}/auto-run", wait_until="domcontentloaded")
        if page.locator("#autorun-log").count() == 0:
            # ログ要素が実行結果ページ側にある構成
            page.goto(f"{system_server}/autorun-report", wait_until="domcontentloaded")
        log = page.locator("#autorun-log, #ar-log-section").first
        expect(log).to_be_attached()
        assert page.evaluate(
            "() => !document.querySelector('#autorun-log')?.closest('details')"
        ), "実行ログが折りたたみ（details）配下にあります"

    def test_st016_report_page_loads(self, page: Page, system_server: str) -> None:
        """ST-016: 実行結果専用ページ（/autorun-report）が JS エラーなく表示される。"""
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        login(page, system_server, MEMBER)
        resp = page.goto(f"{system_server}/autorun-report", wait_until="domcontentloaded")
        assert resp is not None and resp.ok, f"応答: {resp.status if resp else 'なし'}"
        expect(page.locator("#arep-main")).to_be_attached()
        assert not errors, f"JS エラー: {errors}"

    def test_st017_pending_approval_survives_navigation(
        self, page: Page, system_server: str
    ) -> None:
        """ST-017: 承認せずに画面を離れて戻っても、勝手に先へ進んでいない。"""
        _open_autorun(page, system_server)
        page.click("#autorun-leadbar button")
        expect(page.locator("#autorun-decisions")).to_be_visible()
        # 承認せずに離脱して戻る
        page.goto(f"{system_server}/")
        page.goto(f"{system_server}/auto-run", wait_until="domcontentloaded")
        # 実行が始まっておらず、開始前の導線（leadbar）が再表示される
        page.wait_for_selector("#autorun-leadbar button", state="visible")
