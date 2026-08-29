"""比較・カバレッジの網羅性証明: 「どこまで見た/見ていない」を明示するギャップ集計。

audit.jsonl（robots スキップ・ログインウォール・MutationBlocker 遮断の証跡）・
PageData.embedded_frames（読めなかった iframe / closed shadow root・SPEC-3-1）・
capture.coverage.compute_exploration_coverage の未探索画面・comparison.json の
未確認リンク（現新比較・SPEC-3-3）を CoverageGap に正規化する。

evidence-only 原則に従い、断定はしない。「未確認」「見ていない」事実のみを述べる。
report.json のスキーマ・report_hash には一切影響しない（本モジュールは別ファイルの
audit.jsonl / exploration_coverage.json / comparison.json を読むのみで、
report.json 自体には触れない）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from crawler.page_crawler import PageData

logger = logging.getLogger(__name__)

AUDIT_LOG_FILE_NAME = "audit.jsonl"
COMPARISON_JSON_FILE_NAME = "comparison.json"

KIND_ROBOTS_SKIPPED = "robots_skipped"
KIND_LOGIN_WALL = "login_wall"
KIND_UNREADABLE_FRAME = "unreadable_frame"
KIND_UNEXPLORED_SCREEN = "unexplored_screen"
KIND_UNCHECKED_LINK = "unchecked_link"

_KIND_ORDER = (
    KIND_ROBOTS_SKIPPED,
    KIND_LOGIN_WALL,
    KIND_UNREADABLE_FRAME,
    KIND_UNEXPLORED_SCREEN,
    KIND_UNCHECKED_LINK,
)

# diff.link_checker.check_link が未確認（タイムアウト/接続失敗）リンクに
# 付与する detail 文言の接頭辞（diff.comparison._check_new_side_links 参照）。
_UNCHECKED_LINK_DETAIL_PREFIX = "未確認（タイムアウト）: "
_UNCHECKED_LINK_SOURCE_MARKER = "（リンク元"


@dataclass(frozen=True)
class CoverageGap:
    """1 件の「未確認領域」。断定せず、確認できなかった事実のみを記録する。"""

    kind: str  # robots_skipped / unreadable_frame / login_wall / unexplored_screen / unchecked_link
    subject: str  # URL・フレーム src・page_id 等
    reason: str  # 日本語（例:「robots.txt により対象外」）


def _read_audit_log(output_dir: Path) -> list[dict[str, Any]]:
    """audit.jsonl を寛容に読み込む（不在/破損行は警告してスキップ）。"""
    path = output_dir / AUDIT_LOG_FILE_NAME
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("監査ログの行を解釈できませんでした（スキップ）: %s", line[:80])
                continue
            if isinstance(record, dict):
                records.append(record)
    except OSError as exc:
        logger.warning("監査ログの読み込みに失敗しました: %s (%s)", path, exc)
    return records


def _latest_run_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """最新の crawl_started 以降（それ自身を含む）のレコードのみを返す。

    audit.jsonl は追記専用で複数回のクロール実行が混在し得るため、最新実行より
    前の crawl_started（＝過去実行の robots_skipped_urls 等）を再表示しないよう
    位置ベースで絞り込む（§8 既知の罠）。crawl_started が無ければ全件を返す。
    """
    last_start_idx = None
    for idx, record in enumerate(records):
        if record.get("event") == "crawl_started":
            last_start_idx = idx
    if last_start_idx is None:
        return records
    return records[last_start_idx:]


def _robots_skipped_gaps(latest_records: list[dict[str, Any]]) -> list[CoverageGap]:
    gaps: list[CoverageGap] = []
    for record in latest_records:
        if record.get("event") != "crawl_started":
            continue
        for url in record.get("robots_skipped_urls") or []:
            gaps.append(
                CoverageGap(
                    kind=KIND_ROBOTS_SKIPPED,
                    subject=str(url),
                    reason="robots.txt により対象外（未確認）",
                )
            )
    return gaps


def _login_wall_gaps(latest_records: list[dict[str, Any]]) -> list[CoverageGap]:
    gaps: list[CoverageGap] = []
    for record in latest_records:
        if record.get("event") != "login_wall_detected":
            continue
        gaps.append(
            CoverageGap(
                kind=KIND_LOGIN_WALL,
                subject=str(record.get("url") or ""),
                reason="ログインが必要なため未確認",
            )
        )
    return gaps


def _unreadable_frame_gaps(pages: list[PageData]) -> list[CoverageGap]:
    gaps: list[CoverageGap] = []
    for page in pages:
        for frame in page.embedded_frames:
            if frame.readable:
                continue
            reason = frame.note or "読み取り不可のため未確認"
            gaps.append(
                CoverageGap(kind=KIND_UNREADABLE_FRAME, subject=frame.src, reason=f"{reason}")
            )
    return gaps


def _unexplored_screen_gaps(coverage: dict[str, Any] | None) -> list[CoverageGap]:
    if not coverage:
        return []
    gaps: list[CoverageGap] = []
    for screen in coverage.get("screens") or []:
        if screen.get("explored"):
            continue
        gaps.append(
            CoverageGap(
                kind=KIND_UNEXPLORED_SCREEN,
                subject=str(screen.get("url") or screen.get("page_id") or ""),
                reason="探索セッションで未訪問のため未確認",
            )
        )
    return gaps


def _unchecked_link_gaps(output_dir: Path) -> list[CoverageGap]:
    """現新比較の comparison.json（あれば）から未確認リンクを取り出す。"""
    path = output_dir / COMPARISON_JSON_FILE_NAME
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("comparison.json の読み込みに失敗しました（スキップ）: %s (%s)", path, exc)
        return []
    gaps: list[CoverageGap] = []
    for finding in data.get("findings") or []:
        detail = str(finding.get("detail") or "")
        if not detail.startswith(_UNCHECKED_LINK_DETAIL_PREFIX):
            continue
        rest = detail[len(_UNCHECKED_LINK_DETAIL_PREFIX) :]
        url = rest.split(_UNCHECKED_LINK_SOURCE_MARKER, 1)[0].strip()
        gaps.append(
            CoverageGap(
                kind=KIND_UNCHECKED_LINK,
                subject=url,
                reason="タイムアウト/接続失敗のため未確認（切れとは断定しない）",
            )
        )
    return gaps


def collect_coverage_gaps(
    output_dir: Path,
    pages: list[PageData],
    coverage: dict[str, Any] | None = None,
) -> tuple[CoverageGap, ...]:
    """audit.jsonl・embedded_frames・探索カバレッジ・現新比較の情報源を統合する。

    いずれの情報源も欠落時はその情報源だけを省略して集計する（§5-5 エラー処理表）。
    戻り値が空タプルの場合、呼び出し側（html_reporter）は節自体を出力しない（AC-8）。
    """
    latest_records = _latest_run_records(_read_audit_log(output_dir))
    gaps: list[CoverageGap] = [
        *_robots_skipped_gaps(latest_records),
        *_login_wall_gaps(latest_records),
        *_unreadable_frame_gaps(pages),
        *_unexplored_screen_gaps(coverage),
        *_unchecked_link_gaps(output_dir),
    ]
    order = {kind: i for i, kind in enumerate(_KIND_ORDER)}
    gaps.sort(key=lambda g: (order.get(g.kind, len(_KIND_ORDER)), g.subject))
    return tuple(gaps)
