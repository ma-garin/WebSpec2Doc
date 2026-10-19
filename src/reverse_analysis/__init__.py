"""ローカル JS の静的候補と既存 snapshot の実測を限定的に対応付ける reverse analysis。"""

from __future__ import annotations

from reverse_analysis.models import (
    SCHEMA_VERSION,
    Artifact,
    Coverage,
    Diagnostic,
    Relation,
    RuntimeObservation,
    SourceLocation,
    StaticCandidate,
    Summary,
    make_id,
    static_candidate_id,
    to_json_value,
)
from reverse_analysis.reconcile import reconcile, summarize
from reverse_analysis.runtime import RuntimeInput, load_runtime_observations

__all__ = [
    "SCHEMA_VERSION",
    "Artifact",
    "Coverage",
    "Diagnostic",
    "Relation",
    "RuntimeInput",
    "RuntimeObservation",
    "SourceLocation",
    "StaticCandidate",
    "Summary",
    "load_runtime_observations",
    "make_id",
    "reconcile",
    "static_candidate_id",
    "summarize",
    "to_json_value",
]
