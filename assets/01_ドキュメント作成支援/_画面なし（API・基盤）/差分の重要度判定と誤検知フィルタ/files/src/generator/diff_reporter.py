from __future__ import annotations

import html
from datetime import UTC, datetime
from typing import Any

from diff.differ import (
    CHANGE_ADDED,
    CHANGE_MODIFIED,
    CHANGE_REMOVED,
    SEVERITY_BREAKING,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    ApiChange,
    DiffResult,
    FieldAttributeDiff,
    FieldChange,
    LinkChange,
    PageChange,
    TitleChange,
)
from diff.severity import summarize_severity

REPORT_TITLE = "仕様ドリフトレポート"
NAVY = "#00285E"
CYAN = "#009FCA"
GRAY = "#F5F5F5"
TEXT = "#333333"
GREEN = "#198038"
RED = "#DA1E28"
ORANGE = "#8D6B00"
NO_CHANGES_MESSAGE = "変更は検出されませんでした"
EMPTY_TABLE_MESSAGE = "該当する変更はありません"

SEVERITY_LABELS = {
    SEVERITY_BREAKING: "重大",
    SEVERITY_WARNING: "警告",
    SEVERITY_INFO: "情報",
}
SEVERITY_CLASSES = {
    SEVERITY_BREAKING: "sev-breaking",
    SEVERITY_WARNING: "sev-warning",
    SEVERITY_INFO: "sev-info",
}


def generate_diff_report(
    diff: DiffResult,
    old_label: str,
    new_label: str,
    target_url: str,
    *,
    scored: list[dict[str, Any]] | None = None,
    exclusions: list[dict[str, Any]] | None = None,
    summary_text: str = "",
    screenshot_diffs: list[Any] | None = None,
) -> str:
    """差分レポートHTMLを組み立てる。

    scored / exclusions / screenshot_diffs は任意。渡された場合のみ該当セクションを出す
    （既存の呼び出し側はそのまま動く）。
    """
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    sections = [
        _section("画面の追加/削除", _page_changes_table(diff)),
        _section("フォーム項目の変化", _field_changes_table(diff.field_changes)),
        _section("属性レベル変更", _attribute_changes_table(diff.attribute_diffs)),
        _section("API変更", _api_changes_table(diff.api_changes)),
        _section("リンク（遷移）の増減", _link_changes_table(diff.link_changes)),
        _section("タイトル変更", _title_changes_table(diff.title_changes)),
    ]
    if screenshot_diffs:
        sections.append(_section("スクリーンショット比較", _screenshot_table(screenshot_diffs)))
    if exclusions:
        sections.append(_section("無視ルールで除外した変更", _exclusions_table(exclusions)))
    notice = _notice() if not diff.has_changes else ""
    return "\n".join(
        [
            _html_head(),
            "<body>",
            _header(target_url, old_label, new_label, now),
            '<main class="container">',
            _summary_cards(diff),
            _severity_overview(scored, summary_text),
            notice,
            *sections,
            "</main>",
            "</body></html>",
        ]
    )


def _severity_overview(scored: list[dict[str, Any]] | None, summary_text: str) -> str:
    """重要度の内訳と変更要約。根拠を必ず併記し、価値判断に見せない。"""
    if not scored and not summary_text:
        return ""
    parts = ['<div class="overview">']
    if summary_text:
        parts.append(f'<p class="overview-text">{html.escape(summary_text)}</p>')
    if scored:
        counts = summarize_severity(scored)
        badges = "".join(
            f'<span class="sev-{level}">{SEVERITY_LABELS[level]} {counts[level]}</span>'
            for level in ("breaking", "warning", "info")
            if counts.get(level)
        )
        parts.append(f'<p class="overview-badges">{badges}</p>')
        top = [item for item in scored if str(item.get("severity")) == "breaking"][:5]
        if top:
            rows = "".join(
                f"<li><b>{html.escape(str(item.get('label', '')))}</b>"
                f" — {html.escape(str(item.get('reason', '')))}</li>"
                for item in top
            )
            parts.append(f'<ul class="overview-top">{rows}</ul>')
    parts.append(
        '<p class="overview-note">重要度はルールによる分類であり、'
        "変更が安全か危険かの判断ではない。</p></div>"
    )
    return "".join(parts)


def _exclusions_table(exclusions: list[dict[str, Any]]) -> str:
    """除外した変更の内訳。黙って消さず件数と根拠ルールを必ず出す。"""
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item.get('rule_kind', '')))}</td>"
        f"<td><code>{html.escape(str(item.get('rule_pattern', '')))}</code></td>"
        f"<td>{html.escape(str(item.get('rule_note', '')))}</td>"
        f"<td>{int(item.get('count', 0))}</td>"
        "</tr>"
        for item in exclusions
    )
    total = sum(int(item.get("count", 0)) for item in exclusions)
    head = _table_start(("ルール種別", "パターン", "メモ", "除外件数"))
    return (
        f'<p class="overview-text">除外 {total} 件。'
        "除外分は差分本文には出していない（下表が全内訳）。</p>"
        f"{head}{rows}{_table_end()}"
    )


def _screenshot_table(screenshot_diffs: list[Any]) -> str:
    """画面ごとの画像差分率。しきい値超過を先頭に並べる。"""
    items = sorted(
        screenshot_diffs,
        key=lambda d: (not _attr(d, "is_significant", False), -float(_attr(d, "diff_ratio", 0.0))),
    )
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(_attr(item, 'page_id', '')))}</td>"
        f"<td class=\"num\">{float(_attr(item, 'diff_ratio', 0.0)) * 100:.2f}%</td>"
        f"<td>{'<span class=\"sev-breaking\">しきい値超過</span>' if _attr(item, 'is_significant', False) else '<span class=\"sev-info\">範囲内</span>'}</td>"
        f"<td>{_image_cell(str(_attr(item, 'before_path', '')))}</td>"
        f"<td>{_image_cell(str(_attr(item, 'after_path', '')))}</td>"
        "</tr>"
        for item in items
    )
    if not rows:
        return _empty()
    head = _table_start(("画面", "差分率", "判定", "変更前", "変更後"))
    return f"{head}{rows}{_table_end()}"


def _image_cell(path: str) -> str:
    if not path:
        return '<span class="empty">未取得</span>'
    src = html.escape(path)
    return f'<a href="{src}"><img class="shot" src="{src}" alt=""></a>'


def _attr(obj: Any, name: str, default: Any) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _html_head() -> str:
    return (
        '<!doctype html><html lang="ja"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(REPORT_TITLE)}</title>"
        f"<style>{_css()}</style>"
        "</head>"
    )


def _css() -> str:
    return f"""
:root{{--navy:{NAVY};--cyan:{CYAN};--gray:{GRAY};--text:{TEXT};--add:{GREEN};--remove:{RED};--modify:{ORANGE}}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:"Noto Sans JP","Meiryo",sans-serif;color:var(--text);background:var(--gray)}}
.site-header{{background:var(--navy);color:#fff;padding:1.2rem 2rem}}
.site-header h1{{font-size:1.4rem;font-weight:700}}
.site-header .meta{{font-size:.85rem;opacity:.9;margin-top:.3rem;line-height:1.6}}
.container{{max-width:1200px;margin:2rem auto;padding:0 1.5rem}}
.cards{{display:flex;gap:1rem;margin-bottom:2rem;flex-wrap:wrap}}
.card{{flex:1;min-width:150px;background:#fff;border:2px solid var(--cyan);border-radius:8px;padding:1rem 1.5rem;text-align:center}}
.card .num{{font-size:2rem;font-weight:700;color:var(--navy)}}
.card .label{{font-size:.85rem;color:#666;margin-top:.2rem}}
.notice{{background:#fff;border-left:6px solid var(--cyan);border-radius:8px;margin-bottom:2rem;padding:1rem 1.2rem;font-weight:700}}
section{{background:#fff;border-radius:8px;margin-bottom:2rem;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
section h2{{background:var(--navy);color:#fff;padding:.8rem 1.2rem;font-size:1rem}}
.section-body{{padding:1.2rem;overflow-x:auto}}
table{{border-collapse:collapse;width:100%;font-size:.9rem}}
th{{background:var(--navy);color:#fff;padding:.6rem .8rem;text-align:left;white-space:nowrap}}
td{{padding:.55rem .8rem;border-bottom:1px solid #eee;vertical-align:top}}
tr:last-child td{{border-bottom:none}}
tr:nth-child(even) td{{background:#f9f9f9}}
.badge{{font-weight:700;white-space:nowrap}}
.added{{color:var(--add)}}
.removed{{color:var(--remove)}}
.modified{{color:var(--modify)}}
.empty{{color:#777}}
.card-breaking{{border-color:var(--remove);background:#fff5f5}}
.card-breaking .num{{color:var(--remove)}}
.sev-breaking{{display:inline-block;padding:1px 8px;border-radius:10px;background:var(--remove);color:#fff;font-size:.8rem}}
.sev-warning{{display:inline-block;padding:1px 8px;border-radius:10px;background:var(--modify);color:#fff;font-size:.8rem}}
.sev-info{{display:inline-block;padding:1px 8px;border-radius:10px;background:#e0e0e0;color:#333;font-size:.8rem}}
.overview{{background:#fff;border-radius:8px;margin-bottom:2rem;padding:1.2rem;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.overview-text{{font-size:1rem;font-weight:700;line-height:1.7}}
.overview-badges{{display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.7rem}}
.overview-top{{margin:.9rem 0 0 1.2rem;font-size:.9rem;line-height:1.8}}
.overview-note{{margin-top:.9rem;font-size:.8rem;color:#666}}
td.num{{font-variant-numeric:tabular-nums;white-space:nowrap}}
img.shot{{max-width:180px;height:auto;border:1px solid #ddd;border-radius:4px;display:block}}
"""


def _header(target_url: str, old_label: str, new_label: str, now: str) -> str:
    return (
        '<header class="site-header">'
        f"<h1>{html.escape(REPORT_TITLE)}</h1>"
        '<div class="meta">'
        f"対象URL: {html.escape(target_url)}<br>"
        f"比較: {html.escape(old_label)} → {html.escape(new_label)}"
        f" &nbsp;|&nbsp; 生成日時: {html.escape(now)}"
        "</div></header>"
    )


def _summary_cards(diff: DiffResult) -> str:
    breaking = sum(1 for ad in diff.attribute_diffs if ad.severity == SEVERITY_BREAKING)
    return (
        '<div class="cards">'
        + _card(len(diff.added_pages), "追加画面数")
        + _card(len(diff.removed_pages), "削除画面数")
        + _card(len(diff.field_changes), "項目変更数")
        + _card(len(diff.link_changes), "リンク変更数")
        + _card(breaking, "重大な変更", emphasize=breaking > 0)
        + "</div>"
    )


def _card(num: int, label: str, emphasize: bool = False) -> str:
    cls = "card card-breaking" if emphasize else "card"
    return f'<div class="{cls}"><div class="num">{num}</div><div class="label">{html.escape(label)}</div></div>'


def _notice() -> str:
    return f'<div class="notice">{html.escape(NO_CHANGES_MESSAGE)}</div>'


def _section(title: str, body: str) -> str:
    return (
        "<section>"
        f"<h2>{html.escape(title)}</h2>"
        f'<div class="section-body">{body}</div>'
        "</section>"
    )


def _page_changes_table(diff: DiffResult) -> str:
    changes = diff.added_pages + diff.removed_pages
    if not changes:
        return _empty()
    rows = [_table_start(("画面URL", "タイトル", "種別"))]
    rows.extend(_page_change_row(change) for change in changes)
    rows.append(_table_end())
    return "\n".join(rows)


def _page_change_row(change: PageChange) -> str:
    return (
        "<tr>"
        f"<td>{html.escape(change.url)}</td>"
        f"<td>{html.escape(change.title)}</td>"
        f"<td>{_change_badge(change.change_type)}</td>"
        "</tr>"
    )


def _field_changes_table(changes: tuple[FieldChange, ...]) -> str:
    if not changes:
        return _empty()
    rows = [_table_start(("画面URL", "フィールド名", "種別", "変更前 → 変更後"))]
    rows.extend(_field_change_row(change) for change in changes)
    rows.append(_table_end())
    return "\n".join(rows)


def _field_change_row(change: FieldChange) -> str:
    return (
        "<tr>"
        f"<td>{html.escape(change.page_url)}</td>"
        f"<td>{html.escape(change.field_name)}</td>"
        f"<td>{_change_badge(change.change_type)}</td>"
        f"<td>{_field_value(change.before)} → {_field_value(change.after)}</td>"
        "</tr>"
    )


def _attribute_changes_table(changes: tuple[FieldAttributeDiff, ...]) -> str:
    if not changes:
        return _empty()
    rows = [_table_start(("画面URL", "フィールド名", "属性", "変更前 → 変更後", "重要度"))]
    rows.extend(_attribute_change_row(change) for change in changes)
    rows.append(_table_end())
    return "\n".join(rows)


def _attribute_change_row(change: FieldAttributeDiff) -> str:
    return (
        "<tr>"
        f"<td>{html.escape(change.page_url)}</td>"
        f"<td>{html.escape(change.field_name)}</td>"
        f"<td>{html.escape(change.attribute)}</td>"
        f"<td>{html.escape(change.before)} → {html.escape(change.after)}</td>"
        f"<td>{_severity_badge(change.severity)}</td>"
        "</tr>"
    )


def _severity_badge(severity: str) -> str:
    label = SEVERITY_LABELS.get(severity, severity)
    class_name = SEVERITY_CLASSES.get(severity, "sev-info")
    return f'<span class="badge {class_name}">{html.escape(label)}</span>'


def _api_changes_table(changes: tuple[ApiChange, ...]) -> str:
    if not changes:
        return _empty()
    rows = [_table_start(("画面URL", "メソッド", "パス", "種別"))]
    rows.extend(_api_change_row(change) for change in changes)
    rows.append(_table_end())
    return "\n".join(rows)


def _api_change_row(change: ApiChange) -> str:
    return (
        "<tr>"
        f"<td>{html.escape(change.page_url)}</td>"
        f"<td>{html.escape(change.method)}</td>"
        f"<td>{html.escape(change.path)}</td>"
        f"<td>{_change_badge(change.change_type)}</td>"
        "</tr>"
    )


def _link_changes_table(changes: tuple[LinkChange, ...]) -> str:
    if not changes:
        return _empty()
    rows = [_table_start(("画面URL", "リンク", "種別"))]
    rows.extend(_link_change_row(change) for change in changes)
    rows.append(_table_end())
    return "\n".join(rows)


def _link_change_row(change: LinkChange) -> str:
    return (
        "<tr>"
        f"<td>{html.escape(change.page_url)}</td>"
        f"<td>{html.escape(change.link)}</td>"
        f"<td>{_change_badge(change.change_type)}</td>"
        "</tr>"
    )


def _title_changes_table(changes: tuple[TitleChange, ...]) -> str:
    if not changes:
        return _empty()
    rows = [_table_start(("画面URL", "変更前", "変更後"))]
    rows.extend(_title_change_row(change) for change in changes)
    rows.append(_table_end())
    return "\n".join(rows)


def _title_change_row(change: TitleChange) -> str:
    return (
        "<tr>"
        f"<td>{html.escape(change.url)}</td>"
        f"<td>{html.escape(change.before)}</td>"
        f"<td>{html.escape(change.after)}</td>"
        "</tr>"
    )


def _table_start(headers: tuple[str, ...]) -> str:
    cells = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    return f"<table><thead><tr>{cells}</tr></thead><tbody>"


def _table_end() -> str:
    return "</tbody></table>"


def _empty() -> str:
    return f'<p class="empty">{html.escape(EMPTY_TABLE_MESSAGE)}</p>'


def _change_badge(change_type: str) -> str:
    label = {
        CHANGE_ADDED: "追加",
        CHANGE_REMOVED: "削除",
        CHANGE_MODIFIED: "変更",
    }.get(change_type, change_type)
    class_name = {
        CHANGE_ADDED: "added",
        CHANGE_REMOVED: "removed",
        CHANGE_MODIFIED: "modified",
    }.get(change_type, "modified")
    return f'<span class="badge {class_name}">{html.escape(label)}</span>'


def _field_value(field: object | None) -> str:
    if field is None:
        return "-"
    attrs = (
        f"type={getattr(field, 'field_type', '')}",
        f"required={getattr(field, 'required', False)}",
        f"placeholder={getattr(field, 'placeholder', '')}",
    )
    return html.escape(", ".join(str(item) for item in attrs))
