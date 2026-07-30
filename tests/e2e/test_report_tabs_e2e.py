"""実行結果レポート画面 新タブ基盤（6タブ・永続パネル・ディープリンク）の E2E テスト。

対象:
    - 6タブ構成（overview / screens / test-design / flow / runs / history）
    - 複合タブのサブタブ切替（test-design: matrix/summary/detail 等）
    - 永続パネルによる状態保持（タブ切替でマトリクスの検索条件が消えない）
    - ディープリンク #report/<domain>/<tab>/<sub> と旧8タブ名の互換リダイレクト

実行方法:
    make verify-ui
"""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")
FIXTURE_DOMAIN = "e2e-report-tabs.example.com"
ROOT = Path(__file__).parent.parent.parent
FIXTURE_DIR = ROOT / "output" / FIXTURE_DOMAIN

FIXTURE_REPORT = {
    "meta": {
        "target_url": f"https://{FIXTURE_DOMAIN}/",
        "crawled_at": "2026-07-01 12:00",
        "crawl_depth": 1,
        "max_pages": 5,
        "screen_count": 2,
    },
    "screens": [
        {
            "page_id": "P001",
            "title": "トップ",
            "url": f"https://{FIXTURE_DOMAIN}/",
            "is_canonical": True,
            "headings": ["ようこそ"],
            "buttons": ["ログイン"],
            "forms": [],
            "transitions": {"to": ["P002"], "from": []},
        },
        {
            "page_id": "P002",
            "title": "お問い合わせ",
            "url": f"https://{FIXTURE_DOMAIN}/contact",
            "is_canonical": True,
            "headings": ["お問い合わせ"],
            "buttons": ["送信"],
            "forms": [
                {
                    "action": "/contact",
                    "method": "post",
                    "fields": [
                        {
                            "name": "email",
                            "field_type": "email",
                            "required": True,
                            "maxlength": "100",
                            "locators": ["#email"],
                            "test_conditions": ["必須入力", "メール形式"],
                        },
                        {
                            "name": "message",
                            "field_type": "textarea",
                            "required": False,
                            "locators": ["#message"],
                            "test_conditions": ["最大長"],
                        },
                    ],
                }
            ],
            "transitions": {"to": [], "from": ["P001"]},
        },
    ],
}


@pytest.fixture(scope="module", autouse=True)
def report_fixture() -> Generator[None, None, None]:
    """最小構成の report.json を output/ に配置し、テスト後に削除する。"""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / "report.json").write_text(
        json.dumps(FIXTURE_REPORT, ensure_ascii=False), encoding="utf-8"
    )
    yield
    shutil.rmtree(FIXTURE_DIR, ignore_errors=True)


def _open_report(page: Page, suffix: str = "") -> None:
    page.goto(f"{BASE_URL}/#report/{FIXTURE_DOMAIN}{suffix}")
    expect(page.locator("#result-panel")).to_be_visible()
    expect(page.locator("#r-domain")).to_have_text(FIXTURE_DOMAIN)


class TestTabStructure:
    """6タブ構成とパネルホストの検証。"""

    def test_no_javascript_errors_on_report(self, page: Page) -> None:
        js_errors: list[str] = []
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        _open_report(page)
        page.wait_for_load_state("networkidle")
        assert js_errors == [], f"JavaScript エラー: {js_errors}"


class TestSubTabs:
    """複合タブのサブタブ切替の検証。"""

    # テスト設計タブのサブタブ（templates/partials/view-generate.html の並び順）
    DESIGN_SUBTABS = (
        ("by-screen", "画面別設計"),
        ("matrix", "条件マトリクス"),
        ("summary", "技法サマリー"),
        ("detail", "技法詳細"),
        ("mbt", "技法別設計"),
    )

    def test_all_design_subtabs_visible_at_900px(self, page: Page) -> None:
        """R3-14: 技法タブの視認性。幅900pxでも最後（技法別設計 MBT）まで
        overflow-x スクロールの陰に隠れず、折返し表示で常に視認できること。

        .result-subtabs は flex-wrap:wrap のため、5件になっても横にはみ出さず
        2行へ折り返す。順序は画面別設計 → 条件マトリクス → 技法サマリー →
        技法詳細 → 技法別設計（MBT）。"""
        page.set_viewport_size({"width": 900, "height": 700})
        _open_report(page)
        page.locator('.result-tab[data-tab="test-design"]').click()
        tabs = page.locator("#rp-test-design .result-subtabs .result-subtab")
        expect(tabs).to_have_count(len(self.DESIGN_SUBTABS))
        for i, (sub, label) in enumerate(self.DESIGN_SUBTABS):
            tab = tabs.nth(i)
            expect(tab).to_have_attribute("data-sub", sub)
            expect(tab).to_have_text(re.compile(label))
            box = tab.bounding_box()
            assert box is not None, f"サブタブ{i}({sub})のbounding_boxが取得できない"
            assert (
                box["x"] + box["width"] <= 900
            ), f"サブタブ{i}({sub})が画面外にはみ出している: {box}"


class TestRunsTab:
    """テスト実行タブ（AutoRun 結果の一元表示）。"""

    def _write_playwright_report(self, payload: dict) -> Path:
        qa_dir = FIXTURE_DIR / "qa_process"
        qa_dir.mkdir(parents=True, exist_ok=True)
        path = qa_dir / "playwright_report.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return qa_dir


class TestStatePreservation:
    """永続パネルによる状態保持の検証。"""


class TestDeepLink:
    """ディープリンクと旧タブ名互換の検証。"""


class TestExportDropdownKeyboard:
    """エクスポートのドロップダウンをキーボードだけで畳めること。"""

    def test_export_dropdown_closes_on_escape(self, page: Page) -> None:
        """再発防止: 外側クリックでしか閉じられず、キーボード操作では
        開いたドロップダウンを畳めないまま先へ進めなかった。
        """
        _open_report(page)
        button = page.locator("#export-dropdown-btn")
        expect(button).to_be_visible()
        button.click()
        expect(page.locator("#export-dropdown")).to_have_class(re.compile(r"\bis-open\b"))
        expect(button).to_have_attribute("aria-expanded", "true")

        page.keyboard.press("Escape")
        expect(page.locator("#export-dropdown")).not_to_have_class(re.compile(r"\bis-open\b"))
        expect(button).to_have_attribute("aria-expanded", "false")
        expect(button).to_be_focused()
