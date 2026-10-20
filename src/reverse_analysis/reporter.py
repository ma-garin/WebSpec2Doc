"""reverse_analysis.json の組み立て・検証・原子的保存・CLI 要約。

出力は同じ入力・解析結果から同じ JSON になる（時刻・PID・絶対 root・生 stderr・
source 本文を持たない）。トップレベルのキーと schema_version は固定し、未知の版は拒否する。
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from reverse_analysis.models import (
    ENGINE_VERSION_KEY,
    LEGACY_ENGINE_VERSION_KEY,
    SCHEMA_VERSION,
    Artifact,
    Coverage,
    Diagnostic,
    Relation,
    RuntimeObservation,
    StaticCandidate,
    Summary,
    to_json_value,
)

OUTPUT_FILENAME = "reverse_analysis.json"
TMP_PREFIX = f".{OUTPUT_FILENAME}."
TMP_SUFFIX = ".tmp"

PRODUCER_NAME = "webspec2doc-reverse-analysis"
PRODUCER_VERSION = "1"

STATUSES = ("complete", "partial", "unavailable", "failed", "cancelled")
EXIT_CODES = {"complete": 0, "partial": 2, "unavailable": 2, "failed": 2, "cancelled": 130}

TOP_LEVEL_KEYS = (
    "schema_version",
    "status",
    "producer",
    "inputs",
    "artifacts",
    "static_candidates",
    "runtime_observations",
    "relations",
    "coverage",
    "diagnostics",
    "summary",
)
# opt-in（--reverse-provenance）のときだけ末尾に足す。既定の出力は従来と同じキー
PROVIDER_EVIDENCE_KEY = "provider_evidence"
PROVIDER_EVIDENCE_KEYS = ("candidate_provenance", "dependency_edges", "source_map_findings")
_OBJECT_KEYS = {
    "producer": ("name", "version", ENGINE_VERSION_KEY),
    "inputs": ("static_root_label", "static_artifact_sha256", "runtime_snapshot_sha256"),
    "coverage": ("static", "runtime"),
    "summary": (
        "static_candidates",
        "observed_api_records",
        "inferred_relations",
        "ambiguous_relations",
        "unknown_relations",
        "matched_relations",
    ),
}
# 旧名（provider_version）で保存済みの文書も検証できるようにする（書込は新名のみ）
_LEGACY_PRODUCER_KEYS = ("name", "version", LEGACY_ENGINE_VERSION_KEY)
_LIST_KEYS = (
    "artifacts",
    "static_candidates",
    "runtime_observations",
    "relations",
    "diagnostics",
)


class ReportSchemaError(ValueError):
    """reverse_analysis.json の構造が schema と一致しない。"""


def build_document(
    *,
    status: str,
    engine_version: str | None,
    static_root_label: str,
    static_artifact_sha256: str | None,
    runtime_snapshot_sha256: str | None,
    artifacts: Iterable[Artifact],
    static_candidates: Iterable[StaticCandidate],
    runtime_observations: Iterable[RuntimeObservation],
    relations: Iterable[Relation],
    static_coverage: Coverage,
    runtime_coverage: Coverage,
    diagnostics: Iterable[Diagnostic],
    summary: Summary,
    provider_evidence: Mapping[str, Iterable[Any]] | None = None,
) -> dict[str, Any]:
    """モデルから schema_version 1 の文書を作り、検証して返す。"""
    document = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "producer": {
            "name": PRODUCER_NAME,
            "version": PRODUCER_VERSION,
            ENGINE_VERSION_KEY: engine_version,
        },
        "inputs": {
            "static_root_label": static_root_label,
            "static_artifact_sha256": static_artifact_sha256,
            "runtime_snapshot_sha256": runtime_snapshot_sha256,
        },
        "artifacts": to_json_value(tuple(artifacts)),
        "static_candidates": to_json_value(tuple(static_candidates)),
        "runtime_observations": to_json_value(tuple(runtime_observations)),
        "relations": to_json_value(tuple(relations)),
        "coverage": {
            "static": to_json_value(static_coverage),
            "runtime": to_json_value(runtime_coverage),
        },
        "diagnostics": to_json_value(tuple(diagnostics)),
        "summary": to_json_value(summary),
    }
    if provider_evidence is not None:
        document[PROVIDER_EVIDENCE_KEY] = {
            key: to_json_value(tuple(provider_evidence[key])) for key in PROVIDER_EVIDENCE_KEYS
        }
    validate_document(document)
    return document


def validate_document(document: Any) -> None:
    """トップレベルのキー・schema_version・status・型を検査する。"""
    if not isinstance(document, Mapping):
        raise ReportSchemaError("文書が JSON object ではありません")
    version = document.get("schema_version")
    if type(version) is not int or version != SCHEMA_VERSION:
        raise ReportSchemaError(f"未対応の schema_version です: {version!r}")
    keys = tuple(document.keys())
    if keys not in (TOP_LEVEL_KEYS, (*TOP_LEVEL_KEYS, PROVIDER_EVIDENCE_KEY)):
        raise ReportSchemaError("トップレベルのキーが schema と一致しません")
    if PROVIDER_EVIDENCE_KEY in document:
        extra = document[PROVIDER_EVIDENCE_KEY]
        if not isinstance(extra, Mapping) or tuple(extra.keys()) != PROVIDER_EVIDENCE_KEYS:
            raise ReportSchemaError(f"{PROVIDER_EVIDENCE_KEY} のキーが schema と一致しません")
        if not all(isinstance(extra[key], list) for key in PROVIDER_EVIDENCE_KEYS):
            raise ReportSchemaError(f"{PROVIDER_EVIDENCE_KEY} の各項目は配列である必要があります")
    if document["status"] not in STATUSES:
        raise ReportSchemaError(f"status の値が不正です: {document['status']!r}")
    for key, expected in _OBJECT_KEYS.items():
        value = document[key]
        accepted = (expected, _LEGACY_PRODUCER_KEYS) if key == "producer" else (expected,)
        if not isinstance(value, Mapping) or tuple(value.keys()) not in accepted:
            raise ReportSchemaError(f"{key} のキーが schema と一致しません")
    for key in _LIST_KEYS:
        if not isinstance(document[key], list):
            raise ReportSchemaError(f"{key} は配列である必要があります")
    for side in ("static", "runtime"):
        if document["coverage"][side].get("status") not in STATUSES:
            raise ReportSchemaError(f"coverage.{side}.status の値が不正です")


def dumps(document: Mapping[str, Any]) -> str:
    """決定的な JSON 文字列（キー順は schema 定義順）。"""
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def load_document(path: Path) -> dict[str, Any]:
    """保存済み文書を読み、schema を検証する。"""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReportSchemaError("reverse_analysis.json が JSON として読めません") from exc
    validate_document(document)
    return document


def write_document(output_dir: Path, document: Mapping[str, Any]) -> Path:
    """同じディレクトリの一時ファイルへ書き、os.replace で置き換える。失敗時は一時ファイルを消す。"""
    validate_document(document)
    payload = dumps(document).encode("utf-8")
    target = output_dir / OUTPUT_FILENAME
    fd, tmp_name = tempfile.mkstemp(dir=output_dir, prefix=TMP_PREFIX, suffix=TMP_SUFFIX)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if target.is_symlink():
            raise OSError("出力先のファイルが symlink です")
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return target


# ---------------------------------------------------------------- CLI 表示

_STATUS_TEXT = {
    "complete": "完了（選択した入力の処理が完了。全システムの網羅や確定仕様ではありません）",
    "partial": "一部のみ（解析できた範囲だけを保存しました）",
    "unavailable": "静的解析を実行できませんでした（実測のみ保存）",
    "failed": "失敗",
    "cancelled": "取り消し",
}


def format_summary(document: Mapping[str, Any], output_label: str | None) -> list[str]:
    """CLI 向けの要約行。実測・静的構文の事実・対応推論・未確認を分けて示す。"""
    summary = document["summary"]
    coverage = document["coverage"]
    lines = [
        f"reverse analysis: {_STATUS_TEXT[document['status']]}",
        f"出力先: {output_label}" if output_label else "出力先: なし（成果物は保存されていません）",
        f"実測（snapshot の API 記録数。API 総数・網羅率ではない）: {summary['observed_api_records']}",
        f"静的構文の事実（JS 内に構文がある候補。実行の証明ではない）: {summary['static_candidates']}",
        "対応推論: "
        f"inferred={summary['inferred_relations']} ambiguous={summary['ambiguous_relations']} "
        f"matched={summary['matched_relations']}",
        f"未確認（unknown）: {summary['unknown_relations']}",
        "route 候補（静的構文の宣言。画面遷移の実測ではない）: "
        f"{sum(1 for c in document['static_candidates'] if c['kind'] == 'route')}",
    ]
    extra = document.get(PROVIDER_EVIDENCE_KEY)
    if isinstance(extra, Mapping):
        lines.append(
            f"解析出典（opt-in）: 候補出典={len(extra['candidate_provenance'])} "
            f"imports={len(extra['dependency_edges'])} "
            f"source map 所見={len(extra['source_map_findings'])}"
        )
    for side, label in (("static", "静的"), ("runtime", "実測")):
        cov = coverage[side]
        omitted = "不明" if cov["omitted_count"] is None else str(cov["omitted_count"])
        lines.append(
            f"coverage {label}: {cov['status']}（truncated={cov['truncated']} 省略={omitted}）"
        )
        lines.extend(f"  - 制限・欠測理由: {limit}" for limit in cov["limitations"])
    for diag in document["diagnostics"]:
        lines.append(f"[{diag['severity']}] {diag['message']}")
        lines.append(f"  次の行動: {diag['next_action']}")
    return lines
