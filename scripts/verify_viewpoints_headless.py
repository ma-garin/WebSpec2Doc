"""
観点管理UIのheadless高速検証スクリプト。
inputDialog 置き換え後の各フローをPlaywright headlessで確認する。
"""
import asyncio
import sys
from playwright.async_api import async_playwright

BASE_URL = "http://localhost:5555"
PASSED = []
FAILED = []


def ok(label):
    PASSED.append(label)
    print(f"  ✓ {label}")


def fail(label, detail=""):
    FAILED.append(label)
    print(f"  ✗ {label}  {detail}")


async def wait_dialog_open(page, timeout=3000):
    await page.wait_for_selector("#input-dialog-overlay", state="visible", timeout=timeout)


async def wait_dialog_close(page, timeout=3000):
    await page.locator("#input-dialog-overlay").wait_for(state="hidden", timeout=timeout)


async def run():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        # ---- ページ読み込み ----
        await page.goto(BASE_URL, wait_until="networkidle")
        await page.click("text=観点管理")
        await page.wait_for_selector("#vp-list-content", timeout=5000)
        ok("観点管理ビュー表示")

        # ---- 1. textarea が hidden になっているか ----
        await page.click("#vp-new-set")
        await wait_dialog_open(page)
        textarea_visible = await page.is_visible("#input-dialog-textarea")
        input_visible = await page.is_visible("#input-dialog-input")
        if not textarea_visible and input_visible:
            ok("新規セット: textareaが非表示・inputが表示")
        else:
            fail("新規セット: textarea表示バグ", f"textarea={textarea_visible} input={input_visible}")
        await page.keyboard.press("Escape")
        await wait_dialog_close(page)
        ok("新規セット: Escapeでキャンセル")

        # ---- 2. 公開フロー: confirmDialogが出るか ----
        await page.click("#vp-publish")
        await page.wait_for_selector("#confirm-overlay", state="visible", timeout=3000)
        ok("公開: 確認ダイアログ表示")
        await page.click("#confirm-cancel-btn")
        await page.locator("#confirm-overlay").wait_for(state="hidden", timeout=2000)
        ok("公開: キャンセルで閉じる")

        # ---- 3-5. バルク操作 ----
        checkboxes = await page.query_selector_all("input[data-vp-check]")
        if checkboxes:
            await checkboxes[0].click()
            await page.wait_for_selector("#vp-bulkbar", state="visible", timeout=3000)
            ok("バルクバー: 1件選択で表示")

            # タグ
            await page.click("button[data-vp-bulk='tag']")
            await wait_dialog_open(page)
            title = await page.text_content("#input-dialog-title")
            ok(f"バルクタグ: inputDialog [{title}]") if "タグ" in (title or "") else fail("バルクタグ", title)
            await page.keyboard.press("Escape")
            await wait_dialog_close(page)

            # カテゴリ
            await page.click("button[data-vp-bulk='category']")
            await wait_dialog_open(page)
            title = await page.text_content("#input-dialog-title")
            ok(f"バルクカテゴリ: inputDialog [{title}]") if "カテゴリ" in (title or "") else fail("バルクカテゴリ", title)
            await page.keyboard.press("Escape")
            await wait_dialog_close(page)

            # リスク（バリデーション確認）
            await page.click("button[data-vp-bulk='risk']")
            await wait_dialog_open(page)
            title = await page.text_content("#input-dialog-title")
            ok(f"バルクリスク: inputDialog [{title}]") if "リスク" in (title or "") else fail("バルクリスク", title)
            await page.fill("#input-dialog-input", "abc")
            await page.click("#input-dialog-ok-btn")
            error_visible = await page.is_visible("#input-dialog-error")
            ok("バルクリスク: 不正値でエラー表示") if error_visible else fail("バルクリスク: バリデーションエラーが出ない")
            await page.keyboard.press("Escape")
            await wait_dialog_close(page)

            # 選択解除
            await page.click("#vp-clear-selection")
            await page.locator("#vp-bulkbar").wait_for(state="hidden", timeout=2000)
            ok("バルクバー: 選択解除で非表示")
        else:
            fail("バルクバー: チェックボックスが見つからない")

        # ---- 6. 適用ルール追加 ----
        await page.click("#vp-new-assignment")
        await wait_dialog_open(page)
        title = await page.text_content("#input-dialog-title")
        ok(f"適用ルール追加: inputDialog表示 [{title}]")
        await page.keyboard.press("Escape")
        await wait_dialog_close(page)

        # ---- 7. セット設定 ----
        await page.click("#vp-edit-set")
        await wait_dialog_open(page)
        title = await page.text_content("#input-dialog-title")
        ok(f"セット設定: inputDialog表示 [{title}]")
        await page.keyboard.press("Escape")
        await wait_dialog_close(page)

        # ---- 8. エディタモーダル ----
        rows = await page.query_selector_all("tr[data-vp-item-id]")
        if rows:
            await rows[0].click()
            await page.wait_for_selector("#vp-editor-overlay", state="visible", timeout=3000)
            ok("エディタモーダル: 行クリックで表示")
            # カテゴリdatalist確認
            options = await page.query_selector_all("#vp-category-datalist option")
            ok(f"カテゴリdatalist: {len(options)}件の候補") if options else fail("カテゴリdatalist: 候補なし")
            await page.click("#vp-editor-close")
            await page.wait_for_selector("#vp-editor-overlay", state="hidden", timeout=2000)
            ok("エディタモーダル: 閉じる動作")
        else:
            fail("エディタモーダル: 行が見つからない")

        await browser.close()

    # ---- 結果サマリ ----
    print()
    print("=" * 50)
    print(f"PASSED: {len(PASSED)}  FAILED: {len(FAILED)}")
    if FAILED:
        print("FAILED items:")
        for f in FAILED:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("All checks passed.")


if __name__ == "__main__":
    asyncio.run(run())
