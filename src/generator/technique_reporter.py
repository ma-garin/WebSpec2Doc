"""テスト設計技法の Markdown エクスポート。

report.json 形式の screen 辞書（techniques 埋め込み済み、または未埋め込み）から、
技法マトリクスと画面別の推奨技法・根拠・テストケース雛形を Markdown で出力する。
技法が埋め込まれていない screen は technique_recommender で再計算する。
"""

from __future__ import annotations

from analyzer.technique_recommender import (
    _TECHNIQUE_META,
    TECHNIQUE_KEYS,
    techniques_for_screen,
)


def _techniques(screen: dict) -> list[dict]:
    embedded = screen.get("techniques")
    if isinstance(embedded, list):
        return embedded
    return techniques_for_screen(screen)


def _matrix_table(screens: list[dict]) -> str:
    abbrs = [_TECHNIQUE_META[k][1] for k in TECHNIQUE_KEYS]
    header = "| 画面 | タイトル | " + " | ".join(abbrs) + " |"
    sep = "| --- | --- | " + " | ".join("---" for _ in TECHNIQUE_KEYS) + " |"
    rows = [header, sep]
    for sc in screens:
        keys = {t["key"] for t in _techniques(sc)}
        cells = ["✓" if k in keys else "—" for k in TECHNIQUE_KEYS]
        title = str(sc.get("title") or "").replace("|", "／")
        rows.append(f"| {sc.get('page_id', '')} | {title} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def _legend() -> str:
    items = [f"`{_TECHNIQUE_META[k][1]}` = {_TECHNIQUE_META[k][0]}" for k in TECHNIQUE_KEYS]
    return "凡例: " + " / ".join(items)


def _screen_section(screen: dict) -> str:
    techs = _techniques(screen)
    page_id = screen.get("page_id", "")
    title = screen.get("title") or ""
    url = screen.get("url") or ""
    lines = [f"### {page_id} {title}".rstrip(), "", f"<{url}>", ""]
    if not techs:
        lines.append("推奨技法なし（フォーム・遷移がない画面）")
        lines.append("")
        return "\n".join(lines)
    for t in techs:
        lines.append(f"#### {t['label']}")
        lines.append("")
        for reason in t.get("rationale") or []:
            lines.append(f"- {reason}")
        stub = (t.get("case_stub") or "").strip()
        if stub:
            lines.append("")
            lines.append("テストケース雛形:")
            lines.append("")
            lines.append("```")
            lines.append(stub)
            lines.append("```")
        lines.append("")
    return "\n".join(lines)


def generate_techniques_markdown(screens: list[dict]) -> str:
    """技法マトリクス＋画面別推奨の Markdown を返す。"""
    parts = [
        "# テスト設計技法",
        "",
        "稼働中の Web システムから抽出した画面要素（入力種別・制約・選択肢・遷移）",
        "に基づき、ルールベースで推奨したテスト設計技法とテストケース雛形です。",
        "",
        "## 技法マトリクス",
        "",
        _matrix_table(screens),
        "",
        _legend(),
        "",
        "## 画面別 推奨技法と根拠",
        "",
    ]
    parts.extend(_screen_section(sc) for sc in screens)
    return "\n".join(parts).rstrip() + "\n"
