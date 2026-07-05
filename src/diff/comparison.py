"""現新比較モードのオーケストレータ（2 クロール→対応付け→三層比較→4 分類）。

OS 移行・リプレイス時の検証を自動化する。現行 URL と新 URL のペアを 2 ターゲット
クロールし、画面を対応付けて仕様差分・画像差分・リンク切れの三層比較を行い、
想定不具合 4 分類（表示崩れ/文字化け・意味消失/理解不可能/操作不可）で報告する。
分類できない差分は「未分類（要確認）」と明示し、無理に断定しない（evidence-only 原則）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from analyzer.html_analyzer import AnalyzedPage, analyze_pages
from crawler.page_crawler import (
    CheckpointCallback,
    CrawlEventCallback,
    SourceEvidence,
    StopRequested,
    crawl_urls,
)
from crawler.politeness import OriginRateLimiter, crawl_interval_from_env
from diff.differ import (
    SEVERITY_BREAKING,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    DiffResult,
    compare_page_pair,
)
from diff.link_checker import STATUS_BROKEN, STATUS_UNCONFIRMED, LinkOpener, check_links
from diff.pair_matcher import ScreenPair, match_page_pairs
from diff.screenshot_diff import (
    ScreenshotDiff,
    channel_tolerance_from_env,
    compare_screenshots_masked,
    detect_dynamic_regions,
    threshold_from_env,
)

logger = logging.getLogger(__name__)

CATEGORY_LAYOUT_BROKEN = "layout_broken"
CATEGORY_TEXT_GARBLED = "text_garbled"
CATEGORY_INCOMPREHENSIBLE = "incomprehensible"
CATEGORY_INOPERABLE = "inoperable"
CATEGORY_UNCLASSIFIED = "unclassified"

DYNAMIC_MASKS_FILE_NAME = "dynamic_masks.json"
_GARBLED_CHAR = "�"  # U+FFFD REPLACEMENT CHARACTER（文字化けの典型痕跡）
_DYNAMIC_REGION_INTERVAL_SEC = 1.0


class ComparisonError(RuntimeError):
    """現新比較を中止すべきエラー（片側クロールが 0 件など）。"""


@dataclass(frozen=True)
class ComparisonFinding:
    """1 指摘。category は不具合 4 分類 + "unclassified"。"""

    category: str
    page_pair: ScreenPair | None
    detail: str
    old_evidence: SourceEvidence | None
    new_evidence: SourceEvidence | None
    severity: str
    confidence: float = 1.0  # 実測由来は 1.0 固定（evidence-only 原則）


@dataclass(frozen=True)
class ComparisonResult:
    pairs: tuple[ScreenPair, ...]
    added_page_ids: tuple[str, ...]  # 新のみ
    removed_page_ids: tuple[str, ...]  # 現行のみ
    findings: tuple[ComparisonFinding, ...]
    screenshot_diffs: tuple[ScreenshotDiff, ...]


def run_old_new_comparison(
    old_urls: list[str],
    new_urls: list[str],
    output_dir: Path,
    auth_old: Path | None = None,
    auth_new: Path | None = None,
    mask_selectors: tuple[str, ...] = (),
    on_event: CrawlEventCallback | None = None,
    on_checkpoint: CheckpointCallback | None = None,
    stop_requested: StopRequested | None = None,
    link_opener: LinkOpener | None = None,
) -> ComparisonResult:
    """現新比較の一連の処理（2 クロール→対応付け→三層比較→4 分類）を実行する。"""
    old_dir = output_dir / "old"
    new_dir = output_dir / "new"

    old_pages = crawl_urls(
        old_urls,
        output_dir=old_dir,
        auth_state=auth_old,
        on_event=on_event,
        on_checkpoint=on_checkpoint,
        stop_requested=stop_requested,
    )
    new_pages = crawl_urls(
        new_urls,
        output_dir=new_dir,
        auth_state=auth_new,
        on_event=on_event,
        on_checkpoint=on_checkpoint,
        stop_requested=stop_requested,
    )
    if not old_pages or not new_pages:
        raise ComparisonError("現行/新の取得に失敗しました")

    old_analyzed = analyze_pages(old_pages)
    new_analyzed = analyze_pages(new_pages)
    pairs, removed_ids, added_ids = match_page_pairs(old_analyzed, new_analyzed)

    dynamic_masks = _collect_masks(old_analyzed, auth_old, mask_selectors, old_dir)

    old_by_id = {p.page_id: p for p in old_analyzed}
    new_by_id = {p.page_id: p for p in new_analyzed}

    findings: list[ComparisonFinding] = []
    screenshot_diffs: list[ScreenshotDiff] = []
    threshold = threshold_from_env()
    tolerance = channel_tolerance_from_env()

    for pair in pairs:
        old_page = old_by_id[pair.old_page_id]
        new_page = new_by_id[pair.new_page_id]
        diff_result = compare_page_pair(old_page.page_data, new_page.page_data)

        screenshot_diff = _compare_pair_screenshots(
            pair, old_page, new_page, dynamic_masks, threshold, tolerance
        )
        if screenshot_diff is not None:
            screenshot_diffs.append(screenshot_diff)
        else:
            # 画像未取得で視覚比較を実施できなかったことを「未確認」として明示する。
            # 黙って握り潰すと、比較済みで問題なしのペアと区別できず、
            # 検証していない安全性を暗黙に主張してしまう（evidence-only）。
            findings.append(
                ComparisonFinding(
                    category=CATEGORY_UNCLASSIFIED,
                    page_pair=pair,
                    detail="画像未取得のため視覚比較を実施できませんでした（未確認）",
                    old_evidence=_page_evidence(old_page),
                    new_evidence=_page_evidence(new_page),
                    severity=SEVERITY_INFO,
                )
            )

        findings.extend(_classify_pair(pair, diff_result, old_page, new_page, screenshot_diff))

    link_findings = _check_new_side_links(new_analyzed, pairs, new_dir, link_opener)
    findings.extend(link_findings)

    return ComparisonResult(
        pairs=tuple(pairs),
        added_page_ids=tuple(added_ids),
        removed_page_ids=tuple(removed_ids),
        findings=tuple(findings),
        screenshot_diffs=tuple(screenshot_diffs),
    )


# ─────────────────────── 画面ペア単位の三層比較 ───────────────────────


def _compare_pair_screenshots(
    pair: ScreenPair,
    old_page: AnalyzedPage,
    new_page: AnalyzedPage,
    dynamic_masks: dict[str, tuple[tuple[int, int, int, int], ...]],
    threshold: float,
    tolerance: int,
) -> ScreenshotDiff | None:
    old_shot = old_page.page_data.screenshot_path
    new_shot = new_page.page_data.screenshot_path
    if not old_shot or not new_shot:
        logger.info("画像未取得のため画像差分をスキップします: old=%s new=%s", old_shot, new_shot)
        return None
    masks = dynamic_masks.get(pair.old_page_id, ())
    return compare_screenshots_masked(
        Path(old_shot),
        Path(new_shot),
        page_id=pair.old_page_id,
        threshold=threshold,
        masks=masks,
        channel_tolerance=tolerance,
    )


def _field_evidence_maps(
    diff_result: DiffResult,
) -> tuple[dict[str, SourceEvidence | None], dict[str, SourceEvidence | None]]:
    old_map: dict[str, SourceEvidence | None] = {}
    new_map: dict[str, SourceEvidence | None] = {}
    for change in diff_result.field_changes:
        if change.before is not None:
            old_map[change.field_name] = change.before.evidence
        if change.after is not None:
            new_map[change.field_name] = change.after.evidence
    return old_map, new_map


def _page_evidence(page: AnalyzedPage) -> SourceEvidence:
    return SourceEvidence(selector="", screenshot_path=page.page_data.screenshot_path)


def _classify_pair(
    pair: ScreenPair,
    diff_result: DiffResult,
    old_page: AnalyzedPage,
    new_page: AnalyzedPage,
    screenshot_diff: ScreenshotDiff | None,
) -> list[ComparisonFinding]:
    """§5-3 のルールベース分類を 1 画面ペアに適用する。"""
    findings: list[ComparisonFinding] = []
    old_default_evidence = _page_evidence(old_page)
    new_default_evidence = _page_evidence(new_page)
    old_field_evidence, new_field_evidence = _field_evidence_maps(diff_result)

    # (field_name, attribute) で覆済みを記録する。field_name だけで記録すると、
    # 同じ項目に breaking な属性差分と非 breaking な属性差分が同居した場合に、
    # 後者が _detect_unclassified で誤って握り潰され差分が報告されなくなる。
    covered_attributes: set[tuple[str, str]] = set()
    for attr_diff in diff_result.attribute_diffs:
        if attr_diff.severity != SEVERITY_BREAKING:
            continue
        covered_attributes.add((attr_diff.field_name, attr_diff.attribute))
        findings.append(
            ComparisonFinding(
                category=CATEGORY_INOPERABLE,
                page_pair=pair,
                detail=(
                    f"必須属性が変化しました: {attr_diff.field_name}.{attr_diff.attribute}"
                    f"（{attr_diff.before} → {attr_diff.after}）"
                ),
                old_evidence=old_field_evidence.get(attr_diff.field_name) or old_default_evidence,
                new_evidence=new_field_evidence.get(attr_diff.field_name) or new_default_evidence,
                severity=SEVERITY_BREAKING,
            )
        )

    findings.extend(
        _detect_incomprehensible(
            pair, old_page, new_page, old_default_evidence, new_default_evidence
        )
    )
    findings.extend(
        _detect_text_garbled(pair, old_page, new_page, old_default_evidence, new_default_evidence)
    )

    has_spec_diff = diff_result.has_changes
    if screenshot_diff is not None and screenshot_diff.is_significant and not has_spec_diff:
        findings.append(
            ComparisonFinding(
                category=CATEGORY_LAYOUT_BROKEN,
                page_pair=pair,
                detail=(
                    "画像差分が有意ですが仕様差分は検出されていません"
                    f"（diff_ratio={screenshot_diff.diff_ratio:.3f}）"
                ),
                old_evidence=old_default_evidence,
                new_evidence=new_default_evidence,
                severity=SEVERITY_WARNING,
            )
        )

    findings.extend(
        _detect_unclassified(
            pair,
            diff_result,
            covered_attributes,
            old_default_evidence,
            new_default_evidence,
        )
    )
    return findings


def _detect_incomprehensible(
    pair: ScreenPair,
    old_page: AnalyzedPage,
    new_page: AnalyzedPage,
    old_default_evidence: SourceEvidence,
    new_default_evidence: SourceEvidence,
) -> list[ComparisonFinding]:
    findings: list[ComparisonFinding] = []
    old_fields = {f.name: f for form in old_page.page_data.forms for f in form.fields}
    new_fields = {f.name: f for form in new_page.page_data.forms for f in form.fields}
    for name, old_field in old_fields.items():
        new_field = new_fields.get(name)
        if new_field is None:
            continue
        if old_field.has_visible_label and not new_field.has_visible_label:
            findings.append(
                ComparisonFinding(
                    category=CATEGORY_INCOMPREHENSIBLE,
                    page_pair=pair,
                    detail=f"可視ラベルが消失しました: {name}",
                    old_evidence=old_field.evidence or old_default_evidence,
                    new_evidence=new_field.evidence or new_default_evidence,
                    severity=SEVERITY_BREAKING,
                )
            )
        if old_field.aria_label and not new_field.aria_label:
            findings.append(
                ComparisonFinding(
                    category=CATEGORY_INCOMPREHENSIBLE,
                    page_pair=pair,
                    detail=f"aria-label が消失しました: {name}",
                    old_evidence=old_field.evidence or old_default_evidence,
                    new_evidence=new_field.evidence or new_default_evidence,
                    severity=SEVERITY_WARNING,
                )
            )

    old_issues = set(old_page.page_data.a11y_issues)
    new_issues = set(new_page.page_data.a11y_issues)
    added_issues = new_issues - old_issues
    if added_issues:
        findings.append(
            ComparisonFinding(
                category=CATEGORY_INCOMPREHENSIBLE,
                page_pair=pair,
                detail=f"アクセシビリティ課題が増加しました: {', '.join(sorted(added_issues))}",
                old_evidence=old_default_evidence,
                new_evidence=new_default_evidence,
                severity=SEVERITY_WARNING,
            )
        )
    return findings


def _has_garbled_text(text: str) -> bool:
    return _GARBLED_CHAR in text


def _detect_text_garbled(
    pair: ScreenPair,
    old_page: AnalyzedPage,
    new_page: AnalyzedPage,
    old_default_evidence: SourceEvidence,
    new_default_evidence: SourceEvidence,
) -> list[ComparisonFinding]:
    findings: list[ComparisonFinding] = []
    if _has_garbled_text(new_page.page_data.title):
        findings.append(
            ComparisonFinding(
                category=CATEGORY_TEXT_GARBLED,
                page_pair=pair,
                detail=f"タイトルに文字化けを検出しました: {new_page.page_data.title!r}",
                old_evidence=old_default_evidence,
                new_evidence=new_default_evidence,
                severity=SEVERITY_WARNING,
            )
        )
    for heading in new_page.page_data.headings:
        if _has_garbled_text(heading):
            findings.append(
                ComparisonFinding(
                    category=CATEGORY_TEXT_GARBLED,
                    page_pair=pair,
                    detail=f"見出しに文字化けを検出しました: {heading!r}",
                    old_evidence=old_default_evidence,
                    new_evidence=new_default_evidence,
                    severity=SEVERITY_WARNING,
                )
            )

    removed_headings = set(old_page.page_data.headings) - set(new_page.page_data.headings)
    if removed_headings and not any(_has_garbled_text(h) for h in new_page.page_data.headings):
        findings.append(
            ComparisonFinding(
                category=CATEGORY_TEXT_GARBLED,
                page_pair=pair,
                detail=f"現行にあった見出しが消失しました: {', '.join(sorted(removed_headings))}",
                old_evidence=old_default_evidence,
                new_evidence=new_default_evidence,
                severity=SEVERITY_WARNING,
            )
        )
    return findings


def _detect_unclassified(
    pair: ScreenPair,
    diff_result: DiffResult,
    covered_attributes: set[tuple[str, str]],
    old_default_evidence: SourceEvidence,
    new_default_evidence: SourceEvidence,
) -> list[ComparisonFinding]:
    """4 分類のいずれのルールにも該当しない差分を「未分類（要確認）」として明示する。"""
    findings: list[ComparisonFinding] = []
    for attr_diff in diff_result.attribute_diffs:
        if (attr_diff.field_name, attr_diff.attribute) in covered_attributes:
            continue
        findings.append(
            ComparisonFinding(
                category=CATEGORY_UNCLASSIFIED,
                page_pair=pair,
                detail=(
                    f"分類できない差分（要人手確認）: {attr_diff.field_name}.{attr_diff.attribute}"
                    f"（{attr_diff.before} → {attr_diff.after}・severity={attr_diff.severity}）"
                ),
                old_evidence=old_default_evidence,
                new_evidence=new_default_evidence,
                severity=attr_diff.severity,
            )
        )
    for title_change in diff_result.title_changes:
        if _has_garbled_text(title_change.after):
            continue
        findings.append(
            ComparisonFinding(
                category=CATEGORY_UNCLASSIFIED,
                page_pair=pair,
                detail=(
                    "分類できない差分（要人手確認）: タイトル変化 "
                    f"{title_change.before!r} → {title_change.after!r}"
                ),
                old_evidence=old_default_evidence,
                new_evidence=new_default_evidence,
                severity=SEVERITY_INFO,
            )
        )
    for api_change in diff_result.api_changes:
        findings.append(
            ComparisonFinding(
                category=CATEGORY_UNCLASSIFIED,
                page_pair=pair,
                detail=(
                    f"分類できない差分（要人手確認）: API {api_change.method} {api_change.path} "
                    f"（{api_change.change_type}）"
                ),
                old_evidence=old_default_evidence,
                new_evidence=new_default_evidence,
                severity=SEVERITY_INFO,
            )
        )
    return findings


# ─────────────────────── リンク切れ検査 ───────────────────────


def _check_new_side_links(
    new_analyzed: list[AnalyzedPage],
    pairs: list[ScreenPair],
    new_dir: Path,
    link_opener: LinkOpener | None,
) -> list[ComparisonFinding]:
    pair_by_new_id = {pair.new_page_id: pair for pair in pairs}
    targets: list[tuple[str, str]] = []
    for page in new_analyzed:
        for link in page.page_data.links:
            targets.append((link, page.page_id))
    if not targets:
        return []

    limiter = OriginRateLimiter(crawl_interval_from_env())
    results = check_links(targets, limiter=limiter, opener=link_opener, output_dir=new_dir)

    new_by_id = {p.page_id: p for p in new_analyzed}
    findings: list[ComparisonFinding] = []
    for result in results:
        source_page = new_by_id.get(result.source_page_id)
        new_evidence = _page_evidence(source_page) if source_page is not None else None
        pair = pair_by_new_id.get(result.source_page_id)
        if result.status == STATUS_BROKEN:
            findings.append(
                ComparisonFinding(
                    category=CATEGORY_INOPERABLE,
                    page_pair=pair,
                    detail=(
                        f"リンク切れ: {result.url}（リンク元: {result.source_page_id}・"
                        f"HTTP {result.http_status}）"
                    ),
                    old_evidence=None,
                    new_evidence=new_evidence,
                    severity=SEVERITY_BREAKING,
                )
            )
        elif result.status == STATUS_UNCONFIRMED:
            findings.append(
                ComparisonFinding(
                    category=CATEGORY_UNCLASSIFIED,
                    page_pair=pair,
                    detail=f"未確認（タイムアウト）: {result.url}（リンク元: {result.source_page_id}）",
                    old_evidence=None,
                    new_evidence=new_evidence,
                    severity=SEVERITY_INFO,
                )
            )
    return findings


# ─────────────────────── 動的領域マスクの収集 ───────────────────────


def _collect_masks(
    old_analyzed: list[AnalyzedPage],
    auth_old: Path | None,
    mask_selectors: tuple[str, ...],
    old_dir: Path,
) -> dict[str, tuple[tuple[int, int, int, int], ...]]:
    """現行側の各画面を再訪し、動的領域自動検出＋セレクタ指定マスクを収集する。

    動的領域の自動検出は現行側クロール中（実ブラウザ）にしか行えないため、
    比較オーケストレーション内で追加の 1 回撮影を行う。結果は
    old/dynamic_masks.json に永続化し、スナップショットからの再比較に備える。
    """
    try:
        masks = _detect_masks_with_browser(old_analyzed, auth_old, mask_selectors)
    except Exception as exc:  # noqa: BLE001  # マスク検出の失敗は比較自体を止めない
        logger.warning("動的領域マスクの検出に失敗しました。マスクなしで継続します: %s", exc)
        masks = {}
    _save_dynamic_masks(masks, old_dir)
    return masks


def _detect_masks_with_browser(
    old_analyzed: list[AnalyzedPage],
    auth_old: Path | None,
    mask_selectors: tuple[str, ...],
) -> dict[str, tuple[tuple[int, int, int, int], ...]]:
    from crawler.page_crawler import _browser_page, _goto_stable  # noqa: PLC0415

    masks: dict[str, tuple[tuple[int, int, int, int], ...]] = {}
    with _browser_page(auth_old) as page:
        for analyzed in old_analyzed:
            url = analyzed.page_data.url
            try:
                _goto_stable(page, url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("マスク検出のための再訪に失敗しました: %s (%s)", url, exc)
                continue
            dynamic = detect_dynamic_regions(page, interval_sec=_DYNAMIC_REGION_INTERVAL_SEC)
            selector_boxes = _resolve_selector_boxes(page, mask_selectors)
            masks[analyzed.page_id] = dynamic + selector_boxes
    return masks


def _resolve_selector_boxes(
    page: object, selectors: tuple[str, ...]
) -> tuple[tuple[int, int, int, int], ...]:
    boxes: list[tuple[int, int, int, int]] = []
    for selector in selectors:
        try:
            element = page.query_selector(selector)  # type: ignore[attr-defined]
            if element is None:
                continue
            box = element.bounding_box()
            if box:
                boxes.append((int(box["x"]), int(box["y"]), int(box["width"]), int(box["height"])))
        except Exception as exc:  # noqa: BLE001
            logger.warning("マスクセレクタの解決に失敗しました: %s (%s)", selector, exc)
    return tuple(boxes)


def _save_dynamic_masks(
    masks: dict[str, tuple[tuple[int, int, int, int], ...]], old_dir: Path
) -> Path | None:
    if not masks:
        return None
    try:
        old_dir.mkdir(parents=True, exist_ok=True)
        path = old_dir / DYNAMIC_MASKS_FILE_NAME
        serializable = {page_id: [list(box) for box in boxes] for page_id, boxes in masks.items()}
        path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
    except OSError as exc:
        logger.warning("動的マスクの保存に失敗しました: %s", exc)
        return None


def load_dynamic_masks(old_dir: Path) -> dict[str, tuple[tuple[int, int, int, int], ...]]:
    """永続化済みの動的マスクを読み込む（スナップショットからの再比較用）。"""
    path = old_dir / DYNAMIC_MASKS_FILE_NAME
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("動的マスクの読み込みに失敗しました: %s (%s)", path, exc)
        return {}
    if not isinstance(raw, dict):
        return {}
    result: dict[str, tuple[tuple[int, int, int, int], ...]] = {}
    for page_id, boxes in raw.items():
        if not isinstance(boxes, list):
            continue
        parsed_boxes = []
        for box in boxes:
            if isinstance(box, list) and len(box) == 4:
                parsed_boxes.append((int(box[0]), int(box[1]), int(box[2]), int(box[3])))
        result[str(page_id)] = tuple(parsed_boxes)
    return result
