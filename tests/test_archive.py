"""完全アーカイブと外形監視の契約。

守るべきは「アーカイブが元データを消さないこと」と「改竄を受け取り側が検知できること」。
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from archive.external_monitor import (
    diff_documents,
    diff_sitemaps,
    fingerprint_document,
    parse_sitemap,
)
from archive.full_archive import (
    CLAIM_NOTICE,
    MANIFEST_NAME,
    create_full_archive,
    verify_archive,
)

FIXED = datetime(2026, 7, 19, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://e.com/</loc></url>
  <url><loc>https://e.com/help</loc></url>
</urlset>"""


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "site"
    (source / "qa_process").mkdir(parents=True)
    (source / "report.json").write_text('{"screens": []}', encoding="utf-8")
    (source / "qa_process" / "test_cases.md").write_text("# ケース", encoding="utf-8")
    return source


# ─────────────────── 完全アーカイブ ───────────────────


def test_archive_contains_every_source_file(tmp_path: Path) -> None:
    result = create_full_archive(_source(tmp_path), tmp_path / "out", created_at=FIXED)

    with zipfile.ZipFile(result.archive_path) as bundle:
        names = set(bundle.namelist())

    assert "report.json" in names
    assert "qa_process/test_cases.md" in names
    assert result.file_count == 2


def test_archive_does_not_delete_source(tmp_path: Path) -> None:
    """消す判断は保持ポリシー側の責務。二重の削除経路を作らない。"""
    source = _source(tmp_path)

    create_full_archive(source, tmp_path / "out", created_at=FIXED)

    assert (source / "report.json").is_file()
    assert (source / "qa_process" / "test_cases.md").is_file()


def test_manifest_records_checksums(tmp_path: Path) -> None:
    result = create_full_archive(_source(tmp_path), tmp_path / "out", created_at=FIXED)

    with zipfile.ZipFile(result.archive_path) as bundle:
        manifest = json.loads(bundle.read(MANIFEST_NAME).decode("utf-8"))

    assert manifest["summary"]["file_count"] == 2
    assert all(len(entry["sha256"]) == 64 for entry in manifest["files"])
    assert manifest["meta"]["claim_notice"] == CLAIM_NOTICE


def test_verify_passes_for_untouched_archive(tmp_path: Path) -> None:
    result = create_full_archive(_source(tmp_path), tmp_path / "out", created_at=FIXED)

    assert verify_archive(result.archive_path)["ok"] is True


def test_verify_detects_tampered_content(tmp_path: Path) -> None:
    result = create_full_archive(_source(tmp_path), tmp_path / "out", created_at=FIXED)
    tampered = tmp_path / "tampered.zip"

    with zipfile.ZipFile(result.archive_path) as src, zipfile.ZipFile(tampered, "w") as dst:
        for name in src.namelist():
            data = b'{"screens": ["INJECTED"]}' if name == "report.json" else src.read(name)
            dst.writestr(name, data)

    verdict = verify_archive(tampered)

    assert verdict["ok"] is False
    assert verdict["mismatches"][0]["reason"] == "checksum_mismatch"


def test_verify_reports_missing_manifest(tmp_path: Path) -> None:
    path = tmp_path / "bare.zip"
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr("report.json", "{}")

    assert verify_archive(path)["ok"] is False


def test_regenerable_artifacts_are_excluded(tmp_path: Path) -> None:
    source = _source(tmp_path)
    (source / "qa_process" / "playwright-report").mkdir()
    (source / "qa_process" / "playwright-report" / "index.html").write_text("x", encoding="utf-8")

    result = create_full_archive(source, tmp_path / "out", created_at=FIXED)

    with zipfile.ZipFile(result.archive_path) as bundle:
        assert not any("playwright-report" in name for name in bundle.namelist())


def test_missing_source_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        create_full_archive(tmp_path / "absent", tmp_path / "out")


# ─────────────────── sitemap 監視 ───────────────────


def test_sitemap_urls_are_extracted() -> None:
    assert parse_sitemap(SITEMAP) == ["https://e.com/", "https://e.com/help"]


def test_broken_sitemap_yields_empty_without_raising() -> None:
    assert parse_sitemap("<urlset><url>") == []


def test_sitemap_diff_reports_added_and_removed() -> None:
    diff = diff_sitemaps(
        ["https://e.com/", "https://e.com/old"], ["https://e.com/", "https://e.com/new"]
    )

    assert diff.added == ("https://e.com/new",)
    assert diff.removed == ("https://e.com/old",)
    assert diff.unchanged_count == 1
    assert diff.has_changes is True


def test_identical_sitemaps_report_no_changes() -> None:
    diff = diff_sitemaps(["https://e.com/"], ["https://e.com/"])

    assert diff.has_changes is False


# ─────────────────── 文書監視 ───────────────────


def test_replaced_document_is_detected_by_content_hash() -> None:
    before = [fingerprint_document("https://e.com/terms.pdf", b"v1")]
    after = [fingerprint_document("https://e.com/terms.pdf", b"v2")]

    result = diff_documents(before, after)

    assert result["summary"]["replaced"] == 1
    assert result["replaced"][0]["url"] == "https://e.com/terms.pdf"


def test_same_document_is_not_flagged() -> None:
    same = [fingerprint_document("https://e.com/a.pdf", b"same")]

    assert diff_documents(same, list(same))["summary"] == {
        "added": 0,
        "removed": 0,
        "replaced": 0,
    }


def test_added_and_removed_documents_are_listed() -> None:
    before = [fingerprint_document("https://e.com/old.pdf", b"x")]
    after = [fingerprint_document("https://e.com/new.pdf", b"y")]

    result = diff_documents(before, after)

    assert result["added"] == ["https://e.com/new.pdf"]
    assert result["removed"] == ["https://e.com/old.pdf"]


def test_document_diff_declares_claim_scope() -> None:
    result = diff_documents([], [])

    assert result["meta"]["claim_scope"] == "fetched_content_changes_only"
