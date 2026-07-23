from __future__ import annotations

import os

from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")


def _open_viewpoints(page: Page) -> None:
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    page.locator('.app-nav-item[data-view="viewpoints"]').click()
    expect(page.locator("#view-viewpoints")).to_be_visible()
    page.wait_for_selector(".vp-set-row", state="attached")
    page.wait_for_selector("#vp-table-body tr[data-vp-item-id]", state="attached")


def test_viewpoint_dialog_focus_trap_escape_and_discard(page: Page) -> None:
    _open_viewpoints(page)
    first_row = page.locator("#vp-table-body tr[data-vp-item-id]").first
    item_id = first_row.get_attribute("data-vp-item-id")
    first_row.click()
    expect(page.locator("#vp-editor-overlay")).to_be_visible()

    page.locator("#vp-save-item").focus()
    page.keyboard.press("Tab")
    expect(page.locator("#vp-editor-close")).to_be_focused()

    page.locator("#vp-item-purpose").fill("破棄確認用の未保存変更")
    page.keyboard.press("Escape")
    expect(page.locator("#confirm-overlay")).to_be_visible()
    expect(page.locator("#confirm-cancel-btn")).to_have_text("編集を続ける")
    expect(page.locator("#confirm-cancel-btn")).to_be_focused()
    page.locator("#confirm-cancel-btn").click()
    expect(page.locator("#vp-editor-overlay")).to_be_visible()

    page.locator("#vp-editor-close").click()
    page.locator("#confirm-ok-btn").click()
    expect(page.locator("#vp-editor-overlay")).to_be_hidden()
    expect(page.locator(f'[data-vp-item-id="{item_id}"]')).to_be_focused()
