"""
観点管理UIのheadless高速検証スクリプト（3ペインUI対応）。
"""

import asyncio
import os
import sys

from playwright.async_api import async_playwright

# 既定ポートは 8765（web/config.py の PORT）。5555 を固定していたため、
# アプリを普通に起動した状態では接続できず、この検証は動かせなかった。
# E2E と同じ環境変数で上書きできるようにする。
BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")
PASSED = []
FAILED = []
UNVERIFIED = []


def ok(label):
    PASSED.append(label)
    print(f"  ✓ {label}")


def fail(label, detail=""):
    FAILED.append(label)
    print(f"  ✗ {label}  {detail}")


def unverified(label, reason=""):
    """検証できなかったもの。PASS にも FAIL にもしない。

    前提データが無いだけの状態を FAIL にすると、不具合と区別できなくなる。
    かといって PASS にすると、通っていないものを通ったことにしてしまう。
    """
    UNVERIFIED.append(f"{label}（{reason}）" if reason else label)
    print(f"  – {label}  未確認: {reason}")


async def wait_dialog_open(page, timeout=3000):
    await page.wait_for_selector("#input-dialog-overlay", state="visible", timeout=timeout)


async def wait_dialog_close(page, timeout=3000):
    await page.locator("#input-dialog-overlay").wait_for(state="hidden", timeout=timeout)


async def run():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        # driver.js のツアーはフレッシュなブラウザで自動起動し、その SVG
        # オーバーレイがクリックを遮る。ツアー自体はここの検証対象ではないため
        # 完了済みとして始める（tests/e2e/conftest.py と同じ扱い）。
        await page.add_init_script(
            "try { localStorage.setItem('webspec2doc.onboarding.tour-completed', '1'); }"
            " catch (e) { /* private mode 等では何もしない */ }"
        )

        # ---- 1. ページ読み込み + 3ペインUI確認 ----
        await page.goto(BASE_URL, wait_until="networkidle")
        await page.click("text=観点管理")
        await page.wait_for_selector(".vp-workspace", timeout=5000)
        ok("観点管理ビュー / 3ペインレイアウト表示")

        # ---- 2. テーブルにアイテムが表示される ----
        await page.wait_for_selector("#vp-table-body tr[data-vp-item-id]", timeout=6000)
        count_text = await page.text_content("#vp-item-count")
        ok(f"観点テーブル表示: {count_text}")

        # ---- 3. ツリーパネルにフォルダが表示される ----
        folders = await page.query_selector_all(".vp-tree-node")
        if folders:
            ok(f"分類ツリー: {len(folders)}フォルダ")
        else:
            # 既定の観点セットはフォルダを持たない（分類は項目側の category）。
            # フォルダが無いこと自体は不具合ではないので FAIL にしない。
            unverified("分類ツリーのフォルダ表示", "既定データにフォルダが未作成")

        # ---- 4. フォルダクリックでフィルタ ----
        if folders:
            await folders[0].click()
            await page.wait_for_timeout(400)
            filtered_count = await page.text_content("#vp-item-count")
            total_rows = await page.locator("#vp-table-body tr[data-vp-item-id]").count()
            ok(f"フォルダフィルタ: {filtered_count} ({total_rows}行)")
            # すべてに戻す
            await page.click("#vp-tree-all-btn")
            await page.wait_for_timeout(300)

        # ---- 5. テンプレートメニュー ----
        await page.click("#vp-tree-template-btn")
        menu_visible = await page.is_visible("#vp-template-menu")
        ok("テンプレートメニュー表示") if menu_visible else fail("テンプレートメニュー未表示")
        # Escape で閉じる。以前は body の中央を押して閉じていたが、
        # メニュー項目の上を踏んでテンプレート適用の確認ダイアログが開き、
        # 以降の操作が全て塞がれていた。
        await page.keyboard.press("Escape")
        await page.wait_for_selector("#vp-template-menu", state="hidden", timeout=5000)

        # ---- 6. 新規セット inputDialog ----
        await page.click("#vp-new-set")
        await wait_dialog_open(page)
        textarea_visible = await page.is_visible("#input-dialog-textarea")
        input_visible = await page.is_visible("#input-dialog-input")
        (
            ok("新規セット: textareaが非表示・inputが表示")
            if not textarea_visible and input_visible
            else fail("新規セット: textarea表示バグ")
        )
        await page.keyboard.press("Escape")
        await wait_dialog_close(page)

        # ---- 7. 公開ボタン confirmDialog ----
        await page.click("#vp-publish")
        await page.wait_for_selector("#confirm-overlay", state="visible", timeout=3000)
        ok("公開: 確認ダイアログ表示")
        await page.click("#confirm-cancel-btn")
        await page.locator("#confirm-overlay").wait_for(state="hidden", timeout=2000)

        # ---- 8. バルク操作 ----
        checkboxes = await page.query_selector_all("input[data-vp-check]")
        if checkboxes:
            await checkboxes[0].click()
            await page.wait_for_selector("#vp-bulkbar", state="visible", timeout=3000)
            ok("バルクバー: 1件選択で表示")

            for bulk_action, expected_title in [
                ("tag", "タグ"),
                ("category", "カテゴリ"),
                ("risk", "リスク"),
            ]:
                await page.click(f"button[data-vp-bulk='{bulk_action}']")
                await wait_dialog_open(page)
                title = await page.text_content("#input-dialog-title")
                (
                    ok(f"バルク{expected_title}: [{title}]")
                    if expected_title in (title or "")
                    else fail(f"バルク{expected_title}", title)
                )
                await page.keyboard.press("Escape")
                await wait_dialog_close(page)

            # リスクバリデーション
            await page.click("button[data-vp-bulk='risk']")
            await wait_dialog_open(page)
            await page.fill("#input-dialog-input", "abc")
            await page.click("#input-dialog-ok-btn")
            error_visible = await page.is_visible("#input-dialog-error")
            (
                ok("バルクリスク: 不正値でエラー表示")
                if error_visible
                else fail("バルクリスク: バリデーションエラーなし")
            )
            await page.keyboard.press("Escape")
            await wait_dialog_close(page)

            await page.click("#vp-clear-selection")
            await page.locator("#vp-bulkbar").wait_for(state="hidden", timeout=2000)
            ok("バルクバー: 選択解除で非表示")
        else:
            fail("バルクバー: チェックボックスなし")

        # ---- 9. 適用ルール追加 ----
        await page.click("#vp-new-assignment")
        await wait_dialog_open(page)
        title = await page.text_content("#input-dialog-title")
        ok(f"適用ルール追加: [{title}]")
        await page.keyboard.press("Escape")
        await wait_dialog_close(page)

        # ---- 10. エディタモーダル（行の✏ボタンから開く） ----
        edit_btns = await page.query_selector_all("[data-vp-edit]")
        if edit_btns:
            await edit_btns[0].click()
            await page.wait_for_selector("#vp-editor-overlay", state="visible", timeout=3000)
            ok("エディタモーダル: ✏ボタンで表示")
            options = await page.query_selector_all("#vp-category-datalist option")
            (
                ok(f"カテゴリdatalist: {len(options)}件")
                if options
                else fail("カテゴリdatalist: 候補なし")
            )
            await page.click("#vp-editor-close")
            await page.wait_for_selector("#vp-editor-overlay", state="hidden", timeout=2000)
            ok("エディタモーダル: 閉じる動作")
        else:
            fail("エディタモーダル: ✏ボタンなし")

        await browser.close()

    # ---- 結果サマリ ----
    print()
    print("=" * 50)
    print(f"PASSED: {len(PASSED)}  FAILED: {len(FAILED)}  未確認: {len(UNVERIFIED)}")
    for u in UNVERIFIED:
        print(f"  – {u}")
    if FAILED:
        for f in FAILED:
            print(f"  ✗ {f}")
        sys.exit(1)
    print("失敗なし（未確認は上記のとおり）。")


if __name__ == "__main__":
    asyncio.run(run())
