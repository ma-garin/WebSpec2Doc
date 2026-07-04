"""現新比較レポート（comparison.json / comparison.html）の生成。

report.json とは別ファイルに出力し、既存スキーマ・report_hash には一切影響しない
（比較モード未使用時は本モジュール自体が呼ばれず、report.json は byte-identical のまま）。
"""

from __future__ import annotations

import html
import json
import logging
from pathlib import Path
from typing import Any

from crawler.page_crawler import evidence_to_dict
from diff.comparison import ComparisonFinding, ComparisonResult

logger = logging.getLogger(__name__)

COMPARISON_JSON_FILE_NAME = "comparison.json"
COMPARISON_HTML_FILE_NAME = "comparison.html"

_CATEGORY_LABELS: dict[str, str] = {
    "layout_broken": "表示崩れ",
    "text_garbled": "文字化け・意味消失",
    "incomprehensible": "理解不可能",
    "inoperable": "操作不可",
    "unclassified": "未分類（要確認）",
}
_CATEGORY_ORDER: tuple[str, ...] = (
    "inoperable",
    "incomprehensible",
    "text_garbled",
    "layout_broken",
    "unclassified",
)


def _pair_to_dict(pair: Any) -> dict[str, object] | None:
    if pair is None:
        return None
    return {
        "old_page_id": pair.old_page_id,
        "new_page_id": pair.new_page_id,
        "score": pair.score,
        "method": pair.method,
    }


def _finding_to_dict(finding: ComparisonFinding) -> dict[str, object]:
    return {
        "category": finding.category,
        "page_pair": _pair_to_dict(finding.page_pair),
        "detail": finding.detail,
        "old_evidence": evidence_to_dict(finding.old_evidence),
        "new_evidence": evidence_to_dict(finding.new_evidence),
        "severity": finding.severity,
        "confidence": finding.confidence,
    }


def comparison_result_to_dict(result: ComparisonResult) -> dict[str, object]:
    """ComparisonResult を JSON シリアライズ可能な dict に変換する。"""
    return {
        "pairs": [_pair_to_dict(p) for p in result.pairs],
        "added_page_ids": list(result.added_page_ids),
        "removed_page_ids": list(result.removed_page_ids),
        "findings": [_finding_to_dict(f) for f in result.findings],
        "screenshot_diffs": [
            {
                "page_id": d.page_id,
                "before_path": d.before_path,
                "after_path": d.after_path,
                "diff_ratio": d.diff_ratio,
                "is_significant": d.is_significant,
            }
            for d in result.screenshot_diffs
        ],
    }


def generate_comparison_json(result: ComparisonResult) -> str:
    """comparison.json の内容（文字列）を生成する。"""
    return json.dumps(comparison_result_to_dict(result), ensure_ascii=False, indent=2)


def generate_comparison_html(result: ComparisonResult) -> str:
    """自己完結の comparison.html（4 分類×画面マトリクス）を生成する。"""
    summary_tiles = _render_summary_tiles(result)
    findings_by_category: dict[str, list[ComparisonFinding]] = {
        category: [] for category in _CATEGORY_ORDER
    }
    for finding in result.findings:
        findings_by_category.setdefault(finding.category, []).append(finding)

    sections = "".join(
        _render_category_section(category, findings_by_category.get(category, []))
        for category in _CATEGORY_ORDER
    )
    added_removed = _render_added_removed(result)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>現新比較レポート</title>
<style>
:root {{
  --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e;
  --line: #e5e4e0; --breaking: #d03b3b; --warning: #b8860b; --info: #52514e;
}}
@media (prefers-color-scheme: dark) {{
  :root {{ --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --line: #383835;
    --breaking: #ff6b6b; --warning: #e0b84d; --info: #c3c2b7; }}
}}
body {{ margin: 0; padding: 24px; background: var(--surface); color: var(--ink);
  font-family: "Hiragino Sans", "Noto Sans JP", Meiryo, sans-serif; }}
h1 {{ font-size: 20px; margin: 0 0 4px; }}
h2 {{ font-size: 16px; margin: 28px 0 8px; }}
p.caption {{ color: var(--ink-2); margin: 0 0 20px; font-size: 13px; }}
.tiles {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }}
.tile {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px 16px; min-width: 120px; }}
.tile b {{ display: block; font-size: 24px; }}
.tile span {{ color: var(--ink-2); font-size: 12px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; margin-bottom: 8px; }}
th, td {{ border: 1px solid var(--line); padding: 6px 10px; text-align: left; vertical-align: top; }}
th {{ color: var(--ink-2); font-weight: 600; }}
.severity-breaking {{ color: var(--breaking); font-weight: 600; }}
.severity-warning {{ color: var(--warning); font-weight: 600; }}
.severity-info {{ color: var(--info); }}
code {{ background: transparent; border: 1px solid var(--line); border-radius: 4px;
  padding: 1px 4px; font-size: 12px; }}
.empty {{ color: var(--ink-2); font-size: 13px; }}
</style>
</head>
<body>
<h1>現新比較レポート</h1>
<p class="caption">現行 URL と新 URL を実測クロールし、画面対応付け・仕様差分・画像差分・
リンク切れ検査から想定不具合 4 分類で報告します。分類できない差分は「未分類（要確認）」です。</p>
{summary_tiles}
{sections}
{added_removed}
</body>
</html>
"""


def _render_summary_tiles(result: ComparisonResult) -> str:
    counts = {category: 0 for category in _CATEGORY_ORDER}
    for finding in result.findings:
        counts[finding.category] = counts.get(finding.category, 0) + 1
    tiles = "".join(
        f'<div class="tile"><b>{counts.get(category, 0)}</b>'
        f"<span>{html.escape(_CATEGORY_LABELS.get(category, category))}</span></div>"
        for category in _CATEGORY_ORDER
    )
    return (
        '<div class="tiles">'
        f'<div class="tile"><b>{len(result.pairs)}</b><span>対応画面ペア</span></div>'
        f'<div class="tile"><b>{len(result.added_page_ids)}</b><span>新規追加画面</span></div>'
        f'<div class="tile"><b>{len(result.removed_page_ids)}</b><span>削除画面</span></div>'
        f"{tiles}</div>"
    )


def _severity_class(severity: str) -> str:
    return f"severity-{html.escape(severity)}" if severity else ""


def _render_category_section(category: str, findings: list[ComparisonFinding]) -> str:
    label = _CATEGORY_LABELS.get(category, category)
    if not findings:
        return f'<h2>{html.escape(label)}</h2><p class="empty">該当なし</p>'
    rows = []
    for finding in findings:
        pair = finding.page_pair
        pair_text = f"{pair.old_page_id} ⇔ {pair.new_page_id}" if pair is not None else "—"
        old_shot = finding.old_evidence.screenshot_path if finding.old_evidence else None
        new_shot = finding.new_evidence.screenshot_path if finding.new_evidence else None
        rows.append(
            "<tr>"
            f'<td class="{_severity_class(finding.severity)}">{html.escape(finding.severity)}</td>'
            f"<td>{html.escape(pair_text)}</td>"
            f"<td>{html.escape(finding.detail)}</td>"
            f"<td><code>{html.escape(old_shot or '未取得')}</code></td>"
            f"<td><code>{html.escape(new_shot or '未取得')}</code></td>"
            f"<td>{finding.confidence:.1f}</td>"
            "</tr>"
        )
    return (
        f"<h2>{html.escape(label)}（{len(findings)} 件）</h2>"
        "<table><thead><tr><th>重大度</th><th>画面ペア</th><th>詳細</th>"
        "<th>現行 evidence</th><th>新 evidence</th><th>confidence</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _render_added_removed(result: ComparisonResult) -> str:
    if not result.added_page_ids and not result.removed_page_ids:
        return ""
    added = "".join(f"<li><code>{html.escape(pid)}</code></li>" for pid in result.added_page_ids)
    removed = "".join(
        f"<li><code>{html.escape(pid)}</code></li>" for pid in result.removed_page_ids
    )
    return (
        "<h2>対応画面が見つからなかった画面</h2>"
        f'<div class="tiles"><div class="tile"><b>新規追加（新のみ）</b><ul>{added or "<li>なし</li>"}</ul></div>'
        f'<div class="tile"><b>削除（現行のみ）</b><ul>{removed or "<li>なし</li>"}</ul></div></div>'
    )


def save_comparison_outputs(result: ComparisonResult, output_dir: Path) -> tuple[Path, Path]:
    """comparison.json / comparison.html を output_dir に保存し、パスを返す。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / COMPARISON_JSON_FILE_NAME
    html_path = output_dir / COMPARISON_HTML_FILE_NAME
    json_path.write_text(generate_comparison_json(result), encoding="utf-8")
    html_path.write_text(generate_comparison_html(result), encoding="utf-8")
    logger.info("現新比較レポートを保存しました: %s / %s", json_path, html_path)
    return json_path, html_path
