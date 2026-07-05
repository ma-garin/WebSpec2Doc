"""現新比較オーケストレータ（diff.comparison）の単体テスト。

実ブラウザ・実クロールは使わず、crawl_urls をフェイクに差し替えて検証する
（実ブラウザ検証は tests/e2e/test_comparison_e2e.py で行う）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from analyzer.html_analyzer import analyze_pages
from crawler.page_crawler import FieldData, FormData, PageData
from diff import comparison as comparison_module
from diff.comparison import (
    CATEGORY_INCOMPREHENSIBLE,
    CATEGORY_INOPERABLE,
    CATEGORY_LAYOUT_BROKEN,
    CATEGORY_TEXT_GARBLED,
    CATEGORY_UNCLASSIFIED,
    ComparisonError,
    _classify_pair,
    run_old_new_comparison,
)
from diff.differ import SEVERITY_BREAKING, compare_page_pair
from diff.pair_matcher import ScreenPair
from diff.screenshot_diff import ScreenshotDiff


def _page(
    url: str,
    title: str,
    headings: tuple[str, ...] = ("見出し",),
    fields: tuple[FieldData, ...] = (),
    links: tuple[str, ...] = (),
    a11y_issues: tuple[str, ...] = (),
    screenshot_path: str | None = "/tmp/shot.png",
) -> PageData:
    forms = (FormData(action="/submit", method="post", fields=fields),) if fields else ()
    return PageData(
        url=url,
        title=title,
        headings=headings,
        links=links,
        forms=forms,
        screenshot_path=screenshot_path,
        a11y_issues=a11y_issues,
    )


def _pair(old_page_id: str = "P001", new_page_id: str = "P001") -> ScreenPair:
    return ScreenPair(old_page_id=old_page_id, new_page_id=new_page_id, score=1.0, method="path")


class TestClassifyPair:
    def test_required_loss_is_breaking_inoperable(self) -> None:
        """required 消失は breaking かつ「操作不可」に分類される（AC-3・AC-6）。"""
        old_field = FieldData("email", "email", "", required=True)
        new_field = FieldData("email", "email", "", required=False)
        old_page_data = _page("https://old.example.com/contact", "Contact", fields=(old_field,))
        new_page_data = _page("https://new.example.com/contact", "Contact", fields=(new_field,))
        old_page = analyze_pages([old_page_data])[0]
        new_page = analyze_pages([new_page_data])[0]
        pair = _pair(old_page.page_id, new_page.page_id)
        diff_result = compare_page_pair(old_page.page_data, new_page.page_data)

        findings = _classify_pair(pair, diff_result, old_page, new_page, screenshot_diff=None)

        inoperable = [f for f in findings if f.category == CATEGORY_INOPERABLE]
        assert len(inoperable) == 1
        assert inoperable[0].severity == SEVERITY_BREAKING
        assert inoperable[0].confidence == 1.0
        assert inoperable[0].old_evidence is not None
        assert inoperable[0].new_evidence is not None

    def test_garbled_title_classified(self) -> None:
        """title に U+FFFD があれば text_garbled に分類される（AC-6）。"""
        old_page_data = _page("https://old.example.com/products", "商品一覧")
        new_page_data = _page("https://new.example.com/products", "商品�覧")
        old_page = analyze_pages([old_page_data])[0]
        new_page = analyze_pages([new_page_data])[0]
        pair = _pair(old_page.page_id, new_page.page_id)
        diff_result = compare_page_pair(old_page.page_data, new_page.page_data)

        findings = _classify_pair(pair, diff_result, old_page, new_page, screenshot_diff=None)

        garbled = [f for f in findings if f.category == CATEGORY_TEXT_GARBLED]
        assert len(garbled) == 1
        assert "商品�覧" in garbled[0].detail

    def test_visible_label_loss_is_incomprehensible(self) -> None:
        """可視ラベルの消失は「理解不可能」に分類される（5-3 節）。"""
        old_field = FieldData("text", "name", "", required=False, has_visible_label=True)
        new_field = FieldData("text", "name", "", required=False, has_visible_label=False)
        old_page_data = _page("https://old.example.com/form", "Form", fields=(old_field,))
        new_page_data = _page("https://new.example.com/form", "Form", fields=(new_field,))
        old_page = analyze_pages([old_page_data])[0]
        new_page = analyze_pages([new_page_data])[0]
        pair = _pair(old_page.page_id, new_page.page_id)
        diff_result = compare_page_pair(old_page.page_data, new_page.page_data)

        findings = _classify_pair(pair, diff_result, old_page, new_page, screenshot_diff=None)

        incomprehensible = [f for f in findings if f.category == CATEGORY_INCOMPREHENSIBLE]
        assert any("可視ラベルが消失" in f.detail for f in incomprehensible)

    def test_a11y_issue_increase_is_incomprehensible(self) -> None:
        """a11y_issues が増加すると「理解不可能」に分類される（5-3 節）。"""
        old_page_data = _page("https://old.example.com/form", "Form", a11y_issues=())
        new_page_data = _page("https://new.example.com/form", "Form", a11y_issues=("missing-alt",))
        old_page = analyze_pages([old_page_data])[0]
        new_page = analyze_pages([new_page_data])[0]
        pair = _pair(old_page.page_id, new_page.page_id)
        diff_result = compare_page_pair(old_page.page_data, new_page.page_data)

        findings = _classify_pair(pair, diff_result, old_page, new_page, screenshot_diff=None)

        assert any(f.category == CATEGORY_INCOMPREHENSIBLE for f in findings)

    def test_layout_broken_when_significant_diff_without_spec_diff(self) -> None:
        """仕様差分なし・画像差分ありは「表示崩れ」に分類される（5-3 節）。"""
        old_page_data = _page("https://old.example.com/top", "Top")
        new_page_data = _page("https://new.example.com/top", "Top")
        old_page = analyze_pages([old_page_data])[0]
        new_page = analyze_pages([new_page_data])[0]
        pair = _pair(old_page.page_id, new_page.page_id)
        diff_result = compare_page_pair(old_page.page_data, new_page.page_data)
        screenshot_diff = ScreenshotDiff(
            page_id=pair.old_page_id,
            before_path="old.png",
            after_path="new.png",
            diff_ratio=0.5,
            is_significant=True,
        )

        findings = _classify_pair(pair, diff_result, old_page, new_page, screenshot_diff)

        assert len(findings) == 1
        assert findings[0].category == CATEGORY_LAYOUT_BROKEN

    def test_unclassified_for_uncovered_attribute_diff(self) -> None:
        """breaking でない属性差分（maxlength 等）は unclassified として明示される。"""
        old_field = FieldData("text", "message", "", required=True, maxlength=500)
        new_field = FieldData("text", "message", "", required=True, maxlength=100)
        old_page_data = _page("https://old.example.com/contact", "Contact", fields=(old_field,))
        new_page_data = _page("https://new.example.com/contact", "Contact", fields=(new_field,))
        old_page = analyze_pages([old_page_data])[0]
        new_page = analyze_pages([new_page_data])[0]
        pair = _pair(old_page.page_id, new_page.page_id)
        diff_result = compare_page_pair(old_page.page_data, new_page.page_data)

        findings = _classify_pair(pair, diff_result, old_page, new_page, screenshot_diff=None)

        assert any(f.category == CATEGORY_UNCLASSIFIED for f in findings)
        unclassified = [f for f in findings if f.category == CATEGORY_UNCLASSIFIED]
        assert "要人手確認" in unclassified[0].detail

    def test_no_diff_produces_no_findings(self) -> None:
        """差分がなければ指摘は 0 件（過剰検出しない）。"""
        old_page_data = _page("https://old.example.com/top", "Top")
        new_page_data = _page("https://new.example.com/top", "Top")
        old_page = analyze_pages([old_page_data])[0]
        new_page = analyze_pages([new_page_data])[0]
        pair = _pair(old_page.page_id, new_page.page_id)
        diff_result = compare_page_pair(old_page.page_data, new_page.page_data)

        findings = _classify_pair(pair, diff_result, old_page, new_page, screenshot_diff=None)

        assert findings == []

    def test_sibling_nonbreaking_diff_not_suppressed_by_breaking_diff(self) -> None:
        """同じ項目に breaking な属性差分（required）と非 breaking な差分（maxlength）が
        同居しても、後者が握り潰されず unclassified として報告される（回帰）。"""
        # message: required True→False（breaking）かつ maxlength 500→100（非 breaking）
        old_field = FieldData("text", "message", "", required=True, maxlength=500)
        new_field = FieldData("text", "message", "", required=False, maxlength=100)
        old_page_data = _page("https://old.example.com/contact", "Contact", fields=(old_field,))
        new_page_data = _page("https://new.example.com/contact", "Contact", fields=(new_field,))
        old_page = analyze_pages([old_page_data])[0]
        new_page = analyze_pages([new_page_data])[0]
        pair = _pair(old_page.page_id, new_page.page_id)
        diff_result = compare_page_pair(old_page.page_data, new_page.page_data)

        findings = _classify_pair(pair, diff_result, old_page, new_page, screenshot_diff=None)

        # required の breaking 指摘（操作不可）が出る
        assert any(f.category == CATEGORY_INOPERABLE for f in findings)
        # maxlength の非 breaking 差分が unclassified として残る（消えない）
        unclassified = [f for f in findings if f.category == CATEGORY_UNCLASSIFIED]
        assert any("maxlength" in f.detail for f in unclassified), [f.detail for f in findings]


class TestRunOldNewComparison:
    def test_raises_comparison_error_when_one_side_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """片側クロールが 0 件なら比較を中止しエラー終了する（部分レポートを出さない・5-4 節）。"""

        def fake_crawl_urls(urls: list[str], **kwargs: object) -> list[PageData]:
            if "old" in str(kwargs.get("output_dir")):
                return []
            return [_page(urls[0], "Something")]

        monkeypatch.setattr(comparison_module, "crawl_urls", fake_crawl_urls)

        with pytest.raises(ComparisonError):
            run_old_new_comparison(
                ["https://old.example.com/"],
                ["https://new.example.com/"],
                tmp_path,
            )

    def test_end_to_end_with_faked_crawl_and_links(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """2 クロール（フェイク）→対応付け→仕様差分→リンク切れ検査までの一連の流れを検証する。"""
        old_field = FieldData("email", "email", "", required=True)
        new_field = FieldData("email", "email", "", required=False)

        def fake_crawl_urls(urls: list[str], **kwargs: object) -> list[PageData]:
            output_dir = str(kwargs.get("output_dir"))
            if output_dir.endswith("old"):
                return [
                    _page(
                        "https://old.example.com/contact",
                        "お問い合わせ",
                        fields=(old_field,),
                        links=("https://new.example.com/missing",),
                        screenshot_path=None,
                    )
                ]
            return [
                _page(
                    "https://new.example.com/contact",
                    "お問い合わせ",
                    fields=(new_field,),
                    links=("https://new.example.com/missing",),
                    screenshot_path=None,
                )
            ]

        monkeypatch.setattr(comparison_module, "crawl_urls", fake_crawl_urls)

        def fake_link_opener(url: str, timeout_sec: float) -> int:
            return 404

        result = run_old_new_comparison(
            ["https://old.example.com/contact"],
            ["https://new.example.com/contact"],
            tmp_path,
            link_opener=fake_link_opener,
        )

        assert len(result.pairs) == 1
        assert result.added_page_ids == ()
        assert result.removed_page_ids == ()
        assert any(
            f.category == CATEGORY_INOPERABLE and "リンク切れ" in f.detail for f in result.findings
        )
        assert any(
            f.category == CATEGORY_INOPERABLE and "必須属性" in f.detail for f in result.findings
        )
        # 画像未取得（screenshot_path=None）のペアは「未確認」として明示され、
        # 比較済み・問題なしと区別できる（黙って握り潰さない・evidence-only）
        assert any("視覚比較を実施できませんでした（未確認）" in f.detail for f in result.findings)


class TestReportJsonUnchangedWithoutCompare:
    def test_normal_crawl_dispatch_does_not_invoke_comparison(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """現新比較モードのフラグ未指定時は、既存クロール経路のみが呼ばれる（AC-7）。

        比較モードは別ファイル（comparison.json/html）にしか出力しないため、
        本テストでは main.run() のディスパッチ自体が既存経路に来ることのみを確認する
        （report.json の生成自体は既存テスト群で担保済み）。
        """
        import argparse

        import main as main_module

        called = {"crawl": False, "comparison": False}

        def fake_run_crawl(args: argparse.Namespace, auth_path: object) -> None:
            called["crawl"] = True

        def fake_run_comparison(args: argparse.Namespace) -> None:
            called["comparison"] = True

        monkeypatch.setattr(main_module, "_run_crawl", fake_run_crawl)
        monkeypatch.setattr(main_module, "_run_old_new_comparison", fake_run_comparison)

        args = argparse.Namespace(
            url="https://example.com/",
            urls=None,
            login=None,
            login_signal=None,
            login_simple=False,
            login_scrape=None,
            login_submit=False,
            auth=None,
            discover=False,
            record_session=False,
            exploration_coverage=False,
            reverse_assets=False,
            compare_old_urls=None,
            compare_new_urls=None,
        )

        main_module.run(args)

        assert called["crawl"] is True
        assert called["comparison"] is False

    def test_both_compare_urls_dispatch_to_comparison(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--compare-old-urls / --compare-new-urls 両方指定時は比較モードに分岐する。"""
        import argparse

        import main as main_module

        called = {"crawl": False, "comparison": False}

        def fake_run_crawl(args: argparse.Namespace, auth_path: object) -> None:
            called["crawl"] = True

        def fake_run_comparison(args: argparse.Namespace) -> None:
            called["comparison"] = True

        monkeypatch.setattr(main_module, "_run_crawl", fake_run_crawl)
        monkeypatch.setattr(main_module, "_run_old_new_comparison", fake_run_comparison)

        args = argparse.Namespace(
            url=None,
            urls=None,
            login=None,
            login_signal=None,
            login_simple=False,
            login_scrape=None,
            login_submit=False,
            auth=None,
            discover=False,
            record_session=False,
            exploration_coverage=False,
            reverse_assets=False,
            compare_old_urls="https://old.example.com/",
            compare_new_urls="https://new.example.com/",
        )

        main_module.run(args)

        assert called["comparison"] is True
        assert called["crawl"] is False
