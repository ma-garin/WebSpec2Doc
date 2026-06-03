from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from web.services.qa.advanced_html import (
    _advanced_questions,
    _field_rows_for_screen,
    _model_graph_html,
    _playwright_candidates_html,
    _pw_candidate,
    _quality_item,
    _quality_viewpoints_html,
    _rate,
    _risk_reasons,
    _risk_score,
)
from web.services.qa.helpers import (
    QA_ADVANCED_OUTPUTS,
    _field_trace_id,
    _fields,
    _forms,
    _load_qa_viewpoints,
    _output_dir,
    _output_payload,
    _qa_summary,
    _screen_summaries,
    _screens,
)


def _advanced_payload(domain: str, report: dict[str, Any]) -> dict[str, Any]:
    return {
        "domain": domain,
        "outputs": _output_payload(domain),
        "transition_graph": _screen_transition_graph(report),
        "coverage_metrics": _coverage_metrics(report),
        "playwright_candidates": _playwright_candidates(domain, report),
        "quality_viewpoints": _quality_viewpoints(report),
    }


def _generate_advanced_outputs(domain: str, report: dict[str, Any]) -> dict[str, Path]:
    out_dir = _output_dir() / domain / "qa_process"
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    transition_graph = _screen_transition_graph(report)
    coverage_metrics = _coverage_metrics(report)
    playwright_candidates = _playwright_candidates(domain, report)
    quality_viewpoints = _quality_viewpoints(report)
    payloads: dict[str, Any] = {
        "screen_transition_graph": transition_graph,
        "coverage_metrics": coverage_metrics,
        "playwright_candidates": playwright_candidates,
        "quality_viewpoints": quality_viewpoints,
    }
    paths: dict[str, Path] = {}
    for key, _label, filename in QA_ADVANCED_OUTPUTS:
        path = out_dir / filename
        if key == "model_graph":
            path.write_text(
                _model_graph_html(domain, transition_graph, coverage_metrics, generated_at),
                encoding="utf-8",
            )
        elif key == "playwright_candidates_html":
            path.write_text(
                _playwright_candidates_html(domain, playwright_candidates, generated_at),
                encoding="utf-8",
            )
        elif key == "quality_viewpoints_html":
            path.write_text(
                _quality_viewpoints_html(domain, quality_viewpoints, generated_at), encoding="utf-8"
            )
        else:
            path.write_text(
                json.dumps(payloads[key], ensure_ascii=False, indent=2), encoding="utf-8"
            )
        paths[key] = path
    return paths


def _screen_transition_graph(report: dict[str, Any]) -> dict[str, Any]:
    screens = _screen_summaries(report)
    screen_ids = {str(screen["page_id"]) for screen in screens}
    nodes = [
        {
            "id": str(screen["page_id"]),
            "title": screen["title"] or "質問待ち",
            "url": screen["url"],
            "forms": screen["forms"],
            "fields": screen["fields"],
            "required": screen["required"],
            "buttons": screen["buttons"],
            "risk_score": _risk_score(screen),
            "trace_id": str(screen["page_id"]),
        }
        for screen in screens
    ]
    edges = []
    unresolved = []
    for screen in screens:
        source = str(screen["page_id"])
        for target in screen["transitions_to"]:
            edge = {
                "from": source,
                "to": target,
                "label": "navigation",
                "trace_id": f"{source}->{target}",
            }
            edges.append(edge)
            if target not in screen_ids:
                unresolved.append(edge)
    incoming = {str(edge["to"]) for edge in edges}
    outgoing = {str(edge["from"]) for edge in edges}
    return {
        "nodes": nodes,
        "edges": edges,
        "entry_nodes": [node["id"] for node in nodes if node["id"] not in incoming],
        "terminal_nodes": [node["id"] for node in nodes if node["id"] not in outgoing],
        "unresolved_edges": unresolved,
        "questions": _advanced_questions(report),
    }


def _coverage_metrics(report: dict[str, Any]) -> dict[str, Any]:
    summary = _qa_summary(report)
    screens = _screen_summaries(report)
    field_traces = [
        _field_trace_id(screen, form_idx, field_idx)
        for screen in _screens(report)
        for form_idx, form in enumerate(_forms(screen), 1)
        for field_idx, _field in enumerate(_fields(form), 1)
    ]
    transition_traces = [
        f"{screen['page_id']}->{target}"
        for screen in screens
        for target in screen["transitions_to"]
    ]
    operation_traces = [
        f"{screen['page_id']}-B{idx:02d}"
        for screen in screens
        for idx in range(1, screen["buttons"] + 1)
    ]
    expected = (
        [str(screen["page_id"]) for screen in screens]
        + field_traces
        + transition_traces
        + operation_traces
    )
    missing = []
    if summary["screens"] == 0:
        missing.append("画面が抽出されていません")
    if summary["screens"] > 1 and summary["transitions"] == 0:
        missing.append("複数画面に対する遷移情報がありません")
    if summary["fields"] and summary["required"] == 0:
        missing.append("入力項目に対する必須属性が検出されていません")
    if not _load_qa_viewpoints():
        missing.append("QA観点CSVが読み込めません")
    rates = {
        "screen_trace_rate": _rate(summary["screens"], len(screens)),
        "field_trace_rate": _rate(summary["fields"], len(field_traces)),
        "transition_trace_rate": _rate(summary["transitions"], len(transition_traces)),
        "operation_trace_rate": _rate(summary["buttons"], len(operation_traces)),
        "required_field_rate": _rate(summary["fields"], summary["required"]),
    }
    return {
        "summary": summary,
        "rates": rates,
        "expected_trace_count": len(expected),
        "trace_ids": expected,
        "missing_or_question_waiting": missing,
        "risk_distribution": {
            "high": sum(1 for screen in screens if _risk_score(screen) >= 70),
            "medium": sum(1 for screen in screens if 30 <= _risk_score(screen) < 70),
            "low": sum(1 for screen in screens if _risk_score(screen) < 30),
        },
        "review_gates": [
            {"gate": "Trace ID欠落", "status": "NG" if not expected else "OK"},
            {
                "gate": "質問待ち未解消",
                "status": "REVIEW",
                "count": len(missing) + len(_advanced_questions(report)),
            },
            {"gate": "外部API実行", "status": "未実行"},
        ],
    }


def _playwright_candidates(domain: str, report: dict[str, Any]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    case_no = 1
    for screen in _screen_summaries(report):
        sid = str(screen["page_id"])
        title = screen["title"] or sid
        candidates.append(
            _pw_candidate(
                case_no,
                "画面表示スモーク",
                sid,
                "auto",
                [f"page.goto('{screen['url']}')", f"画面タイトルまたは主要見出し `{title}` を確認"],
                "画面が表示され、主要コンテンツが見える",
                "getByRole / getByText を優先。CSS/XPathは最終手段。",
            )
        )
        case_no += 1
        src_url = screen.get("url", "")
        for target in screen["transitions_to"]:
            # 遷移元 URL を含めることで実際に画面を開いてから遷移テストを行える
            goto_step = [f"page.goto('{src_url}')"] if src_url else []
            candidates.append(
                _pw_candidate(
                    case_no,
                    "画面遷移",
                    f"{sid}->{target}",
                    "auto",
                    goto_step + [f"{target} へ遷移するリンクまたはボタンを操作"],
                    "遷移先URLまたは遷移先画面の主要テキストが確認できる",
                    "リンク名、button role、aria-label、test idの順に候補化",
                )
            )
            case_no += 1
        for row in _field_rows_for_screen(screen):
            trace = row["trace_id"]
            field = row["field"]
            label = (
                field.get("name")
                or field.get("element_id")
                or field.get("placeholder")
                or "unnamed"
            )
            # フォームがあるページの URL を先頭に含める
            form_goto_step = [f"page.goto('{src_url}')"] if src_url else []
            candidates.append(
                _pw_candidate(
                    case_no,
                    "フォーム入力",
                    trace,
                    "auto",
                    form_goto_step + [f"`{label}` に代表値を入力", "送信または次操作を実行"],
                    "入力値が受理される、または仕様通りのエラーが出る",
                    "getByLabel / getByPlaceholder / data-testid を優先",
                )
            )
            case_no += 1
            if field.get("required"):
                candidates.append(
                    _pw_candidate(
                        case_no,
                        "必須入力",
                        trace,
                        "auto",
                        form_goto_step + [f"`{label}` を空にする", "送信操作を実行"],
                        "必須エラーが表示され、送信されない",
                        "エラー文言は仕様不明の場合は質問待ち",
                    )
                )
                case_no += 1
    if _screen_summaries(report):
        candidates.append(
            _pw_candidate(
                case_no,
                "アクセシビリティ自動確認",
                "A11Y-ALL",
                "review",
                ["主要画面を開く", "axe-core相当のルールで自動検査する"],
                "重大なWCAG A/AA違反がない、またはレビュー対象として記録される",
                "axe-core/playwright導入時に実行候補化",
            )
        )
        case_no += 1
        candidates.append(
            _pw_candidate(
                case_no,
                "ビジュアル回帰候補",
                "VISUAL-ALL",
                "manual-review",
                ["主要画面のスクリーンショットを取得", "動的領域をマスクして比較"],
                "意図しないレイアウト崩れがない",
                "Playwright toHaveScreenshot候補。動的要素の安定化が必要。",
            )
        )
    return {
        "domain": domain,
        "execution_policy": "候補生成のみ。ブラウザ操作とテスト実行はユーザー承認後に別工程で行う。",
        "locator_policy": [
            "role",
            "text",
            "label",
            "placeholder",
            "test id",
            "CSS/XPathは最終手段",
        ],
        "traceability": "各候補は元画面・元入力項目・元仕様のTrace IDに紐づく。",
        "candidates": candidates,
    }


def _quality_viewpoints(report: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for idx, vp in enumerate(_load_qa_viewpoints(), 1):
        items.append(
            _quality_item(
                f"CSV-{idx:03d}",
                "CSV観点",
                vp["name"],
                f"{vp['summary_type']} / {vp['count']}件",
                "該当画面・入力項目へ照合し、不足仕様を質問待ちにする",
                "review",
                f"QA-VP-{idx:03d}",
            )
        )
    items.extend(
        [
            _quality_item(
                "A11Y-001",
                "アクセシビリティ",
                "ページごとのh1/ランドマーク/ラベル確認",
                "すべての画面",
                "axe-core導入時に自動検査候補。まずは観点としてレビューする",
                "auto-candidate",
                "A11Y-ALL",
            ),
            _quality_item(
                "A11Y-002",
                "アクセシビリティ",
                "フォーム入力とエラーメッセージの関連付け",
                "フォームを持つ画面",
                "label/aria-describedby/エラー文言の有無を確認する",
                "auto-candidate",
                "A11Y-FORM",
            ),
            _quality_item(
                "SEC-001",
                "OWASP WSTG/ASVS",
                "認証・セッション・アクセス制御",
                "ログイン/管理/個人情報画面",
                "権限別期待結果は質問待ちとして明示する",
                "manual-review",
                "SEC-AUTH",
            ),
            _quality_item(
                "SEC-002",
                "OWASP WSTG/ASVS",
                "入力検証・サニタイズ",
                "フォーム入力項目",
                "境界値、禁止文字、HTML/SQL風文字列の扱いを確認する",
                "manual-review",
                "SEC-INPUT",
            ),
            _quality_item(
                "DATA-001",
                "入力設計",
                "境界値・同値分割",
                "text/number/date/email入力",
                "HTML属性と業務ルールから代表値を展開する",
                "auto-candidate",
                "DATA-BVA",
            ),
            _quality_item(
                "DATA-002",
                "入力設計",
                "ペアワイズ/組合せ",
                "複数入力フォーム",
                "全組合せではなく2-wayを優先してケース爆発を抑える",
                "auto-candidate",
                "DATA-PAIRWISE",
            ),
            _quality_item(
                "API-001",
                "API契約",
                "OpenAPI/GraphQL契約テスト",
                "API仕様がある場合",
                "Schemathesis等の契約テスト候補を提示する",
                "optional",
                "API-CONTRACT",
            ),
            _quality_item(
                "VIS-001",
                "ビジュアル回帰",
                "主要画面スクリーンショット比較",
                "重要画面",
                "動的領域をマスクしてPlaywright visual comparison候補にする",
                "optional",
                "VISUAL-ALL",
            ),
        ]
    )
    screen_risks = [
        {
            "screen_id": screen["page_id"],
            "title": screen["title"],
            "risk_score": _risk_score(screen),
            "reasons": _risk_reasons(screen),
        }
        for screen in _screen_summaries(report)
    ]
    return {
        "items": items,
        "screen_risks": screen_risks,
        "questions": _advanced_questions(report),
        "review_policy": "自動診断ではなく、仕様レビューとテスト設計の観点として提示する。",
    }
