from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Any

from web.services.qa.helpers import (
    QA_STEPS,
    _buttons,
    _field_trace_id,
    _fields,
    _forms,
    _load_qa_viewpoints,
    _md,
    _output_dir,
    _qa_summary,
    _screen_summaries,
    _screens,
    _sid,
    _transitions_to,
    _viewpoint_names,
    _viewpoints_by_type,
)
from web.services.qa.markdown_lite import render_markdown_lite


def _generate_outputs(
    domain: str, report: dict[str, Any], ai_artifact: dict[str, Any] | None = None
) -> dict[str, Path]:
    out_dir = _output_dir() / domain / "qa_process"
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    docs = (
        _docs_from_ai_artifact(domain, ai_artifact, generated_at)
        if ai_artifact
        else {
            "test_plan": _test_plan(domain, report, generated_at),
            "test_analysis": _test_analysis(domain, report),
            "test_design": _test_design(domain, report),
            "test_cases": _test_cases(domain, report),
            "cross_review": _cross_review(domain, report),
        }
    )
    paths: dict[str, Path] = {}
    for key, _label, filename in QA_STEPS:
        path = out_dir / filename
        if key == "qa_process_report":
            path.write_text(
                _qa_process_report_html(domain, report, docs, generated_at, bool(ai_artifact)),
                encoding="utf-8",
            )
        else:
            path.write_text(docs[key], encoding="utf-8")
        paths[key] = path
    return paths


def _docs_from_ai_artifact(
    domain: str, artifact: dict[str, Any] | None, generated_at: str
) -> dict[str, str]:
    if not artifact:
        return {}
    plan = artifact.get("test_plan", {}) if isinstance(artifact.get("test_plan"), dict) else {}
    analysis = (
        artifact.get("test_analysis", {}) if isinstance(artifact.get("test_analysis"), dict) else {}
    )
    design = (
        artifact.get("test_design", {}) if isinstance(artifact.get("test_design"), dict) else {}
    )
    cases = artifact.get("test_cases", {}) if isinstance(artifact.get("test_cases"), dict) else {}
    review = (
        artifact.get("cross_review", {}) if isinstance(artifact.get("cross_review"), dict) else {}
    )
    report = (
        artifact.get("qa_process_report", {})
        if isinstance(artifact.get("qa_process_report"), dict)
        else {}
    )
    return {
        "test_plan": "\n".join(
            [
                f"# テスト計画: {domain}",
                "",
                f"- 生成日時: {generated_at}",
                "- 生成方式: OpenAI API補完 + 構造化JSON",
                "",
                _md_list_section("## スコープ", plan.get("scope")),
                _md_list_section("## テストレベル", plan.get("levels")),
                _md_list_section("## リスク", plan.get("risks")),
                _md_list_section("## Entry Criteria", plan.get("entry_criteria")),
                _md_list_section("## Exit Criteria", plan.get("exit_criteria")),
                _md_list_section("## 質問待ち", plan.get("questions")),
            ]
        ),
        "test_analysis": f"# テスト分析: {domain}\n\n{_analysis_table(analysis)}\n\n{_risk_table(analysis)}\n\n{_md_list_section('## 質問待ち', analysis.get('questions'))}",
        "test_design": f"# テスト設計: {domain}\n\n{_design_table(design)}\n\n{_coverage_table(design)}\n\n{_md_list_section('## 質問待ち', design.get('questions'))}",
        "test_cases": f"# テストケース: {domain}\n\n- Expected Case Yield: {_md(cases.get('expected_case_yield', '質問待ち'))}\n\n{_md_list_section('## Case Expansion Ledger', cases.get('case_expansion_ledger'))}\n\n{_cases_table(cases)}\n\n{_md_list_section('## 質問待ち', cases.get('questions'))}",
        "cross_review": f"# 横断レビュー: {domain}\n\n{_md_list_section('## 指摘', review.get('findings'))}\n\n{_md_list_section('## ギャップ', review.get('gaps'))}\n\n{_md_list_section('## 推奨対応', review.get('recommendations'))}\n\n{_md_list_section('## 質問待ち', review.get('questions'))}\n\n## QAプロセスレポート\n- {_md(report.get('summary', '質問待ち'))}\n\n{_md_list_section('## 次のアクション', report.get('next_actions'))}",
    }


def _md_list_section(title: str, values: Any) -> str:
    items = values if isinstance(values, list) else []
    if not items:
        items = ["質問待ち"]
    return title + "\n" + "\n".join(f"- {_md(item)}" for item in items)


def _analysis_table(analysis: dict[str, Any]) -> str:
    rows = ["| 画面ID | 画面 | 観察事項 | リスク | Trace |", "|---|---|---|---|---|"]
    for item in (
        analysis.get("source_inventory", [])
        if isinstance(analysis.get("source_inventory"), list)
        else []
    ):
        if not isinstance(item, dict):
            continue
        rows.append(
            "| {} | {} | {} | {} | {} |".format(
                _md(item.get("screen_id", "")),
                _md(item.get("title", "")),
                _md(" / ".join(str(v) for v in item.get("observations", []) if str(v).strip())),
                _md(item.get("risk", "")),
                _md(item.get("trace_id", "")),
            )
        )
    return "\n".join(rows)


def _risk_table(analysis: dict[str, Any]) -> str:
    rows = ["| リスクID | 内容 | 影響 | Trace |", "|---|---|---|---|"]
    for item in (
        analysis.get("risk_items", []) if isinstance(analysis.get("risk_items"), list) else []
    ):
        if isinstance(item, dict):
            rows.append(
                f"| {_md(item.get('risk_id', ''))} | {_md(item.get('description', ''))} | {_md(item.get('impact', ''))} | {_md(item.get('trace_id', ''))} |"
            )
    return "\n".join(rows)


def _design_table(design: dict[str, Any]) -> str:
    rows = ["| 観点ID | 対象 | 技法 | 設計メモ | Trace |", "|---|---|---|---|---|"]
    for item in design.get("viewpoints", []) if isinstance(design.get("viewpoints"), list) else []:
        if isinstance(item, dict):
            rows.append(
                f"| {_md(item.get('viewpoint_id', ''))} | {_md(item.get('target', ''))} | {_md(item.get('technique', ''))} | {_md(item.get('design_note', ''))} | {_md(item.get('trace_id', ''))} |"
            )
    return "\n".join(rows)


def _coverage_table(design: dict[str, Any]) -> str:
    rows = ["| Trace | Covered By | Coverage Note |", "|---|---|---|"]
    for item in (
        design.get("coverage_matrix", []) if isinstance(design.get("coverage_matrix"), list) else []
    ):
        if isinstance(item, dict):
            rows.append(
                f"| {_md(item.get('trace_id', ''))} | {_md(item.get('covered_by', ''))} | {_md(item.get('coverage_note', ''))} |"
            )
    return "\n".join(rows)


def _cases_table(cases: dict[str, Any]) -> str:
    rows = [
        "| ケースID | タイトル | 手順 | 期待結果 | 実行区分 | 状態 | Trace |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in cases.get("cases", []) if isinstance(cases.get("cases"), list) else []:
        if not isinstance(item, dict):
            continue
        rows.append(
            "| {} | {} | {} | {} | {} | {} | {} |".format(
                _md(item.get("case_id", "")),
                _md(item.get("title", "")),
                _md(" / ".join(str(v) for v in item.get("steps", []) if str(v).strip())),
                _md(item.get("expected", "")),
                _md(item.get("execution_type", "")),
                _md(item.get("status", "")),
                _md(item.get("trace_id", "")),
            )
        )
    return "\n".join(rows)


def _test_plan(domain: str, report: dict[str, Any], generated_at: str) -> str:
    meta = report.get("meta", {})
    summary = _qa_summary(report)
    return "\n".join(
        [
            f"# テスト計画: {domain}",
            "",
            f"- 生成日時: {generated_at}",
            f"- 対象URL: {meta.get('target_url', '質問待ち')}",
            "- 入力仕様: report.json / spec.xlsx / report.html",
            "- 生成方式: 外部LLM APIを使わないテンプレート生成",
            "",
            "## スコープ",
            f"- 画面数: {summary['screens']}",
            f"- フォーム数: {summary['forms']}",
            f"- 入力項目数: {summary['fields']}",
            f"- 必須項目数: {summary['required']}",
            f"- 操作要素数: {summary['buttons']}",
            "",
            "## テストレベル",
            "- 画面仕様確認",
            "- 入力バリデーション確認",
            "- 画面遷移確認",
            "- 操作要素の表示・到達性確認",
            "",
            "## 参考QA観点CSV",
            *[f"- {name}" for name in _viewpoint_names("quality_area_l1", 12)],
            "",
            "## 質問待ち",
            "- サポート対象ブラウザとデバイス条件",
            "- 認証・権限ロール別の期待結果",
            "- 外部連携、メール送信、決済など副作用を伴う処理の扱い",
            "- リリース判定基準と優先度付け",
            "",
        ]
    )


def _test_analysis(domain: str, report: dict[str, Any]) -> str:
    rows = [
        "| 画面ID | 画面 | URL | フォーム | 入力 | 必須 | 操作 | 遷移先 |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for screen in _screen_summaries(report):
        rows.append(
            "| {page_id} | {title} | {url} | {forms} | {fields} | {required} | {buttons} | {to} |".format(
                page_id=_md(screen["page_id"]),
                title=_md(screen["title"] or "質問待ち"),
                url=_md(screen["url"]),
                forms=screen["forms"],
                fields=screen["fields"],
                required=screen["required"],
                buttons=screen["buttons"],
                to=_md(", ".join(screen["transitions_to"]) or "質問待ち"),
            )
        )
    viewpoint_lines = (
        "\n".join(f"- {name}" for name in _viewpoint_names("category_l2", 12)) or "- 質問待ち"
    )
    return (
        f"# テスト分析: {domain}\n\n"
        + "\n".join(rows)
        + "\n\n## 分析メモ\n- 入力項目と操作要素を画面単位でリスク源として扱います。\n- CSV観点を画面仕様に重ね、未確認領域を質問待ちとして扱います。\n- 仕様から期待結果を確定できない箇所は質問待ちとして扱います。\n\n## 参考QA観点CSV\n"
        + viewpoint_lines
        + "\n"
    )


def _test_design(domain: str, report: dict[str, Any]) -> str:
    lines = [
        f"# テスト設計: {domain}",
        "",
        "| 観点ID | 対象 | 設計方針 | 元仕様 |",
        "|---|---|---|---|",
    ]
    for screen in _screens(report):
        sid = _sid(screen)
        lines.append(f"| TD-{sid}-NAV | 画面遷移 | 遷移先へ到達できることを確認 | {sid} |")
        for form_idx, form in enumerate(_forms(screen), 1):
            fid = f"{sid}-F{form_idx:02d}"
            lines.append(f"| TD-{fid}-SUBMIT | フォーム送信 | 正常入力と必須未入力を確認 | {fid} |")
            for field_idx, field in enumerate(_fields(form), 1):
                trace = _field_trace_id(screen, form_idx, field_idx)
                cond = " / ".join(field.get("test_conditions") or []) or "仕様から条件を補完する"
                lines.append(
                    f"| TD-{trace} | 入力項目 `{_md(field.get('name') or field.get('element_id') or 'unnamed')}` | {_md(cond)} | {trace} |"
                )
    for idx, viewpoint in enumerate(_viewpoints_by_type("category_l2")[:12], 1):
        lines.append(
            f"| TD-VP-{idx:02d} | {_md(viewpoint['name'])} | CSV観点を対象仕様へ適用し、該当有無・期待結果・不足仕様を確認 | QA-VP-{idx:02d} |"
        )
    lines += [
        "",
        "## 質問待ち",
        "- 業務上の同値クラス、境界値、禁止文字、重複登録条件は仕様確認が必要です。",
        "",
    ]
    return "\n".join(lines)


def _test_cases(domain: str, report: dict[str, Any]) -> str:
    lines = [
        f"# テストケース: {domain}",
        "",
        "| ケースID | 種別 | 手順 | 期待結果 | Trace |",
        "|---|---|---|---|---|",
    ]
    case_no = 1
    for screen in _screens(report):
        sid = _sid(screen)
        title = screen.get("title") or screen.get("url") or sid
        lines.append(
            f"| TC-{case_no:04d} | 画面表示 | `{_md(screen.get('url', ''))}` を開く | `{_md(title)}` の画面仕様が表示される | {sid} |"
        )
        case_no += 1
        for to_id in _transitions_to(screen):
            lines.append(
                f"| TC-{case_no:04d} | 画面遷移 | {sid} から {to_id} へ遷移する操作を実行 | 遷移先画面へ到達する | {sid}->{to_id} |"
            )
            case_no += 1
        for btn_idx, button in enumerate(_buttons(screen), 1):
            trace = f"{sid}-B{btn_idx:02d}"
            lines.append(
                f"| TC-{case_no:04d} | 操作要素 | `{_md(button)}` を操作 | 期待結果は質問待ち。少なくともエラーなく応答する | {trace} |"
            )
            case_no += 1
        for form_idx, form in enumerate(_forms(screen), 1):
            for field_idx, field in enumerate(_fields(form), 1):
                trace = _field_trace_id(screen, form_idx, field_idx)
                label = (
                    field.get("name")
                    or field.get("element_id")
                    or field.get("placeholder")
                    or "unnamed"
                )
                lines.append(
                    f"| TC-{case_no:04d} | 入力 | `{_md(label)}` に代表値を入力 | 入力値が受理される | {trace} |"
                )
                case_no += 1
                if field.get("required"):
                    lines.append(
                        f"| TC-{case_no:04d} | 必須 | `{_md(label)}` を未入力にする | 必須エラーが表示され送信されない | {trace} |"
                    )
                    case_no += 1
                for cond in field.get("test_conditions") or []:
                    lines.append(
                        f"| TC-{case_no:04d} | 条件 | `{_md(label)}` で {_md(cond)} | 仕様通りに受理またはエラー表示される | {trace} |"
                    )
                    case_no += 1
    for idx, viewpoint in enumerate(_viewpoints_by_type("category_l2")[:10], 1):
        lines.append(
            f"| TC-{case_no:04d} | 観点レビュー | CSV観点 `{_md(viewpoint['name'])}` を対象仕様へ照合 | 該当仕様、非該当理由、不足質問が記録される | QA-VP-{idx:02d} |"
        )
        case_no += 1
    if case_no == 1:
        lines.append(
            "| TC-0001 | 質問待ち | 画面仕様の詳細確認 | テスト可能な期待結果を定義する | QA-UNKNOWN |"
        )
    return "\n".join(lines) + "\n"


def _cross_review(domain: str, report: dict[str, Any]) -> str:
    summary = _qa_summary(report)
    findings = []
    if summary["screens"] == 0:
        findings.append("- 画面が抽出されていません。クロール条件または認証状態の確認が必要です。")
    if summary["fields"] and summary["required"] == 0:
        findings.append(
            "- 入力項目はありますが必須項目が検出されていません。HTML属性と業務必須の差分確認が必要です。"
        )
    if summary["transitions"] == 0 and summary["screens"] > 1:
        findings.append(
            "- 複数画面がありますが遷移情報がありません。リンク抽出条件の確認が必要です。"
        )
    if not findings:
        findings.append(
            "- 自動抽出範囲では重大な欠落兆候はありません。期待結果と業務ルールは質問待ちです。"
        )
    csv_viewpoints = (
        "\n".join(f"- {name}" for name in _viewpoint_names("quality_area_l1", 16)) or "- 質問待ち"
    )
    return (
        f"# 横断レビュー: {domain}\n\n## レビュー観点\n- 画面網羅性\n- 入力項目網羅性\n- 必須/任意の妥当性\n- 操作要素と遷移の整合性\n- トレーサビリティIDの付与\n\n## CSV横断観点\n{csv_viewpoints}\n\n## 指摘\n"
        + "\n".join(findings)
        + "\n\n## 質問待ち\n- 画面ごとの優先度と利用頻度\n- 障害時の業務影響\n- 非機能要件と監査観点\n"
    )


def _qa_process_report_html(
    domain: str,
    report: dict[str, Any],
    docs: dict[str, str],
    generated_at: str,
    used_ai: bool = False,
) -> str:
    summary = _qa_summary(report)
    screen_rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(str(screen["page_id"])),
            html.escape(str(screen["title"])),
            html.escape(str(screen["forms"])),
            html.escape(str(screen["fields"])),
            html.escape(str(screen["required"])),
        )
        for screen in _screen_summaries(report)
    )
    doc_sections = "".join(
        f'<section><h2>{html.escape(label)}</h2><div class="md-doc">{render_markdown_lite(docs[key])}</div></section>'
        for key, label, _filename in QA_STEPS
        if key in docs
    )
    viewpoint_rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(str(vp["summary_type"])),
            html.escape(str(vp["name"])),
            html.escape(str(vp["count"])),
        )
        for vp in _load_qa_viewpoints()
    )
    generation_mode = "OpenAI API補完 + 構造化JSON" if used_ai else "外部LLM API未使用"
    snapshot = (
        report.get("viewpoint_snapshot", {})
        if isinstance(report.get("viewpoint_snapshot"), dict)
        else {}
    )
    snapshot_html = ""
    if snapshot:
        snapshot_html = (
            "<h2>適用観点セット</h2><ul>"
            f"<li>セット: {html.escape(str(snapshot.get('set_name', '')))}</li>"
            f"<li>版: v{html.escape(str(snapshot.get('version', '')))}</li>"
            f"<li>選択理由: {html.escape(str(snapshot.get('selection_reason', '')))}</li>"
            f"<li>観点件数: {html.escape(str(snapshot.get('viewpoint_count', '')))}</li>"
            f"<li>チェックサム: <code>{html.escape(str(snapshot.get('checksum', '')))}</code></li>"
            "</ul>"
        )
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>QAプロセスレポート - {html.escape(domain)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #111827; margin: 32px; line-height: 1.65; }}
    h1 {{ font-size: 28px; margin-bottom: 4px; }}
    h2 {{ font-size: 18px; border-bottom: 1px solid #E5E7EB; padding-bottom: 6px; margin-top: 28px; }}
    .meta {{ color: #6B7280; margin-bottom: 20px; }}
    .cards {{ display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 10px; margin: 18px 0; }}
    .card {{ border: 1px solid #E5E7EB; border-radius: 6px; padding: 12px; background: #F9FAFB; }}
    .num {{ font-size: 24px; font-weight: 800; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 10px; }}
    th, td {{ border: 1px solid #E5E7EB; padding: 8px; text-align: left; font-size: 13px; }}
    th {{ background: #F3F4F6; }}
    pre {{ white-space: pre-wrap; background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 6px; padding: 14px; font-size: 12px; }}
    .md-doc h1, .md-doc h2, .md-doc h3, .md-doc h4, .md-doc h5, .md-doc h6 {{ margin: 18px 0 8px; }}
    .md-doc table.md-table {{ border-collapse: collapse; width: 100%; margin: 0 0 16px; font-size: 12px; }}
    .md-doc table.md-table th, .md-doc table.md-table td {{ border: 1px solid #E5E7EB; padding: 6px 10px; text-align: left; }}
    .md-doc table.md-table th {{ background: #F3F4F6; }}
    .md-doc pre.md-code {{ background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 6px; padding: 12px; overflow: auto; }}
    .md-doc ul, .md-doc ol {{ padding-left: 22px; }}
  </style>
</head>
<body>
  <h1>QAプロセスレポート</h1>
  <div class="meta">対象: {html.escape(domain)} / 生成日時: {html.escape(generated_at)} / {html.escape(generation_mode)}</div>
  <div class="cards">
    <div class="card"><div class="num">{summary['screens']}</div><div>画面</div></div>
    <div class="card"><div class="num">{summary['forms']}</div><div>フォーム</div></div>
    <div class="card"><div class="num">{summary['fields']}</div><div>入力項目</div></div>
    <div class="card"><div class="num">{summary['required']}</div><div>必須</div></div>
    <div class="card"><div class="num">{summary['buttons']}</div><div>操作要素</div></div>
  </div>
  {snapshot_html}
  <h2>入力仕様サマリー</h2>
  <table><thead><tr><th>画面ID</th><th>画面</th><th>フォーム</th><th>入力</th><th>必須</th></tr></thead><tbody>{screen_rows}</tbody></table>
  <h2>適用QA観点</h2>
  <table><thead><tr><th>種別</th><th>観点</th><th>件数</th></tr></thead><tbody>{viewpoint_rows}</tbody></table>
  {doc_sections}
</body>
</html>
"""
