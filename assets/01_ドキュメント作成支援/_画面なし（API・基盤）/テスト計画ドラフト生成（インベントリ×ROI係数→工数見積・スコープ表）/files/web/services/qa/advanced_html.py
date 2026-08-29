from __future__ import annotations

import html
from typing import Any

from web.services.qa.helpers import _fields, _qa_summary


def _model_graph_html(
    domain: str, graph: dict[str, Any], metrics: dict[str, Any], generated_at: str
) -> str:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    width = max(760, len(nodes) * 170)
    height = 340
    positions = {
        node["id"]: (90 + (idx % max(1, len(nodes))) * 150, 130 + (idx % 2) * 88)
        for idx, node in enumerate(nodes)
    }
    edge_svg = ""
    for edge in edges:
        x1, y1 = positions.get(edge["from"], (80, 120))
        x2, y2 = positions.get(edge["to"], (width - 80, 220))
        edge_svg += f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"/><text x="{(x1+x2)/2}" y="{(y1+y2)/2 - 6}" font-size="11" fill="#475569">{html.escape(edge["trace_id"])}</text>'
    node_svg = ""
    for node in nodes:
        x, y = positions[node["id"]]
        color = (
            "#fee2e2"
            if node["risk_score"] >= 70
            else "#fef3c7" if node["risk_score"] >= 30 else "#dcfce7"
        )
        node_svg += f'<g><rect x="{x-52}" y="{y-34}" width="104" height="68" rx="8" fill="{color}" stroke="#334155"/><text x="{x}" y="{y-8}" text-anchor="middle" font-size="13" font-weight="700">{html.escape(node["id"])}</text><text x="{x}" y="{y+12}" text-anchor="middle" font-size="11">{html.escape(str(node["title"])[:18])}</text><text x="{x}" y="{y+28}" text-anchor="middle" font-size="10">risk {node["risk_score"]}</text></g>'
    metric_cards = "".join(
        f"<div class='card'><strong>{html.escape(key)}</strong><span>{html.escape(str(value))}%</span></div>"
        for key, value in metrics.get("rates", {}).items()
    )
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><title>モデル/カバレッジ - {html.escape(domain)}</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:28px;color:#111827}}.meta{{color:#64748b}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin:16px 0}}.card{{border:1px solid #e5e7eb;border-radius:8px;padding:12px;background:#f8fafc}}.card span{{display:block;font-size:24px;font-weight:800;margin-top:6px}}svg{{width:100%;border:1px solid #e5e7eb;border-radius:8px;background:#fff}}table{{border-collapse:collapse;width:100%;margin-top:16px}}td,th{{border:1px solid #e5e7eb;padding:8px;font-size:13px}}th{{background:#f1f5f9}}</style></head>
<body><h1>モデル/カバレッジ</h1><p class="meta">対象: {html.escape(domain)} / 生成日時: {html.escape(generated_at)}</p><div class="cards">{metric_cards}</div>
<svg viewBox="0 0 {width} {height}" role="img" aria-label="画面遷移グラフ"><defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#64748b"/></marker></defs>{edge_svg}{node_svg}</svg>
<h2>レビューゲート</h2><table><thead><tr><th>ゲート</th><th>状態</th><th>件数</th></tr></thead><tbody>{''.join(f"<tr><td>{html.escape(str(g.get('gate','')))}</td><td>{html.escape(str(g.get('status','')))}</td><td>{html.escape(str(g.get('count','')))}</td></tr>" for g in metrics.get('review_gates', []))}</tbody></table></body></html>"""


def _playwright_candidates_html(domain: str, data: dict[str, Any], generated_at: str) -> str:
    rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(str(item["id"])),
            html.escape(str(item["title"])),
            html.escape(str(item["trace_id"])),
            html.escape(str(item["automation_status"])),
            html.escape(str(item["locator_strategy"])),
        )
        for item in data.get("candidates", [])
    )
    return _simple_table_html(
        domain,
        "自動テスト候補",
        generated_at,
        ["ID", "タイトル", "Trace", "状態", "ロケータ方針"],
        rows,
        data.get("execution_policy", ""),
    )


def _quality_viewpoints_html(domain: str, data: dict[str, Any], generated_at: str) -> str:
    rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(str(item["id"])),
            html.escape(str(item["category"])),
            html.escape(str(item["viewpoint"])),
            html.escape(str(item["automation"])),
            html.escape(str(item["trace_id"])),
        )
        for item in data.get("items", [])
    )
    return _simple_table_html(
        domain,
        "品質観点",
        generated_at,
        ["ID", "カテゴリ", "観点", "自動化", "Trace"],
        rows,
        data.get("review_policy", ""),
    )


def _simple_table_html(
    domain: str, title: str, generated_at: str, headers: list[str], rows: str, note: str
) -> str:
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><title>{html.escape(title)} - {html.escape(domain)}</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:28px;color:#111827;line-height:1.6}}.meta{{color:#64748b}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #e5e7eb;padding:8px;font-size:13px;vertical-align:top}}th{{background:#f1f5f9}}</style></head>
<body><h1>{html.escape(title)}</h1><p class="meta">対象: {html.escape(domain)} / 生成日時: {html.escape(generated_at)}</p><p>{html.escape(note)}</p><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></body></html>"""


def _risk_score(screen: dict[str, Any]) -> int:
    score = 10
    score += min(30, int(screen.get("fields") or 0) * 8)
    score += min(20, int(screen.get("required") or 0) * 10)
    score += min(20, int(screen.get("buttons") or 0) * 5)
    title_url = f"{screen.get('title', '')} {screen.get('url', '')}".lower()
    if any(
        word in title_url
        for word in [
            "login",
            "auth",
            "admin",
            "account",
            "payment",
            "checkout",
            "ログイン",
            "管理",
            "決済",
        ]
    ):
        score += 30
    return min(100, score)


def _risk_reasons(screen: dict[str, Any]) -> list[str]:
    reasons = []
    if screen.get("fields"):
        reasons.append("入力項目あり")
    if screen.get("required"):
        reasons.append("必須項目あり")
    if screen.get("buttons"):
        reasons.append("操作要素あり")
    if not screen.get("transitions_to"):
        reasons.append("遷移先未検出")
    return reasons or ["低リスク"]


def _rate(total: int, covered: int) -> int:
    if total <= 0:
        return 100
    return round(min(100, max(0, covered / total * 100)))


def _advanced_questions(report: dict[str, Any]) -> list[str]:
    summary = _qa_summary(report)
    questions = ["業務重要度、利用頻度、障害時影響の優先度付け"]
    if summary["forms"]:
        questions.append("入力値の同値クラス、境界値、禁止文字、重複条件")
    if summary["buttons"]:
        questions.append("操作要素ごとの副作用、確認ダイアログ、権限差分")
    if summary["screens"] > 1:
        questions.append("画面遷移の正規ルート、戻る/再読み込み時の期待結果")
    return questions


def _field_rows_for_screen(screen_summary: dict[str, Any]) -> list[dict[str, Any]]:
    """フォームの各入力項目を、同一フォーム内の他の必須項目（siblings）付きで返す。

    siblings は「対象項目だけを検証するため、他の必須項目には代表値を埋めて
    フォーム送信を成立させる」実操作テスト生成（spec_ts_generator）で使う。
    """
    rows = []
    for form_idx, form in enumerate(screen_summary.get("raw_forms") or [], 1):
        fields = _fields(form)
        for field_idx, field in enumerate(fields, 1):
            siblings = [f for f in fields if f is not field and f.get("required")]
            rows.append(
                {
                    "field": field,
                    "trace_id": f"{screen_summary['page_id']}-F{form_idx:02d}-I{field_idx:02d}",
                    "form_action": form.get("action", ""),
                    "required_siblings": siblings,
                }
            )
    return rows


def _pw_candidate(
    no: int,
    title: str,
    trace_id: str,
    status: str,
    steps: list[str],
    expected: str,
    locator_strategy: str,
    *,
    field: dict[str, Any] | None = None,
    form_action: str = "",
    required_siblings: list[dict[str, Any]] | None = None,
    submit_label: str = "",
) -> dict[str, Any]:
    candidate: dict[str, Any] = {
        "id": f"PW-{no:04d}",
        "title": title,
        "trace_id": trace_id,
        "automation_status": status,
        "steps": steps,
        "expected": expected,
        "locator_strategy": locator_strategy,
        "review_status": "レビュー待ち",
    }
    # 実操作・実アサーション生成に使う具体データ（無ければ従来どおりコメントのみで生成される）
    if field is not None:
        candidate["field"] = {
            "name": field.get("name", ""),
            "field_type": field.get("field_type", "text"),
            "required": bool(field.get("required")),
            "locators": list(field.get("locators") or []),
            "options": list(field.get("options") or []),
            "min_value": field.get("min_value", ""),
            "max_value": field.get("max_value", ""),
            "pattern": field.get("pattern", ""),
        }
        candidate["form_action"] = form_action
        candidate["required_siblings"] = [
            {
                "name": sib.get("name", ""),
                "field_type": sib.get("field_type", "text"),
                "locators": list(sib.get("locators") or []),
                "options": list(sib.get("options") or []),
                # min/max を落とすと、プラン別に異なる制約（例: 特定プランは
                # 人数・泊数が2固定）を汎用フォールバック値が侵害し、対象フィールドとは
                # 無関係の兄弟項目のせいでテストが失敗する（実サイト検証で発覚・修正）。
                "min_value": sib.get("min_value", ""),
                "max_value": sib.get("max_value", ""),
            }
            for sib in (required_siblings or [])
        ]
        candidate["submit_label"] = submit_label
    return candidate


def _quality_item(
    item_id: str,
    category: str,
    viewpoint: str,
    trigger: str,
    recommendation: str,
    automation: str,
    trace_id: str,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "category": category,
        "viewpoint": viewpoint,
        "trigger": trigger,
        "recommendation": recommendation,
        "automation": automation,
        "trace_id": trace_id,
        "review_status": "レビュー待ち",
    }
