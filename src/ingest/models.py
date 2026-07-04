"""文書由来仕様の正規化モデル。

すべての文書由来データは DocumentEvidence（ファイル・位置・引用）を持ち、
実測 evidence（SourceEvidence）と区別して出所を追跡できるようにする。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentEvidence:
    """文書上の出所（実測 evidence と対をなす文書側の根拠）。

    location はフォーマットに応じた位置表現
    （例: "画面一覧!R12" / "page 3, line 8" / "line 42" / "$.screens[2]"）。
    """

    file: str
    location: str
    quote: str = ""


@dataclass(frozen=True)
class DocumentedScreen:
    """文書に記載された画面。"""

    screen_id: str
    name: str
    url_hint: str = ""
    note: str = ""
    evidence: DocumentEvidence | None = None
    source: str = "table"
    confidence: float = 1.0


@dataclass(frozen=True)
class DocumentedField:
    """文書に記載された入力項目。

    required / max_length は文書に記載が無い場合 None（未記載は比較対象にしない）。
    """

    name: str
    physical_name: str = ""
    screen_name: str = ""
    field_type: str = ""
    required: bool | None = None
    max_length: int | None = None
    note: str = ""
    evidence: DocumentEvidence | None = None
    source: str = "table"
    confidence: float = 1.0


@dataclass(frozen=True)
class DocumentedRule:
    """文書に記載された業務ルール（計算式・限度値・権限条件など）。

    Phase 2（LLM 抽出）専用のモデル。source は常に "llm"、
    confidence は幻覚フィルタでの quote 一致度から算出され 0.9 を超えない。
    """

    rule_id: str
    kind: str
    description: str
    screen_name: str = ""
    field_name: str = ""
    expression: str = ""
    source: str = "llm"
    confidence: float = 0.7
    evidence: DocumentEvidence | None = None


@dataclass(frozen=True)
class DocumentBundle:
    """取り込んだ文書一式の正規化結果。"""

    screens: tuple[DocumentedScreen, ...]
    fields: tuple[DocumentedField, ...]
    source_files: tuple[str, ...]
    rules: tuple[DocumentedRule, ...] = ()


def document_evidence_to_dict(evidence: DocumentEvidence | None) -> dict[str, object] | None:
    """DocumentEvidence を JSON シリアライズ可能な dict に変換する。"""
    if evidence is None:
        return None
    return {
        "file": evidence.file,
        "location": evidence.location,
        "quote": evidence.quote,
    }
