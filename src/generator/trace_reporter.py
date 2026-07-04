"""RFP要件トレーサビリティマトリクス（SPEC-1-3）結果の出力。

requirement_trace.json（機械可読）と traceability_matrix.md（人が読む
マトリクス表）を出力する。要件が 1 件も無い場合はどちらのファイルも
生成しない（オプトイン — 既存出力ファイル集合を変えない・AC-6）。
"""

from __future__ import annotations

import json
from pathlib import Path

from ingest.models import DocumentBundle, document_evidence_to_dict
from ingest.req_tracer import STATUS_UNIMPLEMENTED_SUSPECT, RequirementTrace

TRACE_JSON_NAME = "requirement_trace.json"
TRACE_MD_NAME = "traceability_matrix.md"
_JSON_INDENT = 2

_STATUS_LABELS = {
    "covered": "カバー済み",
    "screen_only": "画面対応のみ（テスト未確認）",
    STATUS_UNIMPLEMENTED_SUSPECT: "未実装疑い",
}


def trace_to_dict(traces: tuple[RequirementTrace, ...], bundle: DocumentBundle) -> dict:
    """追跡結果を JSON シリアライズ可能な dict に変換する。"""
    req_id_counts: dict[str, int] = {}
    for trace in traces:
        req_id_counts[trace.requirement.req_id] = req_id_counts.get(trace.requirement.req_id, 0) + 1

    counts = {"covered": 0, "screen_only": 0, STATUS_UNIMPLEMENTED_SUSPECT: 0}
    for trace in traces:
        counts[trace.status] = counts.get(trace.status, 0) + 1

    return {
        "meta": {
            "source_files": list(bundle.source_files),
            "total_requirements": len(traces),
            "covered": counts["covered"],
            "screen_only": counts["screen_only"],
            "unimplemented_suspect": counts[STATUS_UNIMPLEMENTED_SUSPECT],
        },
        "requirements": [
            {
                "req_id": trace.requirement.req_id,
                "title": trace.requirement.title,
                "description": trace.requirement.description,
                "category": trace.requirement.category,
                "source": trace.requirement.source,
                "confidence": trace.requirement.confidence,
                "doc_evidence": document_evidence_to_dict(trace.requirement.evidence),
                "status": trace.status,
                "page_id": trace.page_id,
                "page_url": trace.page_url,
                "match_score": trace.match_score,
                "match_method": trace.match_method,
                "test_condition_count": trace.test_condition_count,
                "candidate_ids": list(trace.candidate_ids),
                "near_page_id": trace.near_page_id,
                "near_page_title": trace.near_page_title,
                "near_score": trace.near_score,
                "duplicate_req_id": req_id_counts[trace.requirement.req_id] > 1,
            }
            for trace in traces
        ],
    }


def save_trace_outputs(
    traces: tuple[RequirementTrace, ...], bundle: DocumentBundle, output_dir: Path
) -> None:
    """requirement_trace.json / traceability_matrix.md を出力する。

    traces が空なら何も書かない（オプトイン。AC-6）。
    """
    if not traces:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    data = trace_to_dict(traces, bundle)
    (output_dir / TRACE_JSON_NAME).write_text(
        json.dumps(data, ensure_ascii=False, indent=_JSON_INDENT), encoding="utf-8"
    )
    (output_dir / TRACE_MD_NAME).write_text(_render_markdown(data), encoding="utf-8")


def _render_markdown(data: dict) -> str:
    meta = data["meta"]
    total = meta["total_requirements"]
    covered_rate = (meta["covered"] / total * 100) if total else 0.0
    lines: list[str] = [
        "# RFP要件トレーサビリティマトリクス",
        "",
        f"参考文書: {', '.join(meta['source_files'])}",
        "",
        "## サマリ",
        "",
        f"- 要件数: {total} 件",
        f"- 対応確認済み（covered）: {meta['covered']} 件（{covered_rate:.1f}%）",
        f"- 画面対応のみ（テスト未確認・screen_only）: {meta['screen_only']} 件",
        f"- 未実装疑い（unimplemented_suspect）: {meta['unimplemented_suspect']} 件",
        "",
        "> 本マトリクスの「未実装疑い」は対応画面が実測から見つからなかったことのみを示し、",
        "> 実装済み・未実装を断定するものではありません（文書の鮮度に依存する疑いです）。",
        "",
    ]

    lines += ["## トレーサビリティマトリクス", ""]
    lines += [
        "| 要件ID | 要件名 | 対応画面 | テスト | 状態 | 文書出所 |",
        "|---|---|---|---|---|---|",
    ]
    for req in data["requirements"]:
        evidence = req["doc_evidence"] or {}
        location = f"{evidence.get('file', '')} {evidence.get('location', '')}".strip()
        page = req["page_id"] or "-"
        test_count = req["test_condition_count"] + len(req["candidate_ids"])
        tests = str(test_count) if req["page_id"] else "-"
        req_id_label = req["req_id"] + ("（ID重複）" if req["duplicate_req_id"] else "")
        status_label = _STATUS_LABELS.get(req["status"], req["status"])
        lines.append(
            f"| {req_id_label} | {req['title']} | {page} | {tests} | {status_label} | {location} |"
        )
    lines.append("")

    suspects = [r for r in data["requirements"] if r["status"] == STATUS_UNIMPLEMENTED_SUSPECT]
    if suspects:
        lines += ["## 未実装疑い一覧", ""]
        lines += [
            "> 対応画面が実測から見つからなかった要件です。断定はできません"
            "（文書の鮮度に依存する疑いであり、実装済みだが画面名・文言が"
            "異なるだけの可能性もあります）。判断材料として、しきい値未満でも"
            "最も近い画面（近い画面）を併記します。",
            "",
        ]
        for req in suspects:
            evidence = req["doc_evidence"] or {}
            location = f"{evidence.get('file', '')} {evidence.get('location', '')}".strip()
            if req["near_page_title"]:
                near = f"{req['near_page_title']}（score={req['near_score']}）"
            else:
                near = "近い候補なし"
            lines.append(
                f"- **{req['req_id']} {req['title']}**（出所: {location}） — 近い画面: {near}"
            )
        lines.append("")
    return "\n".join(lines)
