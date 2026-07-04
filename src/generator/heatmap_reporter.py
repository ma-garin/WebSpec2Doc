"""探索カバレッジヒートマップの HTML 生成。

自己完結の単一 HTML を生成する（外部リソース参照なし）。配色は
検証済みリファレンスパレットの sequential blue（ordinal 4 段・ライト/ダーク
両モード検証 PASS）を回数の濃淡に、status 色は「未探索」の警告にのみ使う。
未探索はアイコン＋ラベルを併記し、色だけに意味を持たせない。
"""

from __future__ import annotations

import html
from typing import Any

HEATMAP_FILE_NAME = "exploration_heatmap.html"

# ordinal 4 段（validate_palette.js で light/dark とも PASS 済み）
_LIGHT_RAMP = ("#86b6ef", "#3987e5", "#1c5cab", "#0d366b")
_DARK_RAMP = ("#184f95", "#2a78d6", "#6da7ec", "#b7d3f6")
_BUCKET_LABELS = ("1", "2〜3", "4〜6", "7+")


def _bucket(count: int) -> int:
    """回数を 0〜4 の段階に割り当てる（0 = 触られていない）。"""
    if count <= 0:
        return 0
    if count == 1:
        return 1
    if count <= 3:
        return 2
    if count <= 6:
        return 3
    return 4


def _cell(count: int, label: str) -> str:
    bucket = _bucket(count)
    css = f' data-level="{bucket}"' if bucket else ""
    return f'<td class="count"{css} title="{html.escape(label)}: {count} 回">' f"{count}</td>"


def generate_heatmap_html(coverage: dict[str, Any]) -> str:
    """カバレッジ集計から自己完結ヒートマップ HTML を生成する。"""
    summary = coverage.get("summary") or {}
    screens = coverage.get("screens") or []
    unmatched = coverage.get("unmatched_footprints") or []

    rows: list[str] = []
    for screen in screens:
        states = screen.get("states") or []
        touched = sum(1 for s in states if s.get("touched"))
        states_cell = f"{touched}/{len(states)}" if states else "—"
        status = (
            '<td class="status ok">探索済み</td>'
            if screen.get("explored")
            else '<td class="status warn">⚠ 未探索</td>'
        )
        rows.append(
            "<tr>"
            f"<td class=\"pid\">{html.escape(str(screen.get('page_id') or ''))}</td>"
            f"<td class=\"name\">{html.escape(str(screen.get('title') or ''))}"
            f"<span class=\"url\">{html.escape(str(screen.get('url') or ''))}</span></td>"
            + _cell(int(screen.get("visits") or 0), "訪問")
            + _cell(int(screen.get("actions") or 0), "操作")
            + f'<td class="states" title="触られた状態 / 検出済み状態">{states_cell}</td>'
            + status
            + "</tr>"
        )

    unmatched_html = ""
    if unmatched:
        items = "".join(
            f"<li><code>{html.escape(str(u.get('path') or ''))}</code>"
            f"（{int(u.get('visits') or 0)} 回訪問）</li>"
            for u in unmatched
        )
        unmatched_html = (
            "<section><h2>地図にない足跡</h2>"
            "<p>探索されたがクロール済みインベントリに存在しないパスです。"
            "クロール範囲の拡張候補になります。</p>"
            f"<ul>{items}</ul></section>"
        )

    legend_steps = "".join(
        f'<span class="legend-step"><i data-level="{level}"></i>{label}</span>'
        for level, label in enumerate(_BUCKET_LABELS, start=1)
    )
    ratio = float(summary.get("coverage_ratio") or 0.0)

    light_css = "".join(
        f'.count[data-level="{i}"]{{background:{color};'
        f'color:{"#0b0b0b" if i <= 2 else "#ffffff"}}}'
        f'.legend-step i[data-level="{i}"]{{background:{color}}}'
        for i, color in enumerate(_LIGHT_RAMP, start=1)
    )
    dark_css = "".join(
        f'.count[data-level="{i}"]{{background:{color};'
        f'color:{"#ffffff" if i <= 2 else "#0b0b0b"}}}'
        f'.legend-step i[data-level="{i}"]{{background:{color}}}'
        for i, color in enumerate(_DARK_RAMP, start=1)
    )

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>探索カバレッジヒートマップ</title>
<style>
:root {{
  --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e;
  --line: #e5e4e0; --warn: #d03b3b; --ok: #0ca30c;
}}
@media (prefers-color-scheme: dark) {{
  :root {{ --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --line: #383835; }}
}}
body {{ margin: 0; padding: 24px; background: var(--surface); color: var(--ink);
  font-family: "Hiragino Sans", "Noto Sans JP", Meiryo, sans-serif; }}
h1 {{ font-size: 20px; margin: 0 0 4px; }}
p.caption {{ color: var(--ink-2); margin: 0 0 20px; font-size: 13px; }}
.tiles {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }}
.tile {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px 16px; min-width: 120px; }}
.tile b {{ display: block; font-size: 24px; }}
.tile span {{ color: var(--ink-2); font-size: 12px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border: 1px solid var(--line); padding: 6px 10px; text-align: left; }}
th {{ color: var(--ink-2); font-weight: 600; background: transparent; }}
td.count {{ text-align: right; font-variant-numeric: tabular-nums; min-width: 48px; }}
td.pid {{ font-family: ui-monospace, monospace; }}
td.name .url {{ display: block; color: var(--ink-2); font-size: 11px; }}
td.states {{ text-align: center; font-variant-numeric: tabular-nums; }}
td.status.warn {{ color: var(--warn); font-weight: 600; }}
td.status.ok {{ color: var(--ink-2); }}
tr:hover td {{ outline: 2px solid var(--line); outline-offset: -2px; }}
.legend {{ margin: 12px 0 20px; font-size: 12px; color: var(--ink-2);
  display: flex; gap: 12px; align-items: center; }}
.legend-step {{ display: inline-flex; align-items: center; gap: 4px; }}
.legend-step i {{ width: 14px; height: 14px; border-radius: 3px; display: inline-block; }}
section {{ margin-top: 24px; }}
h2 {{ font-size: 16px; }}
code {{ background: transparent; border: 1px solid var(--line); border-radius: 4px;
  padding: 1px 4px; }}
{light_css}
@media (prefers-color-scheme: dark) {{ {dark_css} }}
</style>
</head>
<body>
<h1>探索カバレッジヒートマップ</h1>
<p class="caption">クロール済みインベントリ（分母）に探索セッションの足跡（分子）を重ねた結果。
セッションイベント {int(summary.get("session_events") or 0)} 件から集計。</p>
<div class="tiles">
  <div class="tile"><b>{int(summary.get("total_screens") or 0)}</b><span>総画面数（分母）</span></div>
  <div class="tile"><b>{int(summary.get("explored_screens") or 0)}</b><span>探索済み画面</span></div>
  <div class="tile"><b>{ratio:.0%}</b><span>画面カバレッジ</span></div>
  <div class="tile"><b>{int(summary.get("touched_states") or 0)}/{int(summary.get("total_states") or 0)}</b><span>画面状態カバー</span></div>
</div>
<div class="legend">触られた回数: <span class="legend-step"><i style="border:1px solid var(--line)"></i>0</span>{legend_steps}</div>
<table>
<thead><tr><th>ID</th><th>画面</th><th>訪問</th><th>操作</th><th>状態</th><th>判定</th></tr></thead>
<tbody>
{"".join(rows)}
</tbody>
</table>
{unmatched_html}
</body>
</html>
"""
