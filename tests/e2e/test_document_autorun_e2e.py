"""第3弾: AutoRun文書駆動モードのE2E契約。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")


@pytest.fixture()
def autorun_page(page: Page) -> Page:
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    autorun_nav = page.locator(".app-nav-item").filter(has_text="AutoRun").first
    if autorun_nav.count() > 0:
        autorun_nav.click()
    page.wait_for_selector("#view-auto-run", state="attached")
    return page


class TestDocumentDrivenMode:
    """URL駆動を保ったまま文書駆動設定へ切り替えられる。"""

    def test_default_is_url_mode_and_document_settings_are_hidden(self, autorun_page: Page) -> None:
        expect(autorun_page.locator("#autorun-mode-url")).to_be_checked()
        expect(autorun_page.locator("#autorun-document-options")).to_be_hidden()
        expect(autorun_page.locator("#autorun-url")).to_be_visible()

    def test_document_mode_reveals_safe_mbt_settings(self, autorun_page: Page) -> None:
        autorun_page.locator("label[for='autorun-mode-document']").click()

        expect(autorun_page.locator("#autorun-document-options")).to_be_visible()
        expect(autorun_page.locator("#autorun-reference-doc-input")).to_be_visible()
        expect(autorun_page.locator("#autorun-selection-criterion")).to_be_visible()
        expect(autorun_page.locator("#autorun-target-page-field")).to_be_hidden()
        expect(autorun_page.locator("#autorun-validation-safety-note")).to_contain_text(
            "入力のみ・送信しません"
        )

        autorun_page.locator("#autorun-selection-criterion").select_option("reached_target")
        expect(autorun_page.locator("#autorun-target-page-field")).to_be_visible()

    def test_start_posts_uploaded_document_and_safe_configuration(self, autorun_page: Page) -> None:
        captured: list[dict] = []
        upload_bodies: list[str] = []

        def reference_docs(route) -> None:
            upload_bodies.append(route.request.post_data or "")
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "ok": True,
                        "saved": [
                            {
                                "name": "requirements.md",
                                "path": "/output/example.com:8443/reference_docs/requirements.md",
                            }
                        ],
                    }
                ),
            )

        def start(route) -> None:
            captured.append(route.request.post_data_json)
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"ok": True, "job_id": "document-e2e"}),
            )

        autorun_page.route("**/api/reference-docs", reference_docs)
        autorun_page.route("**/api/autorun/start", start)
        autorun_page.locator("#autorun-url").fill("https://example.com:8443")
        autorun_page.locator("#autorun-mode-document").check()
        autorun_page.locator("#autorun-reference-doc-input").set_input_files(
            {
                "name": "requirements.md",
                "mimeType": "text/markdown",
                "buffer": b"# requirement",
            }
        )
        expect(autorun_page.locator("#autorun-reference-doc-list")).to_contain_text(
            "requirements.md"
        )
        autorun_page.locator("#autorun-selection-criterion").select_option("edge_coverage")
        autorun_page.locator("#autorun-observe-validation").check()
        autorun_page.locator("#autorun-start-btn").click()

        assert captured == [
            {
                "url": "https://example.com:8443",
                "depth": 5,
                "max_pages": 300,
                "viewpoint_set_id": "",
                "mode": "document",
                "reference_docs": ["/output/example.com:8443/reference_docs/requirements.md"],
                "selection_criterion": "edge_coverage",
                "target_page_id": "",
                "observe_validation": True,
            }
        ]
        assert upload_bodies and "example.com:8443" in upload_bodies[0]

    def test_url_mode_keeps_existing_start_payload(self, autorun_page: Page) -> None:
        captured: list[dict] = []

        def start(route) -> None:
            captured.append(route.request.post_data_json)
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"ok": True, "job_id": "url-e2e"}),
            )

        autorun_page.route("**/api/autorun/start", start)
        autorun_page.locator("#autorun-url").fill("https://example.com")
        autorun_page.locator("#autorun-start-btn").click()

        assert captured == [
            {
                "url": "https://example.com",
                "depth": 5,
                "max_pages": 300,
                "viewpoint_set_id": "",
            }
        ]

    def test_approval_summary_contains_document_coverage(self, autorun_page: Page) -> None:
        autorun_page.evaluate(
            """() => {
                _autoRunPreviewData = {
                    summary: {total: 3, by_status: {auto: 3}, filter_counts: {all: 3}}
                };
                window._autoRunLastData = {
                    step_data: {
                        crawl: {screens: 5},
                        document_mbt: {requirements: 4, matched_screens: 2, paths: 3, coverage_rate: 0.75}
                    }
                };
                _autorunPopulateApprovalModal();
            }"""
        )

        summary = autorun_page.locator("#arm-summary")
        expect(summary).to_contain_text("4文書要件")
        expect(summary).to_contain_text("2対応画面")
        expect(summary).to_contain_text("3選定パス")
        expect(summary).to_contain_text("75%カバー率")

    @pytest.mark.parametrize("width,height", [(1366, 768), (1920, 1080)])
    def test_document_mode_required_desktop_resolutions(
        self, autorun_page: Page, width: int, height: int
    ) -> None:
        autorun_page.set_viewport_size({"width": width, "height": height})
        autorun_page.locator("#autorun-mode-document").check()

        expect(autorun_page.locator("#autorun-document-options")).to_be_visible()
        expect(autorun_page.locator("#autorun-start-btn")).to_be_in_viewport()
        assert autorun_page.locator("#autorun-form-area").evaluate(
            "element => element.scrollWidth <= element.clientWidth"
        )
        screenshot = Path(__file__).parent / "screenshots" / f"third-wave-{width}x{height}.png"
        autorun_page.screenshot(path=screenshot, full_page=True)
