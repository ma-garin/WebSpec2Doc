"""第2弾のデータ管理・監査ログをブラウザ境界で確認する。"""

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


def test_data_retention_and_admin_audit_flow(page: Page) -> None:
    saved_policies: list[dict] = []
    audit_queries: list[str] = []
    page.route(
        "**/api/admin/storage",
        lambda route: _json(
            route,
            {
                "storage": {
                    "output_bytes": 3_145_728,
                    "instance_bytes": 524_288,
                    "total_bytes": 3_670_016,
                    "sites": [
                        {
                            "domain": "example.com",
                            "snapshot_count": 12,
                            "snapshot_bytes": 2_097_152,
                            "total_bytes": 3_145_728,
                            "updated_at": "2026-07-17T10:00:00+00:00",
                        }
                    ],
                }
            },
        ),
    )

    def retention(route: Route) -> None:
        if route.request.method == "PUT":
            saved_policies.append(route.request.post_data_json)
            _json(
                route,
                {
                    "ok": True,
                    "policy": {
                        **saved_policies[-1],
                        "days": None,
                        "updated_at": "2026-07-17T10:00:00+00:00",
                        "updated_by": "local-admin",
                    },
                },
            )
            return
        policy = saved_policies[-1] if saved_policies else {"mode": "unlimited"}
        _json(
            route,
            {
                "policy": {
                    "mode": policy.get("mode", "unlimited"),
                    "generations": policy.get("generations"),
                    "days": policy.get("days"),
                    "updated_at": "",
                    "updated_by": "",
                }
            },
        )

    page.route("**/api/admin/retention", retention)

    def audit(route: Route) -> None:
        audit_queries.append(route.request.url)
        next_page = "offset=1" in route.request.url
        _json(
            route,
            {
                "events": [
                    {
                        "version": 1,
                        "id": "event-2" if next_page else "event-1",
                        "at": "2026-07-17T10:00:00+00:00",
                        "actor_id": "admin-1",
                        "actor_email": "admin@example.com",
                        "action": (
                            "notification.tested" if next_page else "retention.settings_updated"
                        ),
                        "target_type": "workspace",
                        "target_id": "current",
                        "outcome": "success",
                        "detail": (
                            {"channel": "slack"}
                            if next_page
                            else {"changed_fields": ["mode", "generations"]}
                        ),
                    }
                ],
                "has_more": not next_page,
                "next_offset": None if next_page else 1,
            },
        )

    page.route("**/api/admin/audit**", audit)
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(BASE_URL)
    page.locator('.app-nav-item[data-view="settings"]').click()
    page.locator("#set-tab-data").click()

    expect(page.locator("#storage-total")).to_contain_text("MB")
    expect(page.locator("#storage-sites")).to_contain_text("example.com")
    expect(page.locator("#storage-sites")).to_contain_text("12件")
    page.locator("#retention-mode").select_option("generations")
    expect(page.locator("#retention-generations-field")).to_be_visible()
    expect(page.locator("#retention-days-field")).to_be_hidden()
    page.locator("#retention-generations").fill("12")
    page.locator("#retention-save").click()
    expect(page.locator("#retention-msg")).to_contain_text("保持設定を保存しました")
    assert saved_policies[-1] == {"mode": "generations", "generations": 12}
    page.screenshot(path="tests/e2e/screenshots/second-wave-data-1366x768.png")

    page.locator("#set-tab-audit").click()
    expect(page.locator("#audit-action option[value='notification.tested']")).to_have_text(
        "通知テスト"
    )
    expect(page.locator("#admin-audit-events")).to_contain_text("admin@example.com")
    expect(page.locator("#admin-audit-events")).to_contain_text("保持設定")
    page.locator("#audit-query").fill("admin@example.com")
    page.locator("#audit-search").click()
    expect(page.locator("#admin-audit-events")).to_contain_text("成功")
    expect(page.locator("#audit-load-more")).to_be_visible()
    page.locator("#audit-load-more").click()
    expect(page.locator("#admin-audit-events")).to_contain_text("通知テスト")
    expect(page.locator("#audit-load-more")).to_be_hidden()
    assert any("query=admin%40example.com" in url for url in audit_queries)
    assert any("offset=1" in url for url in audit_queries)
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.screenshot(path="tests/e2e/screenshots/second-wave-audit-1920x1080.png")
