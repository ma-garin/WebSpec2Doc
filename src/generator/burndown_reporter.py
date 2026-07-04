"""探索カバレッジ進捗バーンダウンの HTML 生成。

自己完結の単一 HTML を生成する（外部リソース参照なし）。未探索の残数
（画面・状態）2 系列を SVG 折れ線で描く。配色は heatmap_reporter の
検証済みパレット（ライト/ダーク両モード検証 PASS）を流用する
（同層 generator 内の import なので層分離違反にならない）。

推定日時の点（estimated=True）は破線マーカー＋「推定」ラベルを併記し、
色だけに意味を持たせない（evidence-only 原則）。
"""

from __future__ import annotations

import html
from typing import Any

from generator.heatmap_reporter import _DARK_RAMP, _LIGHT_RAMP

BURNDOWN_FILE_NAME = "exploration_burndown.html"

_CHART_WIDTH = 640
_CHART_HEIGHT = 240
_PAD_LEFT = 48
_PAD_RIGHT = 16
_PAD_TOP = 16
_PAD_BOTTOM = 32

# heatmap の 4 段パレットのうち最も濃い色を「未探索画面」、次点を「未到達状態」に割り当てる
_SCREENS_LIGHT = _LIGHT_RAMP[3]
_SCREENS_DARK = _DARK_RAMP[2]
_STATES_LIGHT = _LIGHT_RAMP[1]
_STATES_DARK = _DARK_RAMP[3]


def _scale(value: float, max_value: float, axis_len: float) -> float:
    if max_value <= 0:
        return 0.0
    return (value / max_value) * axis_len


def _points_to_path(points: list[tuple[float, float]]) -> str:
    if not points:
        return ""
    segments = [f"{points[0][0]:.1f},{points[0][1]:.1f}"]
    segments.extend(f"{x:.1f},{y:.1f}" for x, y in points[1:])
    return "M" + " L".join(segments) if len(points) > 1 else f"M{segments[0]}"


def _build_series_svg(
    points: list[dict[str, Any]],
    key: str,
    color_light: str,
    color_dark: str,
    max_value: int,
) -> tuple[str, str]:
    """1 系列分の折れ線 SVG（path + マーカー）を返す（ライト用 class 付き共通マークアップ）。"""
    axis_w = _CHART_WIDTH - _PAD_LEFT - _PAD_RIGHT
    axis_h = _CHART_HEIGHT - _PAD_TOP - _PAD_BOTTOM
    n = len(points)
    coords: list[tuple[float, float]] = []
    for i, point in enumerate(points):
        x = _PAD_LEFT + (axis_w * i / (n - 1) if n > 1 else axis_w / 2)
        value = float(point[key])
        y = _PAD_TOP + axis_h - _scale(value, max_value, axis_h)
        coords.append((x, y))

    path = _points_to_path(coords)
    var_name = f"--{key}-color"
    line = f'<path d="{html.escape(path)}" fill="none" stroke="var({var_name})" stroke-width="2"/>'
    markers = []
    for (x, y), point in zip(coords, points, strict=False):
        estimated = bool(point.get("estimated"))
        dash = ' stroke-dasharray="2,2"' if estimated else ""
        title = (
            f"{point['session']}: {point['at']}"
            + ("（推定）" if estimated else "")
            + f" / {key}={point[key]}"
        )
        markers.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="var({var_name})"{dash}>'
            f"<title>{html.escape(title)}</title></circle>"
        )
    css = (
        f":root {{ {var_name}: {color_light}; }}\n"
        f"@media (prefers-color-scheme: dark) {{ :root {{ {var_name}: {color_dark}; }} }}"
    )
    return line + "".join(markers), css


def generate_burndown_html(burndown: dict[str, Any]) -> str:
    """バーンダウン集計から自己完結の折れ線 HTML を生成する。"""
    summary = burndown.get("summary") or {}
    points = list(burndown.get("points") or [])
    total_screens = int(summary.get("total_screens") or 0)
    total_states = int(summary.get("total_states") or 0)
    note = str(summary.get("note") or "")

    estimated_points = [p for p in points if p.get("estimated")]

    if not points:
        chart_html = "<p>系列データがありません（セッションが 0 件）。</p>"
        css_vars = ""
    else:
        screens_svg, screens_css = _build_series_svg(
            points, "remaining_screens", _SCREENS_LIGHT, _SCREENS_DARK, max(total_screens, 1)
        )
        states_svg, states_css = _build_series_svg(
            points, "remaining_states", _STATES_LIGHT, _STATES_DARK, max(total_states, 1)
        )
        axis_w = _CHART_WIDTH - _PAD_LEFT - _PAD_RIGHT
        x_labels = "".join(
            f'<text x="{_PAD_LEFT + (axis_w * i / (len(points) - 1) if len(points) > 1 else axis_w / 2):.1f}" '
            f'y="{_CHART_HEIGHT - 8}" font-size="10" text-anchor="middle" fill="var(--ink-2)">'
            f"{i + 1}{'（推定）' if p.get('estimated') else ''}</text>"
            for i, p in enumerate(points)
        )
        chart_html = (
            f'<svg viewBox="0 0 {_CHART_WIDTH} {_CHART_HEIGHT}" role="img" '
            f'aria-label="探索カバレッジ残数の推移">'
            f'<line x1="{_PAD_LEFT}" y1="{_PAD_TOP}" x2="{_PAD_LEFT}" '
            f'y2="{_CHART_HEIGHT - _PAD_BOTTOM}" stroke="var(--line)"/>'
            f'<line x1="{_PAD_LEFT}" y1="{_CHART_HEIGHT - _PAD_BOTTOM}" '
            f'x2="{_CHART_WIDTH - _PAD_RIGHT}" y2="{_CHART_HEIGHT - _PAD_BOTTOM}" stroke="var(--line)"/>'
            f"{screens_svg}{states_svg}{x_labels}"
            "</svg>"
        )
        css_vars = screens_css + "\n" + states_css

    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(p.get('session') or ''))}</td>"
        f"<td>{html.escape(str(p.get('at') or ''))}"
        + (' <span class="est">推定</span>' if p.get("estimated") else "")
        + "</td>"
        f"<td>{int(p.get('explored_screens') or 0)}</td>"
        f"<td>{int(p.get('remaining_screens') or 0)}</td>"
        f"<td>{int(p.get('touched_states') or 0)}</td>"
        f"<td>{int(p.get('remaining_states') or 0)}</td>"
        f"<td>{float(p.get('coverage_ratio') or 0.0):.0%}</td>"
        "</tr>"
        for p in points
    )

    estimated_note_html = ""
    if estimated_points:
        estimated_note_html = (
            '<p class="caption est-note">⚠ 「推定」と表示された点は '
            "元セッションに記録時刻（ts）が無かったため、"
            "ファイル更新時刻からの推定日時です。</p>"
        )

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>探索カバレッジ進捗バーンダウン</title>
<style>
:root {{
  --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --line: #e5e4e0;
}}
@media (prefers-color-scheme: dark) {{
  :root {{ --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --line: #383835; }}
}}
{css_vars}
body {{ margin: 0; padding: 24px; background: var(--surface); color: var(--ink);
  font-family: "Hiragino Sans", "Noto Sans JP", Meiryo, sans-serif; }}
h1 {{ font-size: 20px; margin: 0 0 4px; }}
p.caption {{ color: var(--ink-2); margin: 0 0 12px; font-size: 13px; }}
p.est-note {{ color: var(--ink-2); }}
.chart {{ max-width: {_CHART_WIDTH}px; margin-bottom: 16px; }}
svg {{ width: 100%; height: auto; }}
.legend {{ display: flex; gap: 16px; font-size: 12px; color: var(--ink-2); margin-bottom: 16px; }}
.legend i {{ display: inline-block; width: 12px; height: 12px; border-radius: 2px;
  margin-right: 4px; vertical-align: middle; }}
.legend i.screens {{ background: var(--remaining_screens-color); }}
.legend i.states {{ background: var(--remaining_states-color); }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border: 1px solid var(--line); padding: 6px 10px; text-align: left; }}
th {{ color: var(--ink-2); font-weight: 600; }}
.est {{ color: var(--ink-2); font-size: 11px; border: 1px solid var(--line);
  border-radius: 3px; padding: 0 4px; }}
</style>
</head>
<body>
<h1>探索カバレッジ進捗バーンダウン</h1>
<p class="caption">分母（総画面数 {total_screens} ・総状態数 {total_states}）は最新の report.json
に対するもの。{html.escape(note)}</p>
<div class="legend">
  <span><i class="screens"></i>残り未探索画面数</span>
  <span><i class="states"></i>残り未到達状態数</span>
</div>
<div class="chart">{chart_html}</div>
{estimated_note_html}
<table>
<thead><tr><th>セッション</th><th>日時</th><th>探索済み画面</th><th>残り画面</th>
<th>到達状態</th><th>残り状態</th><th>画面カバレッジ</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
</body>
</html>
"""
