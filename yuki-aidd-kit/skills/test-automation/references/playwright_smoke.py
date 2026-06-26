"""
Playwright スモークテスト scaffold（PWA / 単一HTMLツール用）
セットアップ:
  pip install pytest pytest-playwright
  playwright install chromium
実行:
  pytest tests/test_smoke.py -v
"""
import pytest
from playwright.sync_api import Page, expect

APP_URL = "http://localhost:8000/index.html"  # python3 -m http.server 8000 で起動


def test_page_loads_without_errors(page: Page):
    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.goto(APP_URL)
    assert errors == [], f"console errorあり: {errors}"


def test_localStorage_persistence(page: Page):
    page.goto(APP_URL)
    # 例: 入力 → 保存ボタン
    page.fill("#input-amount", "1000")
    page.click("#btn-save")
    # reload後もデータが残る
    page.reload()
    saved = page.evaluate("() => localStorage.getItem('myapp:entries')")
    assert saved is not None and "1000" in saved


def test_export_works(page: Page):
    page.goto(APP_URL)
    with page.expect_download() as dl_info:
        page.click("#btn-export")
    download = dl_info.value
    assert download.suggested_filename.endswith((".json", ".csv"))


@pytest.mark.parametrize("width,height", [(360, 820), (768, 1812)])  # 折りたたみ端末 カバー/メイン
def test_responsive_fold5(page: Page, width, height):
    page.set_viewport_size({"width": width, "height": height})
    page.goto(APP_URL)
    # 主要操作ボタンが画面内に表示されている
    expect(page.locator("#btn-save")).to_be_visible()


def test_offline_mode(context, page: Page):
    page.goto(APP_URL)  # 先にService Workerでキャッシュさせる
    context.set_offline(True)
    page.reload()
    expect(page.locator("#app-root")).to_be_visible()
