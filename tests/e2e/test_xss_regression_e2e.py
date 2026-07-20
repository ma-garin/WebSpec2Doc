"""レーンD-1: XSS回帰テスト（R3-20）。

A-2（実況OK/NG表示）で追加された `_autorunLiveTestRows()` は外部由来の
テストtitleをそのままHTMLへ連結せず `escHtml()` を通す規約（0-1）になっている。
古典的な onerror ベースのXSSペイロードでも要素として解釈されないことを固定する。
"""

from __future__ import annotations

import os

import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")


@pytest.fixture()
def autorun_page(page: Page) -> Page:
    # AutoRun は独立システム。`/` は「ドキュメント作成」系と判定され
    # AutoRun のナビ項目は非表示になるため、直接開く。
    page.goto(f"{BASE_URL}/auto-run")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#view-auto-run", state="attached")
    return page


def test_malicious_test_title_is_escaped(autorun_page: Page) -> None:
    """進捗NDJSON由来のtitleに<img onerror>を仕込んでもimg要素が生成されない。"""
    autorun_page.evaluate(
        """() => _autorunRender({
            status: 'running_tests',
            job_id: 'xss-test-job',
            domain: 'example.com',
            log: [], outputs: {}, test_results: null,
            test_progress: {
                completed: 1, total: 1, passed: 0, failed: 1,
                tests: [
                    {title: '<img src=x onerror=alert(1)>', status: 'failed',
                     duration_ms: 100, error: '<script>alert(2)</script>'},
                ],
            },
            started_at: '2026-07-06T10:00:00', elapsed_sec: 1,
            error: null, finished_at: null, input_request: null, run_policy: {},
        })"""
    )
    area = autorun_page.locator("#autorun-live-tests-area")
    expect(area.locator(".autorun-live-tests")).to_be_visible()
    # img要素・script要素として解釈されていないこと（escHtml回帰）
    expect(area.locator("img")).to_have_count(0)
    expect(area.locator("script")).to_have_count(0)
    # 文字列としては表示されている（捏造せず、エスケープして可視化）
    expect(area).to_contain_text("<img src=x onerror=alert(1)>")
