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
ANALYSIS_COVERAGE_FILE_NAME = "analysis_coverage_heatmap.html"
AUTORUN_COVERAGE_FILE_NAME = "autorun_coverage_heatmap.html"

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

    charters_html = _render_charters(coverage.get("charters"))

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
{charters_html}
{unmatched_html}
</body>
</html>
"""


def _render_charters(charters: object) -> str:
    """探索チャーター提案セクションを描画する（charters 未指定時は空文字）。"""
    if not isinstance(charters, list) or not charters:
        return ""
    rows = []
    for charter in charters:
        if not isinstance(charter, dict):
            continue
        flows = charter.get("flows") or []
        flow_text = "、".join(
            f"{f.get('flow_name', '')}（{f.get('path_id', '')}）"
            for f in flows
            if isinstance(f, dict)
        )
        priority = str(charter.get("priority") or "")
        priority_class = "warn" if priority == "高" else "ok"
        rows.append(
            "<tr>"
            f"<td class=\"pid\">{html.escape(str(charter.get('page_id') or ''))}</td>"
            f"<td>{html.escape(str(charter.get('title') or ''))}"
            f"<span class=\"url\">{html.escape(str(charter.get('url') or ''))}</span></td>"
            f"<td>{html.escape(str(charter.get('reason') or ''))}</td>"
            f"<td>{html.escape(flow_text) if flow_text else '—'}</td>"
            f'<td class="status {priority_class}">{html.escape(priority)}</td>'
            "</tr>"
        )
    if not rows:
        return ""
    return (
        "<section><h2>次の探索チャーター（提案）</h2>"
        "<p>未探索画面のうち、ビジネスフロー通過画面を優先度「高」として提案します。</p>"
        "<table><thead><tr><th>ID</th><th>画面</th><th>理由</th>"
        "<th>根拠（フロー）</th><th>優先度</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></section>"
    )


# ---------------------------------------------------------------------------
# カバレッジヒートマップ（解析＝取得状況 / AutoRun＝実行回数×成否）
#
# 色だけに意味を持たせない（アクセシビリティ）ため、各セルはアイコンと
# ラベルを併記する。配色は検証済みリファレンスパレット準拠。
# ---------------------------------------------------------------------------

# 解析カバレッジの 3 分類（取得済み / 要ログイン / 未取得）
_ANALYSIS_STATUS = {
    "captured": ("✓ 取得済み", "captured"),
    "login": ("🔒 要ログイン", "login"),
    "missing": ("— 未取得", "missing"),
}

# AutoRun カバレッジの成否分類
_AUTORUN_STATUS = {
    "pass": ("✓ 全て成功", "pass"),
    "fail": ("✗ 失敗あり", "fail"),
    "none": ("— 未実行", "none"),
}


def classify_analysis_status(screen: dict[str, Any]) -> str:
    """画面の取得状況を 'captured' / 'login' / 'missing' に分類する（純関数）。

    取得済み（スクショ実在）を最優先。未取得のうちログインウォール検出済みの
    ものは 'login'、それ以外は 'missing'。
    """
    captured = bool(
        screen.get("captured") or screen.get("has_screenshot") or screen.get("screenshot")
    )
    if captured:
        return "captured"
    if screen.get("requires_login") or screen.get("is_login_required"):
        return "login"
    return "missing"


def classify_autorun_status(runs: int, passed: int, failed: int) -> str:
    """実行回数と成否から 'pass' / 'fail' / 'none' に分類する（純関数）。"""
    if runs <= 0:
        return "none"
    if failed > 0:
        return "fail"
    return "pass"


def _analysis_cell(screen: dict[str, Any]) -> str:
    key = classify_analysis_status(screen)
    label, cls = _ANALYSIS_STATUS[key]
    return f'<td class="cov {cls}">{label}</td>'


def _autorun_cell(runs: int, passed: int, failed: int) -> str:
    key = classify_autorun_status(runs, passed, failed)
    label, cls = _AUTORUN_STATUS[key]
    level = _bucket(runs)
    lvl_attr = f' data-runs="{level}"' if level else ""
    detail = f"{passed} 成功 / {failed} 失敗" if runs > 0 else "未実行"
    return (
        f'<td class="cov autorun {cls}"{lvl_attr} '
        f'title="{html.escape(detail)}">{label}'
        f'<span class="runs">{runs} 回</span></td>'
    )


def _screen_label_cells(screen: dict[str, Any]) -> str:
    return (
        f"<td class=\"pid\">{html.escape(str(screen.get('page_id') or ''))}</td>"
        f"<td class=\"name\">{html.escape(str(screen.get('title') or ''))}"
        f"<span class=\"url\">{html.escape(str(screen.get('url') or ''))}</span></td>"
    )


_COVERAGE_BASE_CSS = """
body { margin: 0; padding: 24px; background: var(--surface); color: var(--ink);
  font-family: "Hiragino Sans", "Noto Sans JP", Meiryo, sans-serif; }
:root { --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --line: #e5e4e0; }
@media (prefers-color-scheme: dark) {
  :root { --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --line: #383835; }
}
h1 { font-size: 20px; margin: 0 0 4px; }
p.caption { color: var(--ink-2); margin: 0 0 20px; font-size: 13px; }
.tiles { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }
.tile { border: 1px solid var(--line); border-radius: 8px; padding: 12px 16px; min-width: 120px; }
.tile b { display: block; font-size: 24px; }
.tile span { color: var(--ink-2); font-size: 12px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { border: 1px solid var(--line); padding: 6px 10px; text-align: left; }
th { color: var(--ink-2); font-weight: 600; }
td.pid { font-family: ui-monospace, monospace; }
td.name .url { display: block; color: var(--ink-2); font-size: 11px; }
td.cov { font-weight: 600; white-space: nowrap; }
td.cov .runs { display: block; font-size: 11px; font-weight: 400; color: var(--ink-2); }
.legend { margin: 12px 0 20px; font-size: 12px; color: var(--ink-2);
  display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
.legend-step { display: inline-flex; align-items: center; gap: 5px; }
.legend-step i { width: 14px; height: 14px; border-radius: 3px; display: inline-block;
  border: 1px solid var(--line); }
/* 取得状況 3 色（ライト/ダーク両検証済みトーン） */
.cov.captured { background: #d7f0dd; } .cov.login { background: #fdeecd; }
.cov.missing { background: #f1eeea; color: var(--ink-2); }
.i-captured { background: #d7f0dd; } .i-login { background: #fdeecd; } .i-missing { background: #f1eeea; }
/* 成否 2 軸: 色相＝成否, 濃淡＝実行回数バケット */
.cov.autorun.pass { background: #d7f0dd; }
.cov.autorun.fail { background: #f7d6d6; }
.cov.autorun.none { background: #f1eeea; color: var(--ink-2); }
.cov.autorun.pass[data-runs="2"] { background: #b7e4c4; }
.cov.autorun.pass[data-runs="3"] { background: #8fd3a6; }
.cov.autorun.pass[data-runs="4"] { background: #62c186; }
.cov.autorun.fail[data-runs="2"] { background: #f0b9b9; }
.cov.autorun.fail[data-runs="3"] { background: #e79393; }
.cov.autorun.fail[data-runs="4"] { background: #db6a6a; }
.i-pass { background: #8fd3a6; } .i-fail { background: #e79393; } .i-none { background: #f1eeea; }
@media (prefers-color-scheme: dark) {
  .cov.captured, .cov.autorun.pass { background: #1f4a2e; color: #eafff0; }
  .cov.login { background: #4a3d1c; color: #fff4d9; }
  .cov.missing, .cov.autorun.none { background: #2c2b28; color: var(--ink-2); }
  .cov.autorun.fail { background: #4d2222; color: #ffe6e6; }
  .cov.autorun.pass[data-runs="3"] { background: #2c6b41; }
  .cov.autorun.pass[data-runs="4"] { background: #388a53; }
  .cov.autorun.fail[data-runs="3"] { background: #6e2f2f; }
  .cov.autorun.fail[data-runs="4"] { background: #8a3838; }
}
"""


def _coverage_doc(title: str, caption: str, tiles: str, legend: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{_COVERAGE_BASE_CSS}</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<p class="caption">{html.escape(caption)}</p>
<div class="tiles">{tiles}</div>
<div class="legend">{legend}</div>
{body}
</body>
</html>
"""


def generate_analysis_coverage_html(screens: list[dict[str, Any]]) -> str:
    """解析カバレッジヒートマップを生成する（取得済み/要ログイン/未取得の 3 色）。

    各 screen は少なくとも page_id/title/url を持ち、取得状況は
    captured/has_screenshot/screenshot（取得済み）と
    requires_login/is_login_required（要ログイン）から判定する。
    """
    screens = screens or []
    counts = {"captured": 0, "login": 0, "missing": 0}
    rows: list[str] = []
    for screen in screens:
        counts[classify_analysis_status(screen)] += 1
        rows.append("<tr>" + _screen_label_cells(screen) + _analysis_cell(screen) + "</tr>")

    total = len(screens)
    ratio = counts["captured"] / total if total else 0.0
    tiles = (
        f'<div class="tile"><b>{total}</b><span>総画面数</span></div>'
        f'<div class="tile"><b>{counts["captured"]}</b><span>取得済み</span></div>'
        f'<div class="tile"><b>{counts["login"]}</b><span>要ログイン</span></div>'
        f'<div class="tile"><b>{counts["missing"]}</b><span>未取得</span></div>'
        f'<div class="tile"><b>{ratio:.0%}</b><span>取得率</span></div>'
    )
    legend = (
        "取得状況: "
        '<span class="legend-step"><i class="i-captured"></i>取得済み</span>'
        '<span class="legend-step"><i class="i-login"></i>要ログイン</span>'
        '<span class="legend-step"><i class="i-missing"></i>未取得</span>'
    )
    body = (
        "<table><thead><tr><th>ID</th><th>画面</th><th>取得状況</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    return _coverage_doc(
        "解析カバレッジヒートマップ",
        f"クロールで検出した {total} 画面の取得状況。要ログインは認証未確立で未取得の画面。",
        tiles,
        legend,
        body,
    )


def generate_autorun_coverage_html(screens: list[dict[str, Any]]) -> str:
    """AutoRun カバレッジヒートマップを生成する（実行回数×成否の 2 軸配色）。

    各 screen は page_id/title/url に加え runs（実行回数）/passed/failed を持つ。
    色相は成否（成功=緑/失敗=赤/未実行=灰）、濃淡は実行回数バケット（_bucket）。
    """
    screens = screens or []
    total_runs = 0
    total_passed = 0
    total_failed = 0
    executed = 0
    rows: list[str] = []
    for screen in screens:
        runs = int(screen.get("runs") or 0)
        passed = int(screen.get("passed") or 0)
        failed = int(screen.get("failed") or 0)
        total_runs += runs
        total_passed += passed
        total_failed += failed
        if runs > 0:
            executed += 1
        rows.append(
            "<tr>" + _screen_label_cells(screen) + _autorun_cell(runs, passed, failed) + "</tr>"
        )

    total = len(screens)
    exec_ratio = executed / total if total else 0.0
    pass_ratio = total_passed / total_runs if total_runs else 0.0
    tiles = (
        f'<div class="tile"><b>{total}</b><span>総画面数</span></div>'
        f'<div class="tile"><b>{executed}</b><span>実行済み画面</span></div>'
        f'<div class="tile"><b>{exec_ratio:.0%}</b><span>実行カバレッジ</span></div>'
        f'<div class="tile"><b>{total_runs}</b><span>総実行回数</span></div>'
        f'<div class="tile"><b>{pass_ratio:.0%}</b><span>成功率</span></div>'
    )
    legend = (
        "成否（色相）: "
        '<span class="legend-step"><i class="i-pass"></i>成功</span>'
        '<span class="legend-step"><i class="i-fail"></i>失敗あり</span>'
        '<span class="legend-step"><i class="i-none"></i>未実行</span>'
        "　濃いほど実行回数が多い"
    )
    body = (
        "<table><thead><tr><th>ID</th><th>画面</th><th>実行回数×成否</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    return _coverage_doc(
        "AutoRun カバレッジヒートマップ",
        f"画面ごとのテスト実行回数と成否。{total} 画面中 {executed} 画面を実行。",
        tiles,
        legend,
        body,
    )
