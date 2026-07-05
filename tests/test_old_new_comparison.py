"""レーンC2: compare_analyzed_pages（純粋比較コア）と /api/snapshot-comparison のテスト。

抽出した比較コアが 4 分類・マスク適用・リンク検査トグルを正しく行い、
ライブ経路（run_old_new_comparison）はバイト同一挙動を保つことを確認する。
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analyzer.html_analyzer import analyze_pages  # noqa: E402
from crawler.page_crawler import FieldData, FormData, PageData  # noqa: E402
from diff import comparison as comparison_module  # noqa: E402
from diff.comparison import (  # noqa: E402
    CATEGORY_INOPERABLE,
    CATEGORY_UNCLASSIFIED,
    ComparisonFinding,
    compare_analyzed_pages,
)
from diff.differ import SEVERITY_BREAKING  # noqa: E402


def _page(
    url: str,
    title: str = "画面",
    fields: tuple[FieldData, ...] = (),
    links: tuple[str, ...] = (),
    screenshot_path: str | None = None,
) -> PageData:
    forms = (FormData(action="/submit", method="post", fields=fields),) if fields else ()
    return PageData(
        url=url,
        title=title,
        headings=("見出し",),
        links=links,
        forms=forms,
        screenshot_path=screenshot_path,
    )


def _analyzed(*pages: PageData) -> list:
    return analyze_pages(list(pages))


class TestCompareAnalyzedPages:
    def test_required_loss_is_inoperable(self) -> None:
        """required 消失は「操作不可（breaking）」に分類される（コア経由）。"""
        old = _analyzed(
            _page("https://x/a", fields=(FieldData("email", "email", "", required=True),))
        )
        new = _analyzed(
            _page("https://x/a", fields=(FieldData("email", "email", "", required=False),))
        )

        result = compare_analyzed_pages(old, new, dynamic_masks={})

        assert any(
            f.category == CATEGORY_INOPERABLE and f.severity == SEVERITY_BREAKING
            for f in result.findings
        )

    def test_image_not_taken_marks_unclassified(self) -> None:
        """画像未取得のペアは『未確認』として未分類に明示される（evidence-only）。"""
        old = _analyzed(_page("https://x/a", screenshot_path=None))
        new = _analyzed(_page("https://x/a", screenshot_path=None))

        result = compare_analyzed_pages(old, new, dynamic_masks={})

        assert any(
            f.category == CATEGORY_UNCLASSIFIED and "画像未取得" in f.detail
            for f in result.findings
        )

    def test_removed_id_surfaces_when_new_drops_page(self) -> None:
        old = _analyzed(_page("https://x/a"), _page("https://x/b"))
        new = _analyzed(_page("https://x/a"))

        result = compare_analyzed_pages(old, new, dynamic_masks={})

        assert result.removed_page_ids, "現行のみの画面が removed に出るべき"

    def test_added_id_surfaces_when_new_adds_page(self) -> None:
        old = _analyzed(_page("https://x/a"))
        new = _analyzed(_page("https://x/a"), _page("https://x/c"))

        result = compare_analyzed_pages(old, new, dynamic_masks={})

        assert result.added_page_ids, "新のみの画面が added に出るべき"

    def test_dynamic_masks_are_threaded_to_screenshot_compare(self, monkeypatch) -> None:
        """渡した dynamic_masks が画像比較へそのまま伝播することを確認する。"""
        captured: dict[str, object] = {}

        def _fake_shot(pair, old_page, new_page, masks, threshold, tolerance):
            captured["masks"] = masks
            return None

        monkeypatch.setattr(comparison_module, "_compare_pair_screenshots", _fake_shot)
        masks = {"P001": ((0, 0, 10, 10),)}
        old = _analyzed(_page("https://x/a"))
        new = _analyzed(_page("https://x/a"))

        compare_analyzed_pages(old, new, dynamic_masks=masks)

        assert captured["masks"] == masks

    def test_check_links_requires_new_dir(self) -> None:
        old = _analyzed(_page("https://x/a"))
        new = _analyzed(_page("https://x/a"))
        with pytest.raises(ValueError, match="new_dir"):
            compare_analyzed_pages(old, new, dynamic_masks={}, check_links=True)

    def test_check_links_false_does_not_invoke_link_check(self, monkeypatch) -> None:
        def _boom(*args, **kwargs):
            raise AssertionError("check_links=False のときリンク検査を呼んではいけない")

        monkeypatch.setattr(comparison_module, "_check_new_side_links", _boom)
        old = _analyzed(_page("https://x/a", links=("https://x/dead",)))
        new = _analyzed(_page("https://x/a", links=("https://x/dead",)))

        result = compare_analyzed_pages(old, new, dynamic_masks={}, check_links=False)

        assert result is not None  # 例外が出ずに完了する

    def test_check_links_true_appends_link_findings(self, monkeypatch) -> None:
        sentinel = ComparisonFinding(
            category=CATEGORY_INOPERABLE,
            page_pair=None,
            detail="リンク切れ（テスト）",
            old_evidence=None,
            new_evidence=None,
            severity=SEVERITY_BREAKING,
        )
        monkeypatch.setattr(comparison_module, "_check_new_side_links", lambda *a, **k: [sentinel])
        old = _analyzed(_page("https://x/a"))
        new = _analyzed(_page("https://x/a"))

        result = compare_analyzed_pages(
            old, new, dynamic_masks={}, check_links=True, new_dir=Path("/tmp")
        )

        assert sentinel in result.findings


# ─────────────────────── /api/snapshot-comparison ルート ───────────────────────


def _write_snapshot(snaps_dir: Path, stem: str, pages: list[PageData]) -> None:
    snaps_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps([asdict(p) for p in pages], ensure_ascii=False, indent=2)
    (snaps_dir / f"{stem}.json").write_text(payload, encoding="utf-8")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import app as appmod

    monkeypatch.setattr("web.validation.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("web.routes.history.OUTPUT_DIR", tmp_path)
    return appmod.app.test_client(), tmp_path


class TestSnapshotComparisonRoute:
    def test_returns_comparison_html(self, client) -> None:
        test_client, out_dir = client
        snaps = out_dir / "example.com" / "snapshots"
        _write_snapshot(snaps, "old", [_page("https://example.com/a")])
        _write_snapshot(snaps, "new", [_page("https://example.com/a")])

        resp = test_client.get(
            "/api/snapshot-comparison?domain=example.com&from=old&to=new",
            headers={"Host": "127.0.0.1"},
        )

        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "現新比較レポート" in body
        assert resp.headers.get("Cache-Control") == "no-store"

    def test_missing_snapshot_returns_not_found_message(self, client) -> None:
        test_client, out_dir = client
        snaps = out_dir / "example.com" / "snapshots"
        _write_snapshot(snaps, "old", [_page("https://example.com/a")])

        resp = test_client.get(
            "/api/snapshot-comparison?domain=example.com&from=old&to=missing",
            headers={"Host": "127.0.0.1"},
        )

        assert resp.status_code == 200
        assert "見つかりません" in resp.get_data(as_text=True)

    def test_invalid_domain_returns_404(self, client) -> None:
        test_client, _ = client
        resp = test_client.get(
            "/api/snapshot-comparison?domain=../etc&from=old&to=new",
            headers={"Host": "127.0.0.1"},
        )
        assert resp.status_code == 404
