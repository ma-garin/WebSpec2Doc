"""APIリファレンスが遮断環境でも描画されることを実機で確認する。

外部ホストへの参照が1つでもあると、顧客のオフライン環境で崩れる。
ブラウザが実際に外部へ出ないことをネットワーク監視で固定する。
"""

from __future__ import annotations

import os

import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")


class TestApiDocs:
    def test_reference_renders_without_any_external_request(self, page: Page) -> None:
        external: list[str] = []

        def record(request) -> None:
            if not request.url.startswith(BASE_URL):
                external.append(request.url)

        page.on("request", record)
        page.goto(f"{BASE_URL}/api/v1/docs")
        page.wait_for_load_state("networkidle")

        expect(page.locator("h1")).to_contain_text("WebSpec2Doc API")
        assert external == [], f"外部への通信が発生した: {external}"



