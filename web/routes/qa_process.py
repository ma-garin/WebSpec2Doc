from __future__ import annotations

import csv
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Blueprint, request

from web.config import OUTPUT_DIR, QA_VIEWPOINTS_CSV
from web.services.openai_qa import OpenAIQAError, generate_openai_qa, has_openai_api_key
from web.summary import _summary_for_domain
from web.validation import _valid_domain

bp = Blueprint("qa_process", __name__)

QA_STEPS = (
    ("test_plan", "テスト計画", "test_plan.md"),
    ("test_analysis", "テスト分析", "test_analysis.md"),
    ("test_design", "テスト設計", "test_design.md"),
    ("test_cases", "テストケース", "test_cases.md"),
    ("cross_review", "横断レビュー", "cross_review.md"),
    ("qa_process_report", "QAプロセスレポート", "qa_process_report.html"),
)

QA_ADVANCED_OUTPUTS = (
    ("screen_transition_graph", "画面遷移グラフJSON", "screen_transition_graph.json"),
    ("model_graph", "モデルグラフHTML", "model_graph.html"),
    ("coverage_metrics", "カバレッジメトリクス", "coverage_metrics.json"),
    ("playwright_candidates", "Playwright候補JSON", "playwright_candidates.json"),
    ("playwright_candidates_html", "Playwright候補HTML", "playwright_candidates.html"),
    ("quality_viewpoints", "品質観点JSON", "quality_viewpoints.json"),
    ("quality_viewpoints_html", "品質観点HTML", "quality_viewpoints.html"),
)


@bp.get("/api/qa-process/input")
def api_qa_process_input() -> dict | tuple[dict, int]:
    domain = request.args.get("domain", "")
    report_path, error = _report_json_path(domain)
    if error:
        return {"error": error}, 404
    report = _load_report(report_path)
    if report is None:
        return {"error": "invalid report.json"}, 400
    return _input_payload(domain, report)


@bp.post("/api/qa-process/generate")
def api_qa_process_generate() -> dict | tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    domain = request.form.get("domain") or body.get("domain", "")
    step = request.form.get("step") or body.get("step", "all")
    use_ai = _truthy(request.form.get("use_ai") or body.get("use_ai"))
    report_path, error = _report_json_path(domain)
    if error:
        return {"error": error}, 404
    report = _load_report(report_path)
    if report is None:
        return {"error": "invalid report.json"}, 400
    ai_status: dict[str, Any] = {
        "requested": use_ai,
        "available": has_openai_api_key(),
        "used": False,
        "fallback": False,
    }
    ai_artifact = None
    if use_ai:
        if not ai_status["available"]:
            ai_status |= {
                "fallback": True,
                "error": "OPENAI_API_KEY が設定されていないためテンプレート生成に切り替えました。",
            }
        else:
            try:
                ai_artifact = generate_openai_qa(domain, report, _load_qa_viewpoints())
                _ai_artifact_path(domain).write_text(
                    json.dumps(ai_artifact, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                ai_status |= {"used": True, "model": ai_artifact.get("model", "")}
            except OpenAIQAError as exc:
                ai_artifact = None
                ai_status |= {"fallback": True, "error": str(exc)}
    outputs = _generate_outputs(domain, report, ai_artifact)
    outputs |= _generate_advanced_outputs(domain, report)
    selected = outputs.get(step) or outputs["qa_process_report"]
    return {
        "ok": True,
        "domain": domain,
        "step": step,
        "selected": str(selected.resolve()),
        "outputs": _output_payload(domain),
        "summary": _qa_summary(report),
        "ai": ai_status,
        "ai_artifact": ai_artifact,
        "advanced": _advanced_payload(domain, report),
    }


@bp.get("/api/qa-process/result")
def api_qa_process_result() -> dict | tuple[dict, int]:
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    if not (OUTPUT_DIR / domain).is_dir():
        return {"error": "not found"}, 404
    return {"domain": domain, "outputs": _output_payload(domain)}


@bp.get("/api/qa-process/advanced")
def api_qa_process_advanced() -> dict | tuple[dict, int]:
    domain = request.args.get("domain", "")
    report_path, error = _report_json_path(domain)
    if error:
        return {"error": error}, 404
    report = _load_report(report_path)
    if report is None:
        return {"error": "invalid report.json"}, 400
    return _advanced_payload(domain, report)


@bp.post("/api/qa-process/generate-advanced")
def api_qa_process_generate_advanced() -> dict | tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    domain = request.form.get("domain") or body.get("domain", "")
    report_path, error = _report_json_path(domain)
    if error:
        return {"error": error}, 404
    report = _load_report(report_path)
    if report is None:
        return {"error": "invalid report.json"}, 400
    outputs = _generate_advanced_outputs(domain, report)
    return {
        "ok": True,
        "domain": domain,
        "outputs": _output_payload(domain),
        "advanced": _advanced_payload(domain, report),
        "generated": {k: str(v.resolve()) for k, v in outputs.items()},
    }


def _report_json_path(domain: str) -> tuple[Path | None, str]:
    if not _valid_domain(domain):
        return None, "not found"
    domain_dir = OUTPUT_DIR / domain
    if not domain_dir.is_dir():
        return None, "not found"
    report_path = domain_dir / "report.json"
    if not report_path.is_file():
        return None, "report.json not found"
    return report_path, ""


def _load_report(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _input_payload(domain: str, report: dict[str, Any]) -> dict[str, Any]:
    domain_dir = OUTPUT_DIR / domain
    return {
        "domain": domain,
        "summary": _summary_for_domain(domain) | _qa_summary(report),
        "input_files": {
            "report_json": _existing_path(domain_dir / "report.json"),
            "spec_excel": _existing_path(domain_dir / "spec.xlsx"),
            "report_html": _existing_path(domain_dir / "report.html"),
        },
        "screens": _screen_summaries(report),
        "outputs": _output_payload(domain),
        "ai": {"available": has_openai_api_key()},
        "ai_artifact": _load_ai_artifact(domain),
        "viewpoints": _load_qa_viewpoints(),
    }


def _existing_path(path: Path) -> str:
    return str(path.resolve()) if path.exists() else ""


def _output_payload(domain: str) -> dict[str, str]:
    out_dir = OUTPUT_DIR / domain / "qa_process"
    return {
        key: _existing_path(out_dir / filename)
        for key, _label, filename in QA_STEPS + QA_ADVANCED_OUTPUTS
    }


def _qa_summary(report: dict[str, Any]) -> dict[str, int]:
    screens = _screens(report)
    forms = [form for screen in screens for form in _forms(screen)]
    fields = [field for form in forms for field in _fields(form)]
    return {
        "screens": len(screens),
        "forms": len(forms),
        "fields": len(fields),
        "required": sum(1 for field in fields if field.get("required")),
        "buttons": sum(len(_buttons(screen)) for screen in screens),
        "transitions": sum(len(_transitions_to(screen)) for screen in screens),
    }


def _load_qa_viewpoints() -> list[dict[str, Any]]:
    try:
        with QA_VIEWPOINTS_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        return []
    viewpoints: list[dict[str, Any]] = []
    for row in rows:
        name = (row.get("name") or "").strip()
        summary_type = (row.get("summary_type") or "").strip()
        if not name or not summary_type:
            continue
        try:
            count = int(row.get("count") or 0)
        except ValueError:
            count = 0
        viewpoints.append({"summary_type": summary_type, "name": name, "count": count})
    return viewpoints


def _viewpoints_by_type(summary_type: str) -> list[dict[str, Any]]:
    return [vp for vp in _load_qa_viewpoints() if vp.get("summary_type") == summary_type]


def _viewpoint_names(summary_type: str, limit: int = 8) -> list[str]:
    return [str(vp["name"]) for vp in _viewpoints_by_type(summary_type)[:limit]]


def _screen_summaries(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for screen in _screens(report):
        fields = [field for form in _forms(screen) for field in _fields(form)]
        rows.append(
            {
                "page_id": screen.get("page_id", ""),
                "title": screen.get("title", ""),
                "url": screen.get("url", ""),
                "forms": len(_forms(screen)),
                "fields": len(fields),
                "required": sum(1 for field in fields if field.get("required")),
                "buttons": len(_buttons(screen)),
                "transitions_to": _transitions_to(screen),
                "raw_forms": _forms(screen),
            }
        )
    return rows


def _ai_artifact_path(domain: str) -> Path:
    out_dir = OUTPUT_DIR / domain / "qa_process"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "ai_artifacts.json"


def _load_ai_artifact(domain: str) -> dict[str, Any] | None:
    path = OUTPUT_DIR / domain / "qa_process" / "ai_artifacts.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _generate_outputs(
    domain: str, report: dict[str, Any], ai_artifact: dict[str, Any] | None = None
) -> dict[str, Path]:
    out_dir = OUTPUT_DIR / domain / "qa_process"
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
        f"<section><h2>{html.escape(label)}</h2><pre>{html.escape(docs[key])}</pre></section>"
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
  <h2>入力仕様サマリー</h2>
  <table><thead><tr><th>画面ID</th><th>画面</th><th>フォーム</th><th>入力</th><th>必須</th></tr></thead><tbody>{screen_rows}</tbody></table>
  <h2>参考QA観点CSV</h2>
  <table><thead><tr><th>種別</th><th>観点</th><th>件数</th></tr></thead><tbody>{viewpoint_rows}</tbody></table>
  {doc_sections}
</body>
</html>
"""


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
    out_dir = OUTPUT_DIR / domain / "qa_process"
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
        for target in screen["transitions_to"]:
            candidates.append(
                _pw_candidate(
                    case_no,
                    "画面遷移",
                    f"{sid}->{target}",
                    "auto",
                    [f"{sid} を開く", f"{target} へ遷移するリンクまたはボタンを操作"],
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
            candidates.append(
                _pw_candidate(
                    case_no,
                    "フォーム入力",
                    trace,
                    "auto",
                    [f"`{label}` に代表値を入力", "送信または次操作を実行"],
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
                        [f"`{label}` を空にする", "送信操作を実行"],
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
    rows = []
    for form_idx, form in enumerate(screen_summary.get("raw_forms") or [], 1):
        for field_idx, field in enumerate(_fields(form), 1):
            rows.append(
                {
                    "field": field,
                    "trace_id": f"{screen_summary['page_id']}-F{form_idx:02d}-I{field_idx:02d}",
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
) -> dict[str, Any]:
    return {
        "id": f"PW-{no:04d}",
        "title": title,
        "trace_id": trace_id,
        "automation_status": status,
        "steps": steps,
        "expected": expected,
        "locator_strategy": locator_strategy,
        "review_status": "レビュー待ち",
    }


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


def _screens(report: dict[str, Any]) -> list[dict[str, Any]]:
    screens = report.get("screens", [])
    return (
        [screen for screen in screens if isinstance(screen, dict)]
        if isinstance(screens, list)
        else []
    )


def _forms(screen: dict[str, Any]) -> list[dict[str, Any]]:
    forms = screen.get("forms", [])
    return [form for form in forms if isinstance(form, dict)] if isinstance(forms, list) else []


def _fields(form: dict[str, Any]) -> list[dict[str, Any]]:
    fields = form.get("fields", [])
    return (
        [field for field in fields if isinstance(field, dict)] if isinstance(fields, list) else []
    )


def _buttons(screen: dict[str, Any]) -> list[str]:
    buttons = screen.get("buttons", [])
    return (
        [str(button) for button in buttons if str(button).strip()]
        if isinstance(buttons, list)
        else []
    )


def _transitions_to(screen: dict[str, Any]) -> list[str]:
    transitions = screen.get("transitions", {})
    to_ids = transitions.get("to", []) if isinstance(transitions, dict) else []
    return (
        [str(to_id) for to_id in to_ids if str(to_id).strip()] if isinstance(to_ids, list) else []
    )


def _sid(screen: dict[str, Any]) -> str:
    return str(screen.get("page_id") or "P???")


def _field_trace_id(screen: dict[str, Any], form_idx: int, field_idx: int) -> str:
    return f"{_sid(screen)}-F{form_idx:02d}-I{field_idx:02d}"


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _md(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
