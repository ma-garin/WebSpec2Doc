"""証跡パックの契約。

守るべきは「欠落を黙って埋めないこと」と「主張境界が必ず出ること」。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from evidence.pack_model import CLAIM_NOTICE, build_evidence_pack
from evidence.pack_reporter import render_html, render_markdown, save_evidence_pack

FIXED_TIME = datetime(2026, 7, 19, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


def _report() -> dict:
    return {
        "ok": False,
        "total": 2,
        "passed": 1,
        "failed": 1,
        "skipped": 0,
        "duration_ms": 4200,
        "tests": [
            {
                "title": "PW-0001 画面表示スモーク [P001]",
                "status": "passed",
                "duration_ms": 1041,
                "error": "",
            },
            {
                "title": "PW-0002 画面遷移 [P002]",
                "status": "failed",
                "duration_ms": 3159,
                "error": "Timeout   30000ms  exceeded\n  waiting for locator",
            },
        ],
    }


def _meta() -> dict:
    return {
        "domain": "example.com",
        "tests": [
            {
                "test_id": "PW-0001",
                "title": "画面表示スモーク",
                "page_id": "P001",
                "url": "https://example.com/",
            },
            {
                "test_id": "PW-0002",
                "title": "画面遷移",
                "page_id": "P002",
                "url": "https://example.com/search",
            },
        ],
    }


def _viewpoints() -> dict:
    return {"screen_risks": [{"page_id": "P002", "viewpoint_ids": ["QV-03", "QV-01"]}]}


# ─────────────────── 組み立て ───────────────────


def test_cases_match_report_count_and_join_meta_by_test_id() -> None:
    pack = build_evidence_pack(_report(), _viewpoints(), _meta(), generated_at=FIXED_TIME)

    assert len(pack["cases"]) == 2
    first = pack["cases"][0]
    assert first["case_id"] == "PW-0001"
    assert first["title"] == "画面表示スモーク"
    assert first["page_id"] == "P001"
    assert first["page_url"] == "https://example.com/"


def test_viewpoints_are_attached_per_page_and_sorted() -> None:
    pack = build_evidence_pack(_report(), _viewpoints(), _meta(), generated_at=FIXED_TIME)

    assert pack["cases"][1]["viewpoint_ids"] == ["QV-01", "QV-03"]


def test_missing_viewpoints_are_declared_not_invented() -> None:
    pack = build_evidence_pack(_report(), None, _meta(), generated_at=FIXED_TIME)

    assert "quality_viewpoints" in pack["meta"]["missing_inputs"]
    assert all(case["viewpoint_ids"] == [] for case in pack["cases"])


def test_absent_report_yields_empty_record_instead_of_raising() -> None:
    pack = build_evidence_pack(None, generated_at=FIXED_TIME)

    assert pack["cases"] == []
    assert "playwright_report" in pack["meta"]["missing_inputs"]


def test_failure_category_is_attached_only_to_failed_cases() -> None:
    classifications = [
        {"test_id": "PW-0001", "category": "env_issue"},
        {"test_id": "PW-0002", "category": "app_change"},
    ]

    pack = build_evidence_pack(
        _report(), _viewpoints(), _meta(), classifications, generated_at=FIXED_TIME
    )

    assert pack["cases"][0]["failure_category"] == ""
    assert pack["cases"][1]["failure_category"] == "app_change"


def test_only_supplied_screenshots_are_linked() -> None:
    pack = build_evidence_pack(
        _report(),
        _viewpoints(),
        _meta(),
        screenshots={"P001": "../screenshots/P001.png"},
        generated_at=FIXED_TIME,
    )

    assert pack["cases"][0]["screenshot_path"] == "../screenshots/P001.png"
    assert pack["cases"][1]["screenshot_path"] == ""


def test_error_excerpt_is_collapsed_and_bounded() -> None:
    pack = build_evidence_pack(_report(), generated_at=FIXED_TIME)

    excerpt = pack["cases"][1]["error_excerpt"]
    assert "\n" not in excerpt
    assert excerpt.startswith("Timeout 30000ms exceeded")
    assert len(excerpt) <= 400


def test_summary_and_duration_come_from_report() -> None:
    pack = build_evidence_pack(_report(), generated_at=FIXED_TIME)

    assert pack["summary"] == {
        "total": 2,
        "passed": 1,
        "failed": 1,
        "skipped": 0,
        "duration_sec": 4.2,
    }


def test_claim_scope_is_always_present() -> None:
    pack = build_evidence_pack(None, generated_at=FIXED_TIME)

    assert pack["meta"]["claim_scope"] == "executed_record_only"
    assert pack["meta"]["claim_notice"] == CLAIM_NOTICE


# ─────────────────── 出力 ───────────────────


def test_markdown_leads_with_claim_notice_and_lists_missing_inputs() -> None:
    pack = build_evidence_pack(_report(), None, _meta(), generated_at=FIXED_TIME)

    markdown = render_markdown(pack)

    assert CLAIM_NOTICE in markdown.split("## ")[0]
    assert "未取得の材料" in markdown
    assert "PW-0002" in markdown


def test_html_is_self_contained_without_external_hosts() -> None:
    pack = build_evidence_pack(_report(), _viewpoints(), _meta(), generated_at=FIXED_TIME)

    document = render_html(pack)

    assert CLAIM_NOTICE in document
    assert "http://" not in document.replace('lang="ja"', "")
    assert "https://cdn" not in document
    assert "<script" not in document


def test_save_writes_both_formats(tmp_path: Path) -> None:
    pack = build_evidence_pack(_report(), _viewpoints(), _meta(), generated_at=FIXED_TIME)

    paths = save_evidence_pack(pack, tmp_path)

    assert paths["evidence_pack_md"].is_file()
    assert paths["evidence_pack_html"].is_file()
    assert "テスト実施証跡パック" in paths["evidence_pack_html"].read_text(encoding="utf-8")


def test_manual_section_is_included_when_supplied(tmp_path: Path) -> None:
    pack = build_evidence_pack(
        _report(),
        _viewpoints(),
        _meta(),
        manual_procedures="# 手順\n1. ログイン",
        generated_at=FIXED_TIME,
    )

    assert "手動テストの実施手順" in render_markdown(pack)
    assert "手動テストの実施手順" in render_html(pack)
