"""機能一覧（features.md）の生成。

画面のforms/buttons/transitionsから「機能」を導出する。新規に機能を推測・創作せず、
report.json に実際に記録された要素からのみ機械的に集計する（evidence-only）。
"""

from __future__ import annotations

from typing import Any

_FeatureRow = tuple[str, str, str, str]


def _screen_label(screen: dict[str, Any]) -> str:
    page_id = str(screen.get("page_id") or "")
    title = str(screen.get("title") or "")
    return f"{page_id} {title}".strip()


def _form_rows(screen: dict[str, Any], start_no: int) -> list[_FeatureRow]:
    rows: list[_FeatureRow] = []
    label = _screen_label(screen)
    for idx, form in enumerate(screen.get("forms") or []):
        action = str(form.get("action") or "")
        method = str(form.get("method") or "GET").upper()
        field_count = len(form.get("fields") or [])
        rows.append(
            (
                f"F{start_no + idx:03d}",
                "フォーム機能",
                label,
                f"{method} {action}（入力項目{field_count}件）".strip(),
            )
        )
    return rows


def _button_rows(screen: dict[str, Any], start_no: int) -> list[_FeatureRow]:
    rows: list[_FeatureRow] = []
    label = _screen_label(screen)
    no = start_no
    for button in screen.get("buttons") or []:
        text = str(button).strip()
        if not text:
            continue
        rows.append((f"F{no:03d}", "操作機能", label, f"「{text}」操作"))
        no += 1
    return rows


def _transition_rows(screen: dict[str, Any], start_no: int) -> list[_FeatureRow]:
    rows: list[_FeatureRow] = []
    page_id = str(screen.get("page_id") or "")
    transitions = screen.get("transitions") or {}
    to_ids = transitions.get("to") or []
    for idx, to_id in enumerate(to_ids):
        rows.append(
            (
                f"F{start_no + idx:03d}",
                "遷移機能",
                _screen_label(screen),
                f"{page_id} → {to_id} への画面遷移",
            )
        )
    return rows


def generate_features_markdown(screens: list[dict[str, Any]]) -> str:
    """画面一覧から機能一覧（機能ID/種別/画面/概要）のMarkdown表を生成する。"""
    rows: list[_FeatureRow] = []
    for screen in screens:
        rows.extend(_form_rows(screen, len(rows) + 1))
        rows.extend(_button_rows(screen, len(rows) + 1))
        rows.extend(_transition_rows(screen, len(rows) + 1))

    lines = [
        "# 機能一覧",
        "",
        "画面・フォーム・遷移から導出した機能の一覧です"
        "（推測を含まず、report.json の実測データのみを機械的に集計しています）。",
        "",
        "| 機能ID | 種別 | 画面 | 概要 |",
        "|---|---|---|---|",
    ]
    if rows:
        lines.extend(
            f"| {fid} | {kind} | {screen} | {summary} |" for fid, kind, screen, summary in rows
        )
    else:
        lines.append("| — | — | — | 機能を抽出できませんでした |")
    lines.append("")
    return "\n".join(lines)
