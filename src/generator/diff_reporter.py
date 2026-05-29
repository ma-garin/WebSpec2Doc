from __future__ import annotations

import html
from datetime import datetime, timezone

from diff.differ import (
    CHANGE_ADDED,
    CHANGE_MODIFIED,
    CHANGE_REMOVED,
    DiffResult,
    FieldChange,
    LinkChange,
    PageChange,
    TitleChange,
)

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


def generate_diff_report(
    diff: DiffResult,
    old_label: str,
    new_label: str,
    target_url: str,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections = [
        _section("画面の追加/削除", _page_changes_table(diff)),
        _section("フォーム項目の変化", _field_changes_table(diff.field_changes)),
        _section("リンク（遷移）の増減", _link_changes_table(diff.link_changes)),
        _section("タイトル変更", _title_changes_table(diff.title_changes)),
    ]
    notice = _notice() if not diff.has_changes else ""
    return "\n".join([
        _html_head(),
        "<body>",
        _header(target_url, old_label, new_label, now),
        '<main class="container">',
        _summary_cards(diff),
        notice,
        *sections,
        "</main>",
        "</body></html>",
    ])


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
    return (
        '<div class="cards">'
        + _card(len(diff.added_pages), "追加画面数")
        + _card(len(diff.removed_pages), "削除画面数")
        + _card(len(diff.field_changes), "項目変更数")
        + _card(len(diff.link_changes), "リンク変更数")
        + "</div>"
    )


def _card(num: int, label: str) -> str:
    return f'<div class="card"><div class="num">{num}</div><div class="label">{html.escape(label)}</div></div>'


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

