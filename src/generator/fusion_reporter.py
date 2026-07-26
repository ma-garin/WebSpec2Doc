"""Doc Fusion（文書×実測突合）結果の出力。

doc_fusion.json（機械可読）と doc_fusion.md（人が読むギャップレポート）を
出力する。すべての指摘に文書 evidence / 実測 evidence を併記する。
"""

from __future__ import annotations

import json
from pathlib import Path

from ingest.matcher import FusionResult
from ingest.models import DocumentBundle, document_evidence_to_dict

FUSION_JSON_NAME = "doc_fusion.json"
FUSION_MD_NAME = "doc_fusion.md"
_JSON_INDENT = 2


def fusion_to_dict(result: FusionResult, bundle: DocumentBundle) -> dict:
    """突合結果を JSON シリアライズ可能な dict に変換する。"""
    data: dict = {
        "meta": {
            "source_files": list(bundle.source_files),
            "documented_screens": len(bundle.screens),
            "documented_fields": len(bundle.fields),
            "matched_screens": len(result.screen_matches),
            "doc_only_screens": len(result.doc_only_screens),
            # 「実装が無い」と「取得できなかった」を数でも分けて示す
            "doc_only_unimplemented": sum(
                1 for d in (result.doc_only_details or ()) if d.reason == "unimplemented"
            ),
            "doc_only_unreached": sum(
                1 for d in (result.doc_only_details or ()) if d.reason == "unreached"
            ),
            "crawl_only_screens": len(result.crawl_only_page_ids),
            "field_gaps": len(result.field_gaps),
        },
        "screen_matches": [
            {
                "page_id": m.page_id,
                "page_url": m.page_url,
                "page_title": m.page_title,
                "official_name": m.screen.name,
                "screen_id": m.screen.screen_id,
                "score": m.score,
                "method": m.method,
                "doc_evidence": document_evidence_to_dict(m.screen.evidence),
            }
            for m in result.screen_matches
        ],
        "doc_only_screens": [
            {
                "name": d.screen.name,
                "screen_id": d.screen.screen_id,
                "url_hint": d.screen.url_hint,
                "doc_evidence": document_evidence_to_dict(d.screen.evidence),
                # 「取得できなかった」と「実装が無い」を区別する。
                # 混ぜると、存在する画面を欠陥として報告することになる。
                "reason": d.reason,
                "reason_evidence": d.evidence,
            }
            for d in (result.doc_only_details or ())
        ],
        "crawl_only_page_ids": list(result.crawl_only_page_ids),
        "field_gaps": [
            {
                "kind": g.kind,
                "page_id": g.page_id,
                "field_name": g.field_name,
                "detail": g.detail,
                "doc_evidence": document_evidence_to_dict(
                    g.doc_field.evidence if g.doc_field else None
                ),
                "crawl_selector": g.crawl_selector,
            }
            for g in result.field_gaps
        ],
    }
    if bundle.rules:
        data["documented_rules"] = [
            {
                "rule_id": r.rule_id,
                "kind": r.kind,
                "description": r.description,
                "screen_name": r.screen_name,
                "field_name": r.field_name,
                "expression": r.expression,
                "source": r.source,
                "confidence": r.confidence,
                "doc_evidence": document_evidence_to_dict(r.evidence),
            }
            for r in bundle.rules
        ]
    return data


def save_fusion_outputs(result: FusionResult, bundle: DocumentBundle, output_dir: Path) -> None:
    """doc_fusion.json / doc_fusion.md を出力する。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    data = fusion_to_dict(result, bundle)
    (output_dir / FUSION_JSON_NAME).write_text(
        json.dumps(data, ensure_ascii=False, indent=_JSON_INDENT), encoding="utf-8"
    )
    (output_dir / FUSION_MD_NAME).write_text(_render_markdown(data), encoding="utf-8")


def _render_markdown(data: dict) -> str:
    meta = data["meta"]
    lines: list[str] = [
        "# 文書×実測 突合レポート（Doc Fusion）",
        "",
        f"参考文書: {', '.join(meta['source_files'])}",
        "",
        "## サマリ",
        "",
        f"- 文書記載の画面: {meta['documented_screens']} 件 / 項目: {meta['documented_fields']} 件",
        f"- 画面の対応づけ: {meta['matched_screens']} 件",
        f"- 文書のみの画面: {meta['doc_only_screens']} 件"
        + (
            f"（うち未実装の疑い {meta.get('doc_only_unimplemented', 0)} 件 / "
            f"未到達 {meta.get('doc_only_unreached', 0)} 件）"
            if meta.get("doc_only_screens")
            else ""
        ),
        f"- 実測のみの画面（文書化漏れ）: {meta['crawl_only_screens']} 件",
        f"- 項目レベルのギャップ: {meta['field_gaps']} 件",
        "",
        "> 本レポートの「文書のみ」「矛盾」は文書の鮮度に依存します。",
        "> 各指摘の根拠（文書の位置・実測セレクタ）を確認のうえ判断してください。",
        "",
    ]
    if data["screen_matches"]:
        lines += ["## 画面の対応表（用語注入）", ""]
        lines += ["| page_id | 実測タイトル | 文書上の正式名称 | 対応根拠 |", "|---|---|---|---|"]
        for m in data["screen_matches"]:
            method = "URL一致" if m["method"] == "url" else f"名称類似({m['score']})"
            lines.append(
                f"| {m['page_id']} | {m['page_title']} | {m['official_name']} | {method} |"
            )
        lines.append("")
    if data["doc_only_screens"]:
        lines += ["## 文書のみの画面", ""]
        lines += [
            "> 「未到達」は実装が存在する証拠（他ページからのリンク・フォーム送信先）が",
            "> ある画面です。今回のクロールで取得できなかっただけなので、",
            "> 未実装として扱わないでください。",
            "",
            "> **「未実装の疑い」の判定限界**: 導線を持つ画面自体が未取得だと、",
            "> その先の画面へのリンクも観測できません（例: 確認画面が未取得なら",
            "> 完了画面へのリンクも見えない）。そのため実装済みの画面が",
            "> 「未実装の疑い」に入ることがあります。断定せず、根拠を読んで",
            "> 判断してください。",
            "",
        ]
        labels = {
            "unimplemented": "未実装の疑い",
            "unreached": "未到達（実装あり・今回未取得）",
            "no_url": "対応づけ不可（文書にURL記載なし）",
        }
        for s in data["doc_only_screens"]:
            evidence = s["doc_evidence"] or {}
            location = f"{evidence.get('file', '')} {evidence.get('location', '')}".strip()
            label = labels.get(s.get("reason", ""), "判定不明")
            lines.append(f"- **{s['name']}** — {label}（出所: {location}）")
            if s.get("reason_evidence"):
                lines.append(f"  - 根拠: {s['reason_evidence']}")
        lines.append("")
    if data["crawl_only_page_ids"]:
        lines += ["## 実測のみの画面（文書化漏れ候補）", ""]
        lines.append("- " + ", ".join(data["crawl_only_page_ids"]))
        lines.append("")
    gaps = data["field_gaps"]
    if gaps:
        lines += ["## 項目レベルのギャップ", ""]
        lines += [
            "| 分類 | 画面 | 項目 | 内容 | 文書の出所 | 実測セレクタ |",
            "|---|---|---|---|---|---|",
        ]
        kind_labels = {"doc_only": "文書のみ", "crawl_only": "実測のみ", "mismatch": "矛盾"}
        for g in gaps:
            evidence = g["doc_evidence"] or {}
            location = f"{evidence.get('file', '')} {evidence.get('location', '')}".strip()
            lines.append(
                f"| {kind_labels.get(g['kind'], g['kind'])} | {g['page_id']} "
                f"| {g['field_name']} | {g['detail']} | {location} | {g['crawl_selector']} |"
            )
        lines.append("")
    rules = data.get("documented_rules")
    if rules:
        lines += ["## 文書由来の業務ルール（LLM 抽出）", ""]
        lines += ["| ID | 種別 | 説明 | 画面/項目 | 出所 |", "|---|---|---|---|---|"]
        for r in rules:
            evidence = r["doc_evidence"] or {}
            location = f"{evidence.get('file', '')} {evidence.get('location', '')}".strip()
            target = " / ".join(v for v in (r["screen_name"], r["field_name"]) if v) or "-"
            lines.append(
                f"| {r['rule_id']} | {r['kind']} | {r['description']} | {target} | {location} |"
            )
        lines.append("")
    return "\n".join(lines)
