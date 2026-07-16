"""第1弾の主要ユーザーフローをブラウザ境界で確認する。"""

from __future__ import annotations

import json
import os

from playwright.sync_api import Page, Route, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")


def _json(route: Route, body: dict, status: int = 200) -> None:
    route.fulfill(
        status=status,
        content_type="application/json",
        body=json.dumps(body, ensure_ascii=False),
    )


def test_tour_replay_shows_checklist_only_during_tour(page: Page) -> None:
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(BASE_URL)
    expect(page.locator("#onboarding-checklist")).to_be_hidden()

    page.locator('.app-nav-item[data-view="settings"]').click()
    page.locator("#set-tab-operations").click()
    page.locator("#restart-tour").click()

    expect(page.locator("#view-dashboard")).to_be_visible()
    expect(page.locator("#onboarding-checklist")).to_be_visible()
    expect(page.locator(".driver-popover-title")).to_contain_text("対象サイトを入力")
    page.wait_for_timeout(500)  # driver.js の表示アニメーション完了後を目視証跡にする
    page.screenshot(path="tests/e2e/screenshots/first-wave-tour-1366x768.png")

    page.locator(".wsd-tour-skip").click()
    expect(page.locator(".driver-popover")).to_be_hidden()
    expect(page.locator("#onboarding-checklist")).to_be_hidden()


def test_empty_state_demo_link_prefills_bundled_demo(page: Page) -> None:
    page.route("**/api/history", lambda route: _json(route, {"items": []}))
    page.goto(BASE_URL)
    expect(page.locator(".empty-demo-btn")).to_be_visible()
    page.locator(".empty-demo-btn").click()
    expect(page.locator("#hero-url")).to_have_value("http://127.0.0.1:8766/")


def test_operations_settings_save_and_test_notification(page: Page) -> None:
    saved_payloads: list[dict] = []
    test_payloads: list[dict] = []

    page.route(
        "**/api/history",
        lambda route: _json(
            route,
            {
                "items": [
                    {
                        "domain": "example.com",
                        "site_url": "http://example.com:8080/catalog?mode=demo",
                        "screens": 1,
                        "fields": 2,
                    }
                ]
            },
        ),
    )

    def schedule_config(route: Route) -> None:
        if route.request.method == "POST":
            saved_payloads.append(route.request.post_data_json)
            _json(route, {"ok": True, "next_run_at": "2026-07-17T02:00:00+09:00"})
            return
        current = {
            "domain": "example.com",
            "site_url": "",
            "interval": "disabled",
            "timezone": "Asia/Tokyo",
            "weekdays": [],
            "window_start": "",
            "window_end": "",
            "retry_max": 2,
            "retry_backoff_seconds": 60,
            "notify_type": "none",
            "notify_endpoint_set": False,
            "notify_template": "",
            "diff_summary_limit": 5,
        }
        if saved_payloads:
            current.update(saved_payloads[-1])
            current["notify_endpoint_set"] = bool(current.pop("notify_endpoint", ""))
        _json(route, current)

    page.route("**/schedule/config**", schedule_config)
    page.route("**/schedule/history**", lambda route: _json(route, {"items": []}))

    def notification_test(route: Route) -> None:
        test_payloads.append(route.request.post_data_json)
        _json(route, {"ok": True, "message": "テスト通知を送信しました。"})

    page.route("**/schedule/notify/test", notification_test)
    page.goto(BASE_URL)
    page.locator('.app-nav-item[data-view="settings"]').click()
    page.locator("#set-tab-operations").click()
    expect(page.locator("#ops-site")).to_have_value("example.com")
    expect(page.locator("#ops-site-url")).to_have_value("http://example.com:8080/catalog?mode=demo")

    page.locator("#ops-interval").select_option("weekly")
    page.locator("#ops-window-start").fill("02:00")
    page.locator("#ops-window-end").fill("05:00")
    page.locator('.ops-weekdays input[value="0"]').check()
    page.locator('.ops-weekdays input[value="4"]').check()
    page.locator("#ops-retry-max").fill("3")
    page.locator("#ops-notify-type").select_option("teams")
    page.locator("#ops-endpoint").fill("https://example.invalid/webhook")
    page.locator("#ops-template").fill("{{ site_url }} changed")
    page.locator("#ops-save").click()

    expect(page.locator("#ops-msg")).to_contain_text("運用設定を保存しました")
    expect(page.locator("#ops-endpoint")).to_have_value("")
    expect(page.locator("#ops-endpoint")).to_have_attribute(
        "placeholder", "設定済み（変更時のみ入力）"
    )
    assert saved_payloads[-1]["weekdays"] == [0, 4]
    assert saved_payloads[-1]["retry_max"] == 3
    assert saved_payloads[-1]["notify_type"] == "teams"

    page.locator("#ops-test-notify").click()
    expect(page.locator("#ops-msg")).to_contain_text("テスト通知を送信しました")
    assert test_payloads[-1]["notify_type"] == "teams"
