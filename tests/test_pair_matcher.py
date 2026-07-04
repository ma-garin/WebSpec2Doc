"""現新比較の画面対応付け（pair_matcher）の単体テスト。"""

from __future__ import annotations

from analyzer.html_analyzer import analyze_pages
from crawler.page_crawler import PageData
from diff.pair_matcher import match_page_pairs


def _page(url: str, title: str, headings: tuple[str, ...] = ()) -> PageData:
    return PageData(
        url=url,
        title=title,
        headings=headings,
        links=(),
        forms=(),
        screenshot_path=None,
    )


def test_pair_match_by_path() -> None:
    """同一パス・別ドメインの 2 ページは score=1.0, method='path' で対応付く（AC-2）。"""
    old_pages = analyze_pages([_page("https://old.example.com/contact", "お問い合わせ（現行）")])
    new_pages = analyze_pages([_page("https://new.example.com/contact", "お問い合わせ（新）")])

    pairs, removed, added = match_page_pairs(old_pages, new_pages)

    assert len(pairs) == 1
    assert pairs[0].old_page_id == old_pages[0].page_id
    assert pairs[0].new_page_id == new_pages[0].page_id
    assert pairs[0].score == 1.0
    assert pairs[0].method == "path"
    assert removed == []
    assert added == []


def test_pair_match_by_title_similarity() -> None:
    """パスが異なっても名称が高い類似度なら対応付く（method='title'）。"""
    old_pages = analyze_pages([_page("https://old.example.com/inquiry", "お問い合わせフォーム")])
    new_pages = analyze_pages([_page("https://new.example.com/contact-us", "お問い合わせフォーム")])

    pairs, removed, added = match_page_pairs(old_pages, new_pages)

    assert len(pairs) == 1
    assert pairs[0].method == "title"
    assert pairs[0].score == 1.0
    assert removed == []
    assert added == []


def test_pair_match_unmatched_reported() -> None:
    """片側にしかない画面は added/removed に載る（AC-2）。"""
    old_pages = analyze_pages(
        [
            _page("https://old.example.com/contact", "お問い合わせ"),
            _page("https://old.example.com/legacy-only", "廃止予定画面"),
        ]
    )
    new_pages = analyze_pages(
        [
            _page("https://new.example.com/contact", "お問い合わせ"),
            _page("https://new.example.com/new-feature", "新機能画面"),
        ]
    )

    pairs, removed, added = match_page_pairs(old_pages, new_pages)

    assert len(pairs) == 1
    assert removed == [old_pages[1].page_id]
    assert added == [new_pages[1].page_id]


def test_pair_match_no_candidates_returns_all_unmatched() -> None:
    """類似度が閾値未満なら 1 組も対応しない（pairs=() で完走。5-4 節）。"""
    old_pages = analyze_pages([_page("https://old.example.com/a", "アルファ")])
    new_pages = analyze_pages([_page("https://new.example.com/z", "全く違う画面名")])

    pairs, removed, added = match_page_pairs(old_pages, new_pages)

    assert pairs == []
    assert removed == [old_pages[0].page_id]
    assert added == [new_pages[0].page_id]


def test_pair_match_greedy_prefers_higher_score() -> None:
    """複数候補がある場合、スコアの高い組み合わせが優先される（貪欲法）。"""
    old_pages = analyze_pages(
        [
            _page("https://old.example.com/x", "商品一覧ページ"),
        ]
    )
    new_pages = analyze_pages(
        [
            _page("https://new.example.com/products-list", "商品一覧ページ"),
            _page("https://new.example.com/other", "商品一覧ページ（別)"),
        ]
    )

    pairs, _removed, added = match_page_pairs(old_pages, new_pages)

    assert len(pairs) == 1
    # 完全一致の方が高スコアなので、そちらと対応付き、もう一方は added に残る
    assert pairs[0].new_page_id == new_pages[0].page_id
    assert new_pages[1].page_id in added
