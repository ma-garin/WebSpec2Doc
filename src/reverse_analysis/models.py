"""reverse analysis の不変データモデル。

実測（observed）・静的構文の事実・対応推論（inferred）・未確認（unknown）を
型の上で分けて持つ。数値 confidence への変換はしない。
ID は出典 digest・位置・kind だけから決定的に作り、時刻や PID を混ぜない。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, fields, is_dataclass
from typing import Any

SCHEMA_VERSION = 1

ID_DIGEST_LENGTH = 16
_ID_SEPARATOR = "\x1f"

CANDIDATE_KINDS = frozenset({"route", "api", "module", "source"})
RESOLUTIONS = frozenset({"exact", "partial", "unavailable"})
EPISTEMIC_STATES = frozenset({"observed", "inferred", "unknown", "unavailable"})
CLASSIFICATIONS = frozenset({"matched", "inferred", "ambiguous", "unknown"})
COVERAGE_STATUSES = frozenset({"complete", "partial", "unavailable", "failed", "cancelled"})
SEVERITIES = frozenset({"info", "warning", "error"})
LOCATION_UNITS = frozenset({"line_column_utf16", "line_column_utf8", "byte_range", "unknown"})

QUERY_SCOPE_NOT_RETAINED = "not_retained"

# 永続化キーの provider 非依存名と旧名（旧名の保存物は読込時だけ別名で受け、書込は新名のみ）
ENGINE_VERSION_KEY = "engine_version"
LEGACY_ENGINE_VERSION_KEY = "provider_version"
ANALYSIS_SNAPSHOT_KEY = "analysis_snapshot_sha256"
LEGACY_ANALYSIS_SNAPSHOT_KEY = "rea_snapshot_sha256"


def read_engine_version(record: Any) -> Any:
    """run.json・結果の producer から解析エンジン版を読む（新名優先・旧名を別名で受ける）。"""
    if not isinstance(record, dict):
        return None
    return record.get(ENGINE_VERSION_KEY) or record.get(LEGACY_ENGINE_VERSION_KEY)


def read_analysis_snapshot_sha(record: Any) -> Any:
    """probe の確認結果から解析 snapshot の digest を読む（新名優先・旧名を別名で受ける）。"""
    if not isinstance(record, dict):
        return None
    return record.get(ANALYSIS_SNAPSHOT_KEY) or record.get(LEGACY_ANALYSIS_SNAPSHOT_KEY)

# 突合の根拠・制限の語彙（出力 JSON に現れる固定値）
BASIS_METHOD_PATH_ONLY = "method_path_only"
BASIS_STATIC_ONLY = "static_only"
BASIS_RUNTIME_ONLY = "runtime_only"
BASIS_DYNAMIC_EXPRESSION = "dynamic_expression"
BASIS_METHOD_MISSING = "method_missing"
BASIS_QUERY_DEPENDENT = "query_dependent"
BASIS_PATH_UNRESOLVED = "path_unresolved"

LIMIT_RUNTIME_ORIGIN_NOT_RECORDED = "runtime_origin_not_recorded"
LIMIT_RUNTIME_QUERY_NOT_RETAINED = "runtime_query_not_retained"
LIMIT_NOT_IDENTITY_PROOF = "not_call_site_identity_proof"
LIMIT_MULTIPLE_CANDIDATES = "multiple_static_candidates"
LIMIT_MULTIPLE_OBSERVATIONS = "multiple_runtime_observations"
LIMIT_NOT_OBSERVED = "not_observed_in_runtime_snapshot"
LIMIT_NO_STATIC_CANDIDATE = "no_static_candidate"
LIMIT_AUTO_MATCH_WITHHELD = "automatic_matching_withheld"
LIMIT_OBSERVED_CALLS_ONLY = "observed_calls_only"


def make_id(prefix: str, *parts: str) -> str:
    """出典に由来する値だけから決定的な ID を作る。"""
    joined = _ID_SEPARATOR.join(parts)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:ID_DIGEST_LENGTH]
    return f"{prefix}-{digest}"


def _require(value: str, allowed: frozenset[str], name: str) -> None:
    if value not in allowed:
        raise ValueError(f"{name} の値が不正です: {value!r}（許可: {sorted(allowed)}）")


@dataclass(frozen=True)
class SourceLocation:
    """artifact 内の位置。UTF-16 位置と UTF-8 byte offset を混ぜない。"""

    artifact_path: str
    unit: str
    start_line: int | None = None
    start_column: int | None = None
    end_line: int | None = None
    end_column: int | None = None
    start_byte: int | None = None
    end_byte: int | None = None
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        _require(self.unit, LOCATION_UNITS, "SourceLocation.unit")
        if self.unit == "unknown" and not self.unavailable_reason:
            raise ValueError("位置の単位が不明な場合は unavailable_reason が必要です")
        if self.unit == "byte_range" and (self.start_line, self.start_column) != (None, None):
            raise ValueError("byte_range の位置に line/column を混ぜられません")
        if self.unit.startswith("line_column") and (self.start_byte, self.end_byte) != (
            None,
            None,
        ):
            raise ValueError("line/column の位置に byte offset を混ぜられません")

    def position_key(self) -> str:
        return ":".join(
            str(value)
            for value in (
                self.unit,
                self.start_line,
                self.start_column,
                self.end_line,
                self.end_column,
                self.start_byte,
                self.end_byte,
            )
        )


@dataclass(frozen=True)
class Artifact:
    """解析対象ファイル。local 絶対 root は持たず、入力 root からの相対 path で識別する。"""

    path: str
    sha256: str
    size: int
    producer: str
    producer_version: str

    def __post_init__(self) -> None:
        if self.path.startswith("/") or ".." in self.path.split("/"):
            raise ValueError("Artifact.path は入力 root からの相対 path にしてください")


@dataclass(frozen=True)
class StaticCandidate:
    """静的解析の候補。epistemic_state は「候補が AST 内に実在する」事実の状態であり、
    その API が実在・実行されることの証明ではない。"""

    id: str
    kind: str
    artifact_path: str
    artifact_sha256: str
    location: SourceLocation
    resolution: str
    epistemic_state: str
    authority: str
    method: str | None = None
    origin: str | None = None
    path: str | None = None
    expression: str | None = None
    query_dependent: bool = False
    limitations: tuple[str, ...] = ()
    # path が確定しない（引数などが入る）候補の、静的な定数を解決した表示用パターン（例: /api/v2/items/:param）。
    # 推論した値で、path（確定値）とは混ぜない
    path_pattern: str | None = None

    def __post_init__(self) -> None:
        _require(self.kind, CANDIDATE_KINDS, "StaticCandidate.kind")
        _require(self.resolution, RESOLUTIONS, "StaticCandidate.resolution")
        _require(self.epistemic_state, EPISTEMIC_STATES, "StaticCandidate.epistemic_state")


def static_candidate_id(artifact_sha256: str, location: SourceLocation, kind: str) -> str:
    """出典 digest＋位置＋kind から決定的な候補 ID を作る（Task 2 の正規化で使う）。"""
    return make_id("sc", artifact_sha256, location.artifact_path, location.position_key(), kind)


@dataclass(frozen=True)
class RuntimeObservation:
    """既存 snapshot の API 観測 1 件。snapshot digest と JSON pointer で出典へ戻れる。

    既存 snapshot は API の origin と query を保存しないため、origin は常に None、
    query_scope は not_retained。page_url の origin を API の origin とみなさない。
    """

    id: str
    snapshot_sha256: str
    json_pointer: str
    page_url: str
    method: str
    path: str
    status_code: int
    content_type: str
    sample_fields: tuple[str, ...]
    origin: None = None
    query_scope: str = QUERY_SCOPE_NOT_RETAINED
    epistemic_state: str = "observed"

    def __post_init__(self) -> None:
        if self.origin is not None:
            raise ValueError("既存 snapshot に API origin は記録されていません（捏造禁止）")
        if self.query_scope != QUERY_SCOPE_NOT_RETAINED:
            raise ValueError("既存 snapshot は query を保持しません")
        if self.epistemic_state != "observed":
            raise ValueError("RuntimeObservation の状態は observed 固定です")


@dataclass(frozen=True)
class Relation:
    """静的候補と実測の対応推論。matched でも関係そのものの状態は inferred。"""

    id: str
    static_ids: tuple[str, ...]
    runtime_ids: tuple[str, ...]
    classification: str
    epistemic_state: str
    basis: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _require(self.classification, CLASSIFICATIONS, "Relation.classification")
        _require(self.epistemic_state, EPISTEMIC_STATES, "Relation.epistemic_state")
        if self.epistemic_state == "observed":
            raise ValueError("対応関係を observed にはできません（推論です）")
        if not self.static_ids and not self.runtime_ids:
            raise ValueError("Relation は少なくとも 1 件の ID を持つ必要があります")


@dataclass(frozen=True)
class Coverage:
    """取得範囲。collection が空であることと取得不能（unavailable）を区別する。"""

    status: str
    truncated: bool
    omitted_count: int | None
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require(self.status, COVERAGE_STATUSES, "Coverage.status")


@dataclass(frozen=True)
class Diagnostic:
    """利用者向けの診断。message・next_action に絶対 path や秘密を含めない。"""

    code: str
    severity: str
    stage: str
    message: str
    next_action: str

    def __post_init__(self) -> None:
        _require(self.severity, SEVERITIES, "Diagnostic.severity")


@dataclass(frozen=True)
class Summary:
    """件数の要約。observed_api_records は取得レコード数で、API 総数や網羅率ではない。"""

    static_candidates: int
    observed_api_records: int
    inferred_relations: int
    ambiguous_relations: int
    unknown_relations: int
    matched_relations: int


def to_json_value(value: Any) -> Any:
    """dataclass・tuple を JSON 互換の値へ変換する（キー順はフィールド定義順で決定的）。"""
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_json_value(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, (tuple, list)):
        return [to_json_value(item) for item in value]
    return value
