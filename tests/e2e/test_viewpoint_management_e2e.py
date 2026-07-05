from __future__ import annotations

import json
import uuid

from playwright.sync_api import Page, Route, expect

BASE_URL = "http://127.0.0.1:8765"


def _open_viewpoints(page: Page) -> None:
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    page.locator('.app-nav-item[data-view="viewpoints"]').click()
    expect(page.locator("#view-viewpoints")).to_be_visible()
    page.wait_for_selector(".vp-set-row", state="attached")
    page.wait_for_selector("#vp-table-body tr[data-vp-item-id]", state="attached")


def test_viewpoint_initial_state_edit_save_and_focus_restore(page: Page) -> None:
    _open_viewpoints(page)
    expect(page.locator("#vp-editor-overlay")).to_be_hidden()
    expect(page.locator("#vp-feedback")).to_be_hidden()
    expect(page.locator("#vp-bulkbar")).to_be_hidden()

    first_row = page.locator("#vp-table-body tr[data-vp-item-id]").first
    item_id = first_row.get_attribute("data-vp-item-id")
    first_row.press("Enter")
    expect(page.locator("#vp-editor-overlay")).to_be_visible()
    expect(page.locator("#vp-editor-title")).to_be_focused()
    expect(page.locator("#vp-item-name")).not_to_have_value("")

    current = page.locator("#vp-item-purpose").input_value()
    page.locator("#vp-item-purpose").fill(current + " E2E確認")
    assert page.evaluate("vpCollectItem().automation") in {"automated", "semi_automated", "manual"}
    expect(page.locator("#vp-editor-state")).to_have_text("未保存")
    page.locator("#vp-save-item").focus()
    page.keyboard.press("Enter")
    expect(page.locator("#vp-editor-overlay")).to_be_hidden()
    expect(page.locator("#vp-feedback")).to_contain_text("下書きを保存しました")
    expect(page.locator(f'[data-vp-item-id="{item_id}"]')).to_be_focused()


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


def test_viewpoint_validation_and_conflict_recovery(page: Page) -> None:
    _open_viewpoints(page)
    page.locator("#vp-table-body tr[data-vp-item-id]").first.click()
    original_name = page.locator("#vp-item-name").input_value()
    page.locator("#vp-item-name").fill("")
    page.locator("#vp-save-item").click()
    expect(page.locator("#vp-item-name-error")).to_contain_text("名称を入力")
    expect(page.locator("#vp-item-name")).to_be_focused()

    page.locator("#vp-item-name").fill(original_name)
    page.locator("#vp-item-purpose").fill("競合回復E2E")
    current = page.evaluate("vpState.selectedItem")
    intercepted = {"done": False}

    def conflict_once(route: Route) -> None:
        if intercepted["done"]:
            route.continue_()
            return
        intercepted["done"] = True
        route.fulfill(
            status=409,
            content_type="application/json",
            body=json.dumps(
                {
                    "error": "他の操作で更新されています。",
                    "details": {
                        "current": current,
                        "diff": {
                            "purpose": {
                                "submitted": "競合回復E2E",
                                "current": "サーバー版",
                            }
                        },
                    },
                },
                ensure_ascii=False,
            ),
        )

    page.route("**/api/viewpoint-items/*", conflict_once)
    page.locator("#vp-save-item").click()
    expect(page.locator("#vp-conflict-panel")).to_be_visible()
    expect(page.locator("#vp-editor-state")).to_have_text("競合")
    page.locator("#vp-conflict-reapply").click()
    expect(page.locator("#vp-editor-overlay")).to_be_hidden()
    expect(page.locator("#vp-feedback")).to_contain_text("下書きを保存しました")
    page.unroute("**/api/viewpoint-items/*", conflict_once)


def test_published_item_is_readonly_and_can_create_next_draft(page: Page) -> None:
    _open_viewpoints(page)
    page.locator('[data-vp-tab="published"]').click()
    page.wait_for_selector("#vp-table-body tr[data-vp-item-id]", state="attached")
    page.locator("#vp-table-body tr[data-vp-item-id]").first.click()
    expect(page.locator("#vp-item-name")).to_be_disabled()
    expect(page.locator("#vp-save-item")).to_be_hidden()
    expect(page.locator("#vp-create-next-draft")).to_be_visible()
    page.locator("#vp-create-next-draft").click()
    expect(page.locator('[data-vp-tab="draft"]')).to_have_attribute("aria-selected", "true")
    expect(page.locator("#vp-editor-overlay")).to_be_visible()
    expect(page.locator("#vp-item-name")).to_be_enabled()
    expect(page.locator("#vp-save-item")).to_be_visible()


def test_viewpoint_create_delete_and_undo(page: Page) -> None:
    _open_viewpoints(page)
    name = f"E2E削除対象-{uuid.uuid4().hex[:8]}"
    page.locator("#vp-add-viewpoint").click()
    expect(page.locator("#vp-item-name")).to_be_focused()
    page.locator("#vp-item-name").fill(name)
    page.locator("#vp-item-category").fill("E2E")
    page.locator("#vp-save-item").focus()
    page.keyboard.press("Enter")
    expect(page.locator("#vp-editor-overlay")).to_be_hidden()

    row = page.locator("#vp-table-body tr", has_text=name)
    expect(row).to_be_visible()
    row.press("Enter")
    page.locator("#vp-delete-item").focus()
    page.keyboard.press("Enter")
    expect(page.locator("#confirm-overlay")).to_be_visible()
    page.locator("#confirm-ok-btn").click()
    expect(page.locator("#vp-editor-overlay")).to_be_hidden()
    expect(page.locator("#vp-feedback")).to_contain_text("観点を削除しました")

    page.locator("#vp-feedback-action").focus()
    page.keyboard.press("Enter")
    expect(page.locator("#vp-feedback")).to_contain_text("削除を取り消しました")
    expect(page.locator("#vp-table-body tr", has_text=name)).to_be_visible()


def test_viewpoint_desktop_modal_screenshots(page: Page) -> None:
    for width, height, name in [
        (1920, 1080, "viewpoints-modal-1920x1080.png"),
        (1366, 768, "viewpoints-modal-1366x768.png"),
        (1024, 768, "viewpoints-modal-1024x768.png"),
    ]:
        page.set_viewport_size({"width": width, "height": height})
        _open_viewpoints(page)
        page.locator("#vp-table-body tr[data-vp-item-id]").first.click()
        expect(page.locator("#vp-editor-overlay")).to_be_visible()
        page.screenshot(path=f"tests/e2e/screenshots/{name}", full_page=False)
        overflow = page.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        assert not overflow
        page.locator("#vp-editor-close").click()


def test_viewpoint_template_menu_lists_real_presets_with_items(page: Page) -> None:
    """R1-18: ISTQB/ISO25010/非機能要求グレード2018/PMBOKプリセットが実アイテム入りで
    提供されること（従来は空フォルダのみだった）を確認する。"""
    _open_viewpoints(page)
    page.locator("#vp-tree-template-btn").click()
    menu = page.locator("#vp-template-menu")
    expect(menu).to_be_visible()
    items = menu.locator(".vp-template-item")
    expect(items).to_have_count(4)
    keys = items.evaluate_all("(els) => els.map((el) => el.dataset.template)")
    assert set(keys) == {"istqb", "iso25010", "nfr2018", "pmbok"}
    for item in items.all():
        expect(item).to_contain_text("観点")  # "X観点" のカウント表記が出ていること


def test_viewpoint_template_apply_seeds_folders_and_items_into_tree(page: Page) -> None:
    _open_viewpoints(page)
    page.locator("#vp-tree-template-btn").click()
    page.locator('[data-template="istqb"]').click()
    expect(page.locator("#confirm-overlay")).to_be_visible()
    expect(page.locator("#confirm-overlay")).to_contain_text("フォルダ")
    page.locator("#confirm-ok-btn").click()
    expect(page.locator("#vp-feedback")).to_contain_text("ISTQB テストレベル")

    tree = page.locator("#vp-tree-root")
    expect(tree).to_contain_text("単体テスト")
    expect(tree).to_contain_text("結合テスト")


def test_autorun_has_viewpoint_selector(page: Page) -> None:
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    page.locator('.app-nav-item[data-view="auto-run"]').click()
    selector = page.locator("#autorun-viewpoint-set")
    expect(selector).to_be_visible()
    expect(selector).to_have_value("")
    expect(page.locator("#autorun-viewpoint-recommendation")).to_contain_text("推奨")
