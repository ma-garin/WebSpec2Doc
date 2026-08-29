"""画面カバレッジマップ（踏んだ範囲の可視化）。

自動テストが実際に踏んだ画面・遷移を、画面遷移図に重ねて表示する。

主張境界: ここで示すのは**踏んだ範囲の事実**のみ。
「踏んだ＝検証した」ではないため、カバレッジ率を品質保証の数値として掲げない。
数値は未踏領域を探すための道具であって、達成目標ではない。
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

CLAIM_SCOPE = "traversed_range_only"

CLAIM_NOTICE = (
    "本図は自動テストが踏んだ範囲の記録である。"
    "踏んだことは検証したことを意味しないため、この割合を品質保証の指標として用いない。"
)

STATUS_COVERED = "covered"
STATUS_UNTOUCHED = "untouched"

REPORT_TITLE = "画面カバレッジマップ"


def build_coverage_map(
    graph: dict[str, Any],
    executed_page_ids: set[str] | list[str],
    executed_edges: set[tuple[str, str]] | list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """遷移図に「踏んだ／未踏」を重ねた構造を返す。"""
    touched_nodes = {str(page_id) for page_id in executed_page_ids}
    touched_edges = {(str(a), str(b)) for a, b in (executed_edges or set())}

    nodes: list[dict[str, Any]] = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id", ""))
        nodes.append(
            {
                "id": node_id,
                "title": str(node.get("title", "")),
                "url": str(node.get("url", "")),
                "status": STATUS_COVERED if node_id in touched_nodes else STATUS_UNTOUCHED,
            }
        )

    edges: list[dict[str, Any]] = []
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        source, target = str(edge.get("from", "")), str(edge.get("to", ""))
        edges.append(
            {
                "from": source,
                "to": target,
                "status": (
                    STATUS_COVERED if (source, target) in touched_edges else STATUS_UNTOUCHED
                ),
            }
        )

    covered_nodes = sum(1 for node in nodes if node["status"] == STATUS_COVERED)
    covered_edges = sum(1 for edge in edges if edge["status"] == STATUS_COVERED)
    return {
        "meta": {"claim_scope": CLAIM_SCOPE, "claim_notice": CLAIM_NOTICE},
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "total_screens": len(nodes),
            "traversed_screens": covered_nodes,
            "total_transitions": len(edges),
            "traversed_transitions": covered_edges,
            "untouched_screens": [
                node["id"] for node in nodes if node["status"] == STATUS_UNTOUCHED
            ],
        },
    }


def executed_pages_from_meta(
    meta: dict[str, Any], report: dict[str, Any] | None = None
) -> set[str]:
    """AutoRun のメタと実行結果から、実際に踏んだ画面IDを取り出す。

    report を渡した場合は「実行された（skipped でない）テスト」に限定する。
    渡さない場合は生成された全テストの対象画面を踏んだ扱いにする。
    """
    executed_ids: set[str] = set()
    ran_test_ids: set[str] | None = None
    if report is not None:
        ran_test_ids = set()
        for test in report.get("tests", []):
            if not isinstance(test, dict) or str(test.get("status", "")) == "skipped":
                continue
            title = str(test.get("title", "")).strip()
            token = title.split(" ", 1)[0] if title else ""
            if token:
                ran_test_ids.add(token)

    for item in meta.get("tests", []):
        if not isinstance(item, dict):
            continue
        test_id = str(item.get("test_id", ""))
        page_id = str(item.get("page_id", ""))
        if not page_id:
            continue
        if ran_test_ids is None or test_id in ran_test_ids:
            executed_ids.add(page_id)
    return executed_ids


def save_coverage_map(coverage: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "coverage_map_json": out_dir / "coverage_map.json",
        "coverage_map_html": out_dir / "coverage_map.html",
    }
    paths["coverage_map_json"].write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    paths["coverage_map_html"].write_text(render_html(coverage), encoding="utf-8")
    return paths


def render_html(coverage: dict[str, Any]) -> str:
    meta = coverage.get("meta", {})
    summary = coverage.get("summary", {})
    rows = "".join(
        "<tr>"
        f"<td><code>{html.escape(str(node.get('id', '')))}</code></td>"
        f"<td>{html.escape(str(node.get('title', '')))}</td>"
        f"<td>{html.escape(str(node.get('url', '')))}</td>"
        f"<td>{_status_cell(str(node.get('status', '')))}</td>"
        "</tr>"
        for node in coverage.get("nodes", [])
    )
    untouched = summary.get("untouched_screens", [])
    untouched_block = (
        f'<p class="untouched">未踏の画面: {html.escape(", ".join(untouched))}</p>'
        if untouched
        else '<p class="muted">未踏の画面はありません。</p>'
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
<section><h2>踏んだ範囲</h2>
<div class="cards">
<div class="card"><div class="num">{summary.get('traversed_screens', 0)}
 / {summary.get('total_screens', 0)}</div><div>画面</div></div>
<div class="card"><div class="num">{summary.get('traversed_transitions', 0)}
 / {summary.get('total_transitions', 0)}</div><div>遷移</div></div>
</div>
{untouched_block}
</section>
<section><h2>画面別</h2><div class="scroll"><table>
<thead><tr><th>画面ID</th><th>名称</th><th>URL</th><th>状態</th></tr></thead>
<tbody>{rows}</tbody></table></div></section>
</main></body></html>"""


def _status_cell(status: str) -> str:
    if status == STATUS_COVERED:
        return '<span class="pill covered">踏んだ</span>'
    return '<span class="pill untouched">未踏</span>'


def _css() -> str:
    return """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif;color:#16202B;background:#f5f7f9;line-height:1.7}
header{background:#00285E;color:#fff;padding:1.4rem 2rem}
header h1{font-size:1.35rem}
.notice{margin-top:.4rem;font-size:.85rem;opacity:.92;max-width:70ch}
main{max-width:1000px;margin:2rem auto;padding:0 1.5rem;display:flex;flex-direction:column;gap:1.5rem}
section{background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.08);overflow:hidden}
section h2{background:#eef2f5;padding:.7rem 1.2rem;font-size:1rem}
.cards{display:flex;gap:1rem;padding:1.2rem;flex-wrap:wrap}
.card{flex:1;min-width:140px;border:2px solid #d8e0e6;border-radius:8px;padding:.9rem;text-align:center}
.card .num{font-size:1.6rem;font-weight:700;font-variant-numeric:tabular-nums}
.untouched{padding:0 1.2rem 1.2rem;color:#8D6B00;font-size:.9rem}
.muted{padding:0 1.2rem 1.2rem;color:#888;font-size:.9rem}
.scroll{padding:1.2rem;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.88rem}
th{background:#00285E;color:#fff;padding:.55rem .8rem;text-align:left;white-space:nowrap}
td{padding:.5rem .8rem;border-bottom:1px solid #eee}
.pill{display:inline-block;padding:1px 9px;border-radius:10px;font-size:.8rem}
.pill.covered{background:#198038;color:#fff}
.pill.untouched{background:#e0e0e0;color:#333}
code{font-family:ui-monospace,Menlo,monospace}
"""
