"""文書の再生（Doc Fusion Phase 3）。

古い参考文書の構造（画面・項目・記載順）を骨格として維持したまま、実測で
確認できた値に更新した新版仕様書（refreshed_spec.md）と変更ログ
（refresh_log.json）を生成する。

**LLM を使わない決定的マージ**である。文書の自由文を LLM でリライトすると
根拠のない文が混入するため、更新は「突合で対応づいた属性の置換」と
「実測 evidence 付きの追記」に限定する（evidence-only 原則）。
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from analyzer.html_analyzer import AnalyzedPage
from crawler.page_crawler import FieldData
from ingest.matcher import FusionResult
from ingest.models import (
    DocumentBundle,
    DocumentedField,
    DocumentedScreen,
    DocumentEvidence,
    document_evidence_to_dict,
)

REFRESH_MD_NAME = "refreshed_spec.md"
REFRESH_LOG_NAME = "refresh_log.json"
_JSON_INDENT = 2

_NOTE_UPDATED = "実測により更新（旧: {old} → 実測: {new}）"
_NOTE_UNCONFIRMED = "実測で確認できず（未確認 — 廃止/権限/未探索の可能性）"
_NOTE_UNDOCUMENTED = "文書未記載（実測で検出）"
_NOTE_LOOKUP_FAILED = "実測値の特定に失敗（doc_fusion.md 参照）"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RefreshEntry:
    """新版生成時の 1 変更（変更ログの行）。"""

    kind: str  # "updated" / "doc_only" / "new" / "unchanged"
    screen_name: str  # 文書上の画面名（new は実測タイトル）
    subject: str  # 対象（項目名・"画面" 等）
    attribute: str = ""  # 変わった属性（"必須区分" / "桁数" / ""）
    old_value: str = ""  # 文書記載値（new は ""）
    new_value: str = ""  # 実測値（doc_only は ""）
    doc_evidence: DocumentEvidence | None = None
    crawl_selector: str = ""  # 実測根拠（SourceEvidence.selector）


def _crawled_fields(page: AnalyzedPage) -> list[FieldData]:
    """ページ内の全フォームフィールドを走査する（ingest.matcher と同じ規則）。"""
    return [field for form in page.page_data.forms for field in form.fields]


def _find_page(pages: list[AnalyzedPage], page_id: str) -> AnalyzedPage | None:
    return next((p for p in pages if p.page_id == page_id), None)


def _lookup_crawled_field(page: AnalyzedPage | None, selector: str) -> FieldData | None:
    """crawl_selector から実測 FieldData を逆引きする。見つからなければ None。"""
    if page is None or not selector:
        return None
    for crawled in _crawled_fields(page):
        if crawled.evidence is not None and crawled.evidence.selector == selector:
            return crawled
    return None


def _fields_for_screen(bundle: DocumentBundle, screen: DocumentedScreen) -> list[DocumentedField]:
    """文書上でこの画面に属する項目を集める（matcher._fields_for_screen と同じ規則）。

    画面参照が空の項目は、文書全体の画面が 1 つだけの場合に限りその画面に帰属させる。
    """
    keys = {screen.name, screen.screen_id} - {""}
    fields = [f for f in bundle.fields if f.screen_name in keys]
    if not fields and len(bundle.screens) == 1:
        fields = [f for f in bundle.fields if not f.screen_name]
    return fields


def _diff_attribute(doc_field: DocumentedField, crawled: FieldData) -> tuple[str, str, str]:
    """doc_field と実測 crawled の間で矛盾している属性を 1 つ特定する。

    (attribute, old_value, new_value) を返す。矛盾が特定できない場合は
    ("", "", "") を返す（呼び出し側は特定失敗として扱う）。
    """
    if doc_field.required is not None and doc_field.required != crawled.required:
        old = "必須" if doc_field.required else "任意"
        new = "必須" if crawled.required else "任意"
        return "必須区分", old, new
    if (
        doc_field.max_length is not None
        and crawled.maxlength is not None
        and doc_field.max_length != crawled.maxlength
    ):
        return "桁数", str(doc_field.max_length), str(crawled.maxlength)
    return "", "", ""


def _official_screen_name(result: FusionResult, page_id: str, fallback: str) -> str:
    match = next((m for m in result.screen_matches if m.page_id == page_id), None)
    return match.screen.name if match is not None else fallback


def build_refresh_entries(
    result: FusionResult,
    bundle: DocumentBundle,
    pages: list[AnalyzedPage],
) -> tuple[RefreshEntry, ...]:
    """FusionResult.field_gaps を変更エントリへ変換する。

    - kind="mismatch" の FieldGap（doc_field あり）→ RefreshEntry(kind="updated")。
      旧値・新値は doc_field（max_length/required）と対応 FieldData
      （maxlength/required、crawl_selector から逆引き）から取り直す
      （detail 文字列のパースはしない）。
      doc_field が無い矛盾（DocumentedRule 由来の限度値矛盾）は、業務ルールの
      真偽判定がスコープ外のため変換しない（仕様外判断）。
    - kind="doc_only" → RefreshEntry(kind="doc_only")
    - kind="crawl_only" → RefreshEntry(kind="new")
    - ギャップに現れない対応済み項目 → RefreshEntry(kind="unchanged")
    - 画面まるごとの doc_only / crawl_only（新規画面）も同様に追加する。
    """
    pages_by_id = {p.page_id: p for p in pages}
    entries: list[RefreshEntry] = []

    for gap in result.field_gaps:
        if gap.kind == "mismatch":
            if gap.doc_field is None:
                continue
            screen_name = _official_screen_name(result, gap.page_id, gap.doc_field.screen_name)
            crawled = _lookup_crawled_field(pages_by_id.get(gap.page_id), gap.crawl_selector)
            attribute, old_value, new_value = ("", "", "")
            if crawled is not None:
                attribute, old_value, new_value = _diff_attribute(gap.doc_field, crawled)
            entries.append(
                RefreshEntry(
                    kind="updated",
                    screen_name=screen_name,
                    subject=gap.doc_field.name,
                    attribute=attribute,
                    old_value=old_value,
                    new_value=new_value,
                    doc_evidence=gap.doc_field.evidence,
                    crawl_selector=gap.crawl_selector,
                )
            )
        elif gap.kind == "doc_only":
            if gap.doc_field is None:
                continue
            screen_name = _official_screen_name(result, gap.page_id, gap.doc_field.screen_name)
            entries.append(
                RefreshEntry(
                    kind="doc_only",
                    screen_name=screen_name,
                    subject=gap.doc_field.name,
                    doc_evidence=gap.doc_field.evidence,
                )
            )
        elif gap.kind == "crawl_only":
            screen_name = _official_screen_name(result, gap.page_id, gap.page_id)
            entries.append(
                RefreshEntry(
                    kind="new",
                    screen_name=screen_name,
                    subject=gap.field_name,
                    crawl_selector=gap.crawl_selector,
                )
            )

    for screen in result.doc_only_screens:
        entries.append(
            RefreshEntry(
                kind="doc_only",
                screen_name=screen.name,
                subject="画面",
                doc_evidence=screen.evidence,
            )
        )

    for page_id in result.crawl_only_page_ids:
        page = pages_by_id.get(page_id)
        title = page.page_data.title if page is not None else page_id
        url = page.page_data.url if page is not None else ""
        entries.append(
            RefreshEntry(
                kind="new",
                screen_name=title,
                subject="画面",
                new_value=url,
            )
        )

    gap_field_keys = {
        (gap.page_id, gap.field_name)
        for gap in result.field_gaps
        if gap.kind in ("doc_only", "mismatch")
    }
    for match in result.screen_matches:
        for doc_field in _fields_for_screen(bundle, match.screen):
            if (match.page_id, doc_field.name) in gap_field_keys:
                continue
            entries.append(
                RefreshEntry(
                    kind="unchanged",
                    screen_name=match.screen.name,
                    subject=doc_field.name,
                    doc_evidence=doc_field.evidence,
                )
            )

    return tuple(entries)


def _required_mark(value: bool | None) -> str:
    if value is None:
        return ""
    return "○" if value else "×"


def _length_mark(value: int | None) -> str:
    return "" if value is None else str(value)


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|")


def _field_row(
    doc_field: DocumentedField,
    required_display: bool | None,
    length_display: int | None,
    note_suffix: str,
) -> str:
    note = doc_field.note
    if note_suffix:
        note = f"{note} ※{note_suffix}".strip()
    cells = (
        doc_field.name,
        doc_field.field_type,
        _required_mark(required_display),
        _length_mark(length_display),
        note,
    )
    return "| " + " | ".join(_escape_cell(c) for c in cells) + " |"


def _render_matched_screen(
    heading: str,
    screen: DocumentedScreen,
    match_page_id: str,
    bundle: DocumentBundle,
    result: FusionResult,
    pages_by_id: dict[str, AnalyzedPage],
) -> list[str]:
    lines: list[str] = [heading, ""]
    lines += ["| 項目名 | 型 | 必須 | 桁数 | 備考 |", "|---|---|---|---|---|"]
    page = pages_by_id.get(match_page_id)
    field_gaps = [g for g in result.field_gaps if g.page_id == match_page_id]
    for doc_field in _fields_for_screen(bundle, screen):
        mismatches = [
            g for g in field_gaps if g.kind == "mismatch" and g.field_name == doc_field.name
        ]
        doc_only = [
            g for g in field_gaps if g.kind == "doc_only" and g.field_name == doc_field.name
        ]
        if mismatches:
            required_display = doc_field.required
            length_display = doc_field.max_length
            notes: list[str] = []
            failed = False
            for gap in mismatches:
                crawled = _lookup_crawled_field(page, gap.crawl_selector)
                if crawled is None:
                    failed = True
                    continue
                attribute, old_value, new_value = _diff_attribute(doc_field, crawled)
                if attribute == "必須区分":
                    required_display = crawled.required
                    notes.append(_NOTE_UPDATED.format(old=old_value, new=new_value))
                elif attribute == "桁数":
                    length_display = crawled.maxlength
                    notes.append(_NOTE_UPDATED.format(old=old_value, new=new_value))
                else:
                    failed = True
            if failed and not notes:
                notes.append(_NOTE_LOOKUP_FAILED)
            lines.append(_field_row(doc_field, required_display, length_display, "；".join(notes)))
        elif doc_only:
            lines.append(
                _field_row(doc_field, doc_field.required, doc_field.max_length, _NOTE_UNCONFIRMED)
            )
        else:
            lines.append(_field_row(doc_field, doc_field.required, doc_field.max_length, ""))
    for gap in field_gaps:
        if gap.kind != "crawl_only":
            continue
        crawled = _lookup_crawled_field(page, gap.crawl_selector)
        if crawled is None:
            continue
        undocumented_field = DocumentedField(
            name=gap.field_name,
            field_type=crawled.field_type,
        )
        lines.append(
            _field_row(undocumented_field, crawled.required, crawled.maxlength, _NOTE_UNDOCUMENTED)
        )
    lines.append("")
    return lines


def _render_doc_only_screen(
    heading: str, screen: DocumentedScreen, bundle: DocumentBundle
) -> list[str]:
    lines: list[str] = [heading, "", f"> ※{_NOTE_UNCONFIRMED}", ""]
    doc_fields = _fields_for_screen(bundle, screen)
    if doc_fields:
        lines += ["| 項目名 | 型 | 必須 | 桁数 | 備考 |", "|---|---|---|---|---|"]
        for doc_field in doc_fields:
            lines.append(_field_row(doc_field, doc_field.required, doc_field.max_length, ""))
        lines.append("")
    return lines


def _render_new_screens(result: FusionResult, pages_by_id: dict[str, AnalyzedPage]) -> list[str]:
    if not result.crawl_only_page_ids:
        return []
    lines: list[str] = ["## 文書未記載の新規画面", ""]
    for page_id in result.crawl_only_page_ids:
        page = pages_by_id.get(page_id)
        if page is None:
            continue
        lines.append(f"### {page.page_data.title}（実測 evidence: {page.page_data.url}）")
        lines.append("")
        crawled_fields = _crawled_fields(page)
        if crawled_fields:
            lines += ["| 項目名 | 型 | 必須 | 桁数 | 備考 |", "|---|---|---|---|---|"]
            for crawled in crawled_fields:
                name = crawled.name or crawled.element_id or crawled.field_type
                doc_field = DocumentedField(name=name, field_type=crawled.field_type)
                lines.append(
                    _field_row(doc_field, crawled.required, crawled.maxlength, _NOTE_UNDOCUMENTED)
                )
            lines.append("")
        else:
            lines.append("（フォーム項目なし）")
            lines.append("")
    return lines


def render_refreshed_markdown(
    entries: tuple[RefreshEntry, ...],
    result: FusionResult,
    bundle: DocumentBundle,
    pages: list[AnalyzedPage],
) -> str:
    """文書順の骨格で新版 md を組み立てる。

    注釈書式は固定:
    「※実測により更新（旧: {old} → 実測: {new}）」
    「※実測で確認できず（未確認 — 廃止/権限/未探索の可能性）」
    「※文書未記載（実測で検出）」
    """
    pages_by_id = {p.page_id: p for p in pages}
    counts = Counter(e.kind for e in entries)
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        "# 再生版仕様書（refreshed_spec）",
        "",
        f"生成日時: {now}",
        f"元文書: {', '.join(bundle.source_files)}",
        "",
        "## サマリ",
        "",
        f"- 更新（実測で値を修正）: {counts.get('updated', 0)} 件",
        f"- 未確認（文書のみ・実測で見つからず）: {counts.get('doc_only', 0)} 件",
        f"- 新規（文書未記載・実測のみ）: {counts.get('new', 0)} 件",
        f"- 変更なし（文書と実測が一致）: {counts.get('unchanged', 0)} 件",
        "",
        "> 本書は決定的マージ（LLM 不使用）で生成しています。自由文の説明・業務背景の段落は",
        "> 引き継がれません。業務ルールの真偽は実測で検証していないため文書記載のままです。",
        "",
    ]

    seen_names: Counter[str] = Counter()
    for screen in bundle.screens:
        seen_names[screen.name] += 1
        display_name = (
            screen.name
            if seen_names[screen.name] == 1
            else f"{screen.name} ({seen_names[screen.name]})"
        )
        match = next((m for m in result.screen_matches if m.screen is screen), None)
        if match is not None:
            page = pages_by_id.get(match.page_id)
            page_title = page.page_data.title if page is not None else match.page_title
            page_url = page.page_data.url if page is not None else match.page_url
            heading = f"## {display_name}（実測: {page_title} / {page_url}）"
            lines += _render_matched_screen(
                heading, screen, match.page_id, bundle, result, pages_by_id
            )
        else:
            heading = f"## {display_name}（実測で確認できず）"
            lines += _render_doc_only_screen(heading, screen, bundle)

    lines += _render_new_screens(result, pages_by_id)
    return "\n".join(lines)


def _refresh_log_to_dict(entries: tuple[RefreshEntry, ...]) -> dict:
    counts = Counter(e.kind for e in entries)
    return {
        "meta": {
            "updated": counts.get("updated", 0),
            "doc_only": counts.get("doc_only", 0),
            "new": counts.get("new", 0),
            "unchanged": counts.get("unchanged", 0),
        },
        "entries": [
            {
                "kind": e.kind,
                "screen_name": e.screen_name,
                "subject": e.subject,
                "attribute": e.attribute,
                "old_value": e.old_value,
                "new_value": e.new_value,
                "doc_evidence": document_evidence_to_dict(e.doc_evidence),
                "crawl_selector": e.crawl_selector,
            }
            for e in entries
        ],
    }


def save_refresh_outputs(
    result: FusionResult,
    bundle: DocumentBundle,
    pages: list[AnalyzedPage],
    output_dir: Path,
) -> None:
    """refreshed_spec.md / refresh_log.json を出力する。

    bundle.screens が空なら何も書かない（骨格が作れないため文書再生をスキップ）。
    json は fusion_reporter と同じ ensure_ascii=False・indent=2。
    """
    if not bundle.screens:
        logger.info("画面情報が無いため文書再生をスキップしました")
        return
    entries = build_refresh_entries(result, bundle, pages)
    markdown = render_refreshed_markdown(entries, result, bundle, pages)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / REFRESH_MD_NAME).write_text(markdown, encoding="utf-8")
    log_data = _refresh_log_to_dict(entries)
    (output_dir / REFRESH_LOG_NAME).write_text(
        json.dumps(log_data, ensure_ascii=False, indent=_JSON_INDENT), encoding="utf-8"
    )
