"""ビューポート間の観測差分。

「PCにはあるがスマホには出ない項目」「モバイル専用の遷移」を、基準ビューポート
との比較として抽出する。差分の計算は既存のドリフト検知エンジン（diff.differ）を
そのまま使い、比較の意味づけだけをここで与える。

主張境界: 出せるのは**観測した画面幅での事実**のみ。片方に無い＝バグ、とは言わない
（レスポンシブ設計として意図的に隠している場合と区別できないため）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from diff.differ import CHANGE_ADDED, CHANGE_REMOVED, compute_diff

if TYPE_CHECKING:
    from crawler.page_crawler import PageData

CLAIM_SCOPE = "observed_viewports_only"

CLAIM_NOTICE = (
    "本書は指定したビューポートで観測した差分の記録であり、"
    "片方に表示されないことが不具合であるとは判定しない。"
)


def compare_viewports(observations: dict[str, list[PageData]], baseline: str) -> dict[str, Any]:
    """ビューポート別の観測結果を、基準ビューポートと突き合わせる。

    observations: ビューポート名 -> そのビューポートで観測した PageData 一覧
    baseline:     基準にするビューポート名（通常は desktop）
    """
    if baseline not in observations:
        raise ValueError(f"基準ビューポート {baseline} の観測結果がありません")

    base_pages = observations[baseline]
    comparisons: list[dict[str, Any]] = []
    for name, pages in observations.items():
        if name == baseline:
            continue
        comparisons.append(_compare_pair(baseline, base_pages, name, pages))

    return {
        "meta": {
            "baseline": baseline,
            "viewports": sorted(observations),
            "claim_scope": CLAIM_SCOPE,
            "claim_notice": CLAIM_NOTICE,
        },
        "summary": _summary(comparisons),
        "comparisons": comparisons,
    }


def _compare_pair(
    base_name: str, base_pages: list[PageData], name: str, pages: list[PageData]
) -> dict[str, Any]:
    """基準→対象の向きで差分を取る。

    compute_diff(old=基準, new=対象) としているので、
    removed = 基準にあって対象に無い（＝対象で見えない）
    added   = 対象にしかない（＝対象専用）
    """
    result = compute_diff(base_pages, pages)

    hidden_pages = [{"url": change.url, "title": change.title} for change in result.removed_pages]
    only_pages = [{"url": change.url, "title": change.title} for change in result.added_pages]
    hidden_fields = [
        {"page_url": change.page_url, "field_name": change.field_name}
        for change in result.field_changes
        if str(change.change_type) == CHANGE_REMOVED
    ]
    only_fields = [
        {"page_url": change.page_url, "field_name": change.field_name}
        for change in result.field_changes
        if str(change.change_type) == CHANGE_ADDED
    ]
    hidden_links = [
        {"page_url": change.page_url, "link": change.link}
        for change in result.link_changes
        if str(change.change_type) == CHANGE_REMOVED
    ]
    only_links = [
        {"page_url": change.page_url, "link": change.link}
        for change in result.link_changes
        if str(change.change_type) == CHANGE_ADDED
    ]

    return {
        "baseline": base_name,
        "viewport": name,
        "hidden_pages": hidden_pages,
        "viewport_only_pages": only_pages,
        "hidden_fields": hidden_fields,
        "viewport_only_fields": only_fields,
        "hidden_links": hidden_links,
        "viewport_only_links": only_links,
        "counts": {
            "hidden_pages": len(hidden_pages),
            "viewport_only_pages": len(only_pages),
            "hidden_fields": len(hidden_fields),
            "viewport_only_fields": len(only_fields),
            "hidden_links": len(hidden_links),
            "viewport_only_links": len(only_links),
        },
    }


def _summary(comparisons: list[dict[str, Any]]) -> dict[str, int]:
    totals = {
        "hidden_pages": 0,
        "viewport_only_pages": 0,
        "hidden_fields": 0,
        "viewport_only_fields": 0,
        "hidden_links": 0,
        "viewport_only_links": 0,
    }
    for comparison in comparisons:
        for key in totals:
            totals[key] += int(comparison["counts"][key])
    return totals


def has_differences(report: dict[str, Any]) -> bool:
    """差分が1件でもあるか（レポートの見出し出し分け用）。"""
    return any(value for value in report.get("summary", {}).values())
