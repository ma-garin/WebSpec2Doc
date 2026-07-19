"""SPEC-1-5: Doc Fusion の Web UI 統合（参考文書アップロードとギャップ表示）の E2E テスト。

対象:
    - templates/partials/view-generate.html のステップ2 参考文書アップロード欄
    - 結果タブの「文書突合」タブ（doc_fusion.json 存在時のみ表示）
    - static/js/wizard.js::アップロードUI / static/js/doc-fusion.js::renderDocFusion

実行方法:
    make verify-ui
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")
FIXTURE_DOMAIN = "e2e-doc-fusion.example.com"
NO_DOCS_DOMAIN = "e2e-doc-fusion-empty.example.com"
ROOT = Path(__file__).parent.parent.parent
FIXTURE_DIR = ROOT / "output" / FIXTURE_DOMAIN
NO_DOCS_DIR = ROOT / "output" / NO_DOCS_DOMAIN


def _minimal_report(domain: str) -> dict:
    return {
        "meta": {"target_url": f"https://{domain}/", "crawled_at": "2026-07-01 12:00"},
        "screens": [
            {
                "page_id": "P001",
                "title": "トップ",
                "url": f"https://{domain}/",
                "is_canonical": True,
                "headings": [],
                "buttons": [],
                "forms": [],
                "transitions": {"to": [], "from": []},
            }
        ],
    }


FIXTURE_DOC_FUSION = {
    "meta": {
        "source_files": ["screens.yaml"],
        "documented_screens": 2,
        "documented_fields": 1,
        "matched_screens": 1,
        "doc_only_screens": 1,
        "crawl_only_screens": 0,
        "field_gaps": 1,
    },
    "screen_matches": [
        {
            "page_id": "P001",
            "page_url": f"https://{FIXTURE_DOMAIN}/",
            "page_title": "トップ",
            "official_name": "トップ画面",
            "screen_id": "GA-001",
            "score": 1.0,
            "method": "url",
            "doc_evidence": {"file": "screens.yaml", "location": "$.screens[0]", "quote": ""},
        }
    ],
    "doc_only_screens": [
        {
            "name": "廃止済み管理画面",
            "screen_id": "GA-099",
            "url_hint": "/admin-legacy",
            "doc_evidence": {"file": "screens.yaml", "location": "$.screens[1]", "quote": ""},
        }
    ],
    "crawl_only_page_ids": [],
    "field_gaps": [
        {
            "kind": "mismatch",
            "page_id": "P001",
            "field_name": "amount",
            "detail": "限度値が矛盾: 文書では 500000、実測 max_value=1000000",
            "doc_evidence": {"file": "screens.yaml", "location": "line 5", "quote": "限度額50万円"},
            "crawl_selector": "[name='amount']",
        }
    ],
}


@pytest.fixture(scope="module", autouse=True)
def doc_fusion_fixture() -> Generator[None, None, None]:
    """doc_fusion.json 集計済みドメインと未集計ドメインを output/ に配置する。"""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / "report.json").write_text(
        json.dumps(_minimal_report(FIXTURE_DOMAIN), ensure_ascii=False), encoding="utf-8"
    )
    (FIXTURE_DIR / "doc_fusion.json").write_text(
        json.dumps(FIXTURE_DOC_FUSION, ensure_ascii=False), encoding="utf-8"
    )

    NO_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (NO_DOCS_DIR / "report.json").write_text(
        json.dumps(_minimal_report(NO_DOCS_DOMAIN), ensure_ascii=False), encoding="utf-8"
    )

    yield
    shutil.rmtree(FIXTURE_DIR, ignore_errors=True)
    shutil.rmtree(NO_DOCS_DIR, ignore_errors=True)


def _open_report(page: Page, domain: str) -> None:
    page.goto(f"{BASE_URL}/#report/{domain}")
    expect(page.locator("#result-panel")).to_be_visible()
    expect(page.locator("#r-domain")).to_have_text(domain)


class TestReferenceDocUpload:
    def test_reference_doc_upload_flow(self, page: Page, tmp_path: Path) -> None:
        page.goto(f"{BASE_URL}/")
        page.locator("#nav-new-analysis-btn").click()
        expect(page.locator("#view-generate")).to_be_visible()
        page.fill("#url-input", "https://e2e-doc-fusion-upload.example.com/")
        page.evaluate("showWizardStep(2)")
        expect(page.locator("#reference-doc-input")).to_be_attached()

        upload_file = tmp_path / "screens.yaml"
        upload_file.write_text("screens: []", encoding="utf-8")
        page.locator("#reference-doc-input").set_input_files(str(upload_file))

        expect(page.locator("#reference-doc-list li")).to_have_count(1)
        expect(page.locator("#reference-doc-list")).to_contain_text("screens.yaml")

        # 削除ボタンで一覧から消える
        page.locator("#reference-doc-list .reference-doc-remove-btn").click()
        expect(page.locator("#reference-doc-list li")).to_have_count(0)

    def test_reference_doc_upload_rejects_unsupported(self, page: Page, tmp_path: Path) -> None:
        page.goto(f"{BASE_URL}/")
        page.locator("#nav-new-analysis-btn").click()
        expect(page.locator("#view-generate")).to_be_visible()
        page.fill("#url-input", "https://e2e-doc-fusion-reject.example.com/")
        page.evaluate("showWizardStep(2)")

        bad_file = tmp_path / "malware.exe"
        bad_file.write_bytes(b"MZ")
        page.locator("#reference-doc-input").set_input_files(str(bad_file))

        expect(page.locator("#reference-doc-status")).to_contain_text("対応形式")
        expect(page.locator("#reference-doc-list li")).to_have_count(0)


class TestDocFusionTab:
    def test_gap_tab_visible_after_fusion(self, page: Page) -> None:
        _open_report(page, FIXTURE_DOMAIN)
        tab = page.locator('.result-tab[data-tab="doc-fusion"]')
        expect(tab).to_be_visible()
        tab.click()
        expect(page.locator("#rp-doc-fusion")).to_contain_text("文書×実測 突合")
        expect(page.locator("#rp-doc-fusion")).to_contain_text("限度値が矛盾")

    def test_no_docs_no_tab(self, page: Page) -> None:
        _open_report(page, NO_DOCS_DOMAIN)
        expect(page.locator('.result-tab[data-tab="doc-fusion"]')).to_be_hidden()
