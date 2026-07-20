"""証跡パックを Markdown / HTML として出力する。

外部CDNに依存しない自己完結HTMLにする（顧客環境・オフラインでも開けること）。
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

REPORT_TITLE = "テスト実施証跡パック"

RESULT_LABELS = {
    "passed": "合格",
    "failed": "不合格",
    "skipped": "スキップ",
}
CATEGORY_LABELS = {
    "env_issue": "環境起因",
    "test_rot": "テスト老朽化",
    "app_change": "アプリ変更",
    "env_setup": "環境構築",
}


def save_evidence_pack(pack: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    """evidence_pack.md と evidence_pack.html を書き出す。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "evidence_pack.md"
    html_path = out_dir / "evidence_pack.html"
    md_path.write_text(render_markdown(pack), encoding="utf-8")
    html_path.write_text(render_html(pack), encoding="utf-8")
    return {"evidence_pack_md": md_path, "evidence_pack_html": html_path}


# ─────────────────── Markdown ───────────────────


def render_markdown(pack: dict[str, Any]) -> str:
    meta = pack.get("meta", {})
    summary = pack.get("summary", {})
    lines = [
        f"# {REPORT_TITLE}",
        "",
        f"> {meta.get('claim_notice', '')}",
        "",
        f"- 生成日時: {meta.get('generated_at', '')}",
        f"- 対象: {meta.get('domain', '') or '未取得'}",
        f"- 主張範囲: `{meta.get('claim_scope', '')}`",
    ]
    missing = meta.get("missing_inputs", [])
    if missing:
        lines.append(f"- **未取得の材料**: {', '.join(str(item) for item in missing)}")
    lines += [
        "",
        "## 実行サマリー",
        "",
        "| 総数 | 合格 | 不合格 | スキップ | 所要 | 検証実行率 |",
        "|---:|---:|---:|---:|---:|---:|",
        f"| {summary.get('total', 0)} | {summary.get('passed', 0)} |"
        f" {summary.get('failed', 0)} | {summary.get('skipped', 0)} |"
        f" {summary.get('duration_sec', 0)} 秒 |"
        f" {summary.get('verification_rate', 0)}% ({summary.get('verified_cases', 0)}件) |",
        "",
        "> 検証実行率 = 値の受理／拒否・実在確認など、有意なアサーションを伴うテストの割合。"
        "「合格」件数は、対象が壊れていても body 要素が存在するだけで合格しうるため、"
        "この率と併せて読むこと。",
        "",
        "## 実行環境",
        "",
    ]
    for key, value in (pack.get("environment") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines += ["", "## テストケース別の実施記録", ""]
    lines.append("| ケースID | 名称 | 画面 | 結果 | 所要(秒) | 観点 | 失敗分類 |")
    lines.append("|---|---|---|---|---:|---|---|")
    for case in pack.get("cases", []):
        lines.append(
            f"| {case.get('case_id', '')} | {case.get('title', '')} |"
            f" {case.get('page_id', '') or '—'} |"
            f" {RESULT_LABELS.get(str(case.get('result')), case.get('result', ''))} |"
            f" {case.get('duration_sec', 0)} |"
            f" {', '.join(case.get('viewpoint_ids', [])) or '—'} |"
            f" {CATEGORY_LABELS.get(str(case.get('failure_category')), case.get('failure_category') or '—')} |"
        )
    manual = str(pack.get("manual_section", ""))
    if manual:
        lines += ["", "## 手動テストの実施手順", "", manual]
    audit = pack.get("audit_excerpt") or []
    if audit:
        lines += ["", "## 監査ログ抜粋", "", "```json"]
        lines += [json.dumps(item, ensure_ascii=False) for item in audit]
        lines.append("```")
    return "\n".join(lines) + "\n"


# ─────────────────── HTML ───────────────────


def render_html(pack: dict[str, Any]) -> str:
    meta = pack.get("meta", {})
    summary = pack.get("summary", {})
    missing = meta.get("missing_inputs", [])
    missing_block = (
        f'<p class="missing">未取得の材料: {html.escape(", ".join(str(m) for m in missing))}</p>'
        if missing
        else ""
    )
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(case.get('case_id', '')))}</td>"
        f"<td>{html.escape(str(case.get('title', '')))}</td>"
        f"<td>{html.escape(str(case.get('page_id', '')) or '—')}</td>"
        f"<td>{_result_cell(str(case.get('result', '')))}</td>"
        f"<td class=\"num\">{case.get('duration_sec', 0)}</td>"
        f"<td>{html.escape(', '.join(case.get('viewpoint_ids', [])) or '—')}</td>"
        f"<td>{html.escape(CATEGORY_LABELS.get(str(case.get('failure_category')), str(case.get('failure_category') or '—')))}</td>"
        f"<td>{_shot_cell(str(case.get('screenshot_path', '')))}</td>"
        "</tr>"
        for case in pack.get("cases", [])
    )
    env_rows = "".join(
        f"<li>{html.escape(str(key))}: <code>{html.escape(str(value))}</code></li>"
        for key, value in (pack.get("environment") or {}).items()
    )
    return f"""<!doctype html><html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(REPORT_TITLE)}</title>
<style>{_css()}</style>
</head><body>
<header><h1>{html.escape(REPORT_TITLE)}</h1>
<p class="notice">{html.escape(str(meta.get('claim_notice', '')))}</p></header>
<main>
<section><h2>概要</h2>
<ul>
<li>生成日時: {html.escape(str(meta.get('generated_at', '')))}</li>
<li>対象: {html.escape(str(meta.get('domain', '')) or '未取得')}</li>
<li>主張範囲: <code>{html.escape(str(meta.get('claim_scope', '')))}</code></li>
</ul>
{missing_block}
<div class="cards">
<div class="card"><div class="num">{summary.get('total', 0)}</div><div>総数</div></div>
<div class="card ok"><div class="num">{summary.get('passed', 0)}</div><div>合格</div></div>
<div class="card ng"><div class="num">{summary.get('failed', 0)}</div><div>不合格</div></div>
<div class="card"><div class="num">{summary.get('skipped', 0)}</div><div>スキップ</div></div>
<div class="card verif"><div class="num">{summary.get('verification_rate', 0)}%</div><div>検証実行率</div></div>
</div>
<p class="verif-note">検証実行率 = 値の受理／拒否・実在確認など、有意なアサーションを伴うテストの割合
（{summary.get('verified_cases', 0)} / {summary.get('total', 0)} 件）。
「合格」件数は対象が壊れていても body 要素が存在するだけで合格しうるため、この率と併せて読むこと。</p>
</section>
<section><h2>実行環境</h2><ul>{env_rows}</ul></section>
<section><h2>テストケース別の実施記録</h2>
<div class="scroll"><table>
<thead><tr><th>ケースID</th><th>名称</th><th>画面</th><th>結果</th><th>所要(秒)</th>
<th>観点</th><th>失敗分類</th><th>画面証跡</th></tr></thead>
<tbody>{rows}</tbody></table></div></section>
{_manual_section(pack)}
</main></body></html>"""


def _manual_section(pack: dict[str, Any]) -> str:
    manual = str(pack.get("manual_section", ""))
    if not manual:
        return ""
    return (
        "<section><h2>手動テストの実施手順</h2>"
        f"<pre class='manual'>{html.escape(manual)}</pre></section>"
    )


def _result_cell(result: str) -> str:
    label = RESULT_LABELS.get(result, result or "—")
    css = {"passed": "ok", "failed": "ng", "skipped": "sk"}.get(result, "")
    return f'<span class="pill {css}">{html.escape(label)}</span>'


def _shot_cell(path: str) -> str:
    if not path:
        return '<span class="muted">未取得</span>'
    src = html.escape(path)
    return f'<a href="{src}"><img src="{src}" alt=""></a>'


def _css() -> str:
    return """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif;color:#1b2430;background:#f5f7f9;line-height:1.7}
header{background:#00285E;color:#fff;padding:1.4rem 2rem}
header h1{font-size:1.35rem}
.notice{margin-top:.4rem;font-size:.85rem;opacity:.92}
main{max-width:1100px;margin:2rem auto;padding:0 1.5rem;display:flex;flex-direction:column;gap:1.5rem}
section{background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.08);overflow:hidden}
section h2{background:#eef2f5;padding:.7rem 1.2rem;font-size:1rem}
section>ul,section>.cards,.scroll{padding:1.2rem}
section>ul{list-style:none;display:flex;flex-direction:column;gap:.3rem;font-size:.9rem}
.missing{margin:0 1.2rem;color:#8D6B00;font-weight:700;font-size:.9rem}
.cards{display:flex;gap:1rem;flex-wrap:wrap}
.card{flex:1;min-width:120px;border:2px solid #d8e0e6;border-radius:8px;padding:.9rem;text-align:center}
.card .num{font-size:1.8rem;font-weight:700}
.card.ok{border-color:#198038}.card.ng{border-color:#DA1E28}
.card.verif{border-color:#8D6B00}.card.verif .num{color:#8D6B00}
.verif-note{margin:0 1.2rem 1.2rem;font-size:.82rem;color:#5A6572}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.88rem;min-width:760px}
th{background:#00285E;color:#fff;padding:.55rem .7rem;text-align:left;white-space:nowrap}
td{padding:.5rem .7rem;border-bottom:1px solid #eee;vertical-align:top}
td.num{font-variant-numeric:tabular-nums;text-align:right}
.pill{display:inline-block;padding:1px 8px;border-radius:10px;font-size:.8rem;background:#e0e0e0}
.pill.ok{background:#198038;color:#fff}.pill.ng{background:#DA1E28;color:#fff}.pill.sk{background:#ccc}
.muted{color:#888}
img{max-width:110px;border:1px solid #ddd;border-radius:4px;display:block}
pre.manual{padding:1.2rem;white-space:pre-wrap;font-size:.85rem;line-height:1.8}
"""
