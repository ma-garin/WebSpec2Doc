"""Document Assurance の共通型。全レーン共通の契約（変更は主担当のみ）。

真実の区別: 値の出所は Provenance、結論の確度は Status。AI 推論を OBSERVED にしない。
すべて frozen dataclass か dict（JSON 化可能）。元データは変更せず新しい値を返す。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# --- 出所（値がどう得られたか）---
OBSERVED = "OBSERVED"    # 原文にそのまま書かれている
DERIVED = "DERIVED"      # 決定論的な変換で原文から導いた（単位換算・分割など）
INFERRED = "INFERRED"    # AI/推測で補った。事実ではない
PROVENANCE = (OBSERVED, DERIVED, INFERRED)

# --- 結論の状態 ---
CANDIDATE, CONFIRMED, REJECTED, UNKNOWN, NOT_EVALUATED, BLOCKED = (
    "CANDIDATE", "CONFIRMED", "REJECTED", "UNKNOWN", "NOT_EVALUATED", "BLOCKED")
# --- ルール結果 ---
PASS, FAIL, NOT_APPLICABLE = "PASS", "FAIL", "NOT_APPLICABLE"
# --- テスト可能性 ---
CAN_TEST, PARTIAL, NOT_TESTABLE = "CAN_TEST", "PARTIALLY_TESTABLE", "NOT_TESTABLE"
# --- 重大度 ---
SEVERITIES = ("critical", "high", "medium", "low", "info")
# --- 検出元 ---
DETERMINISTIC, AI, HYBRID, HUMAN = "deterministic", "ai", "hybrid", "human"
# --- 準備状態 ---
DRAFT, REVIEWABLE, CONDITIONALLY_READY, READY = "DRAFT", "REVIEWABLE", "CONDITIONALLY_READY", "READY"


@dataclass(frozen=True)
class Location:
    """原文への戻り先。全文は複製せず snippet は短く、hash で改変を検出する。"""
    document_id: str
    section: str = ""          # 見出しパス "3 > 3.2"
    line_start: int = 0        # 1 始まり。0 は不明
    line_end: int = 0
    snippet: str = ""          # 120 字以内
    snippet_hash: str = ""     # sha1(snippet 元文)[:12]


@dataclass(frozen=True)
class Field:
    """構造化要件の 1 項目。value と出所を必ず対で持つ。"""
    value: str
    provenance: str            # OBSERVED/DERIVED/INFERRED


@dataclass(frozen=True)
class RequirementUnit:
    requirement_id: str        # 原文の ID（REQ-001 等）があればそれ、なければ "RU-<doc>-<連番>"
    document_id: str
    location: Location
    raw_text: str
    fields: dict[str, Field] = field(default_factory=dict)  # actor/trigger/condition/action/object/expected_result/exception/constraint/timing/quantity/state/priority/acceptance_criteria
    kind: str = "functional"   # functional/nfr/business_rule/security_rule/constraint
    parent_id: str = ""        # 分割で生じた単位は元の ID。分割自体は DERIVED
    split: bool = False
    fingerprint: str = ""      # 意味指紋（位置が変わっても同じ）

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Finding:
    finding_id: str            # "<rule_id>:<requirement_id or loc>:<n>"
    rule_id: str
    rule_version: str
    result: str                # FAIL（指摘）/ PASS / NOT_EVALUATED / NOT_APPLICABLE
    severity: str
    title: str
    why_matters: str
    reason: str                # 失敗理由（原文の語を引用）
    how_to_fix: str
    location: Location
    requirement_id: str = ""
    source: str = DETERMINISTIC
    status: str = CANDIDATE    # 確定は人が行う
    confidence: float = 0.0    # 0..1。算出根拠は confidence_basis
    confidence_basis: tuple[str, ...] = ()
    counter_evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Score:
    """0〜100。評価できなかった範囲は coverage に出し、指摘 0 件を 100 にしない。"""
    name: str
    value: float | None        # None = 評価不能（NOT_EVALUATED）
    coverage: float            # 0..1 評価できた要件の割合
    explanation: tuple[str, ...] = ()   # 減点理由の上位
    included: tuple[str, ...] = ()
    not_evaluated: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def finding_dict_valid(d: dict) -> bool:
    """Finding.to_dict() の最低要件（根拠なしは UNSUPPORTED として除外する側が使う）。"""
    loc = d.get("location") or {}
    return bool(d.get("rule_id")) and bool(loc.get("document_id")) and bool(loc.get("snippet_hash"))
