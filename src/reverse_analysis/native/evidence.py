"""Native 解析の組立: 入力ディレクトリの JS → ParsedFile 群 → StaticNormalization。

REA 形の出力を経由せず、parse／extract／routes／module_graph／sourcemap の結果を
既存の StaticNormalization（reverse_analysis.models／normalize の型）へ直接組み立てる。
外部プロセスは起動しない。ファイル本文・絶対 path は結果に載せない。

候補の epistemic_state: AST で確認した構文は observed、route という意味づけは inferred、
解決できない式は unknown ではなく partial＋limitation（通る/通らないを断定しない）。
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import threading
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from reverse_analysis.canonical import canonical_digest
from reverse_analysis.files import VerifiedFile, validate_input_directory
from reverse_analysis.models import (
    Artifact,
    Coverage,
    Diagnostic,
    SourceLocation,
    StaticCandidate,
    static_candidate_id,
    to_json_value,
)
from reverse_analysis.native import extract as _extract
from reverse_analysis.native import module_graph as _module_graph
from reverse_analysis.native import parser as _parser
from reverse_analysis.native import routes as _routes
from reverse_analysis.native import sourcemap as _sourcemap
from reverse_analysis.normalize import (
    LIMIT_MODULE_IDENTITY_ONLY,
    LIMIT_ROUTE_CANDIDATE,
    CandidateProvenance,
    StaticNormalization,
    _collision_diagnostics,
    _mark_shared_endpoints,
    _separate_collisions,
)

NATIVE_VERSION = "1.0.0"
ENGINE_VERSION = f"webspec2doc-native/{NATIVE_VERSION}"
PRODUCER_NAME = "webspec2doc-native"
AUTHORITY = "webspec2doc-native-ast"

JS_SUFFIXES = (".js", ".mjs", ".cjs", ".jsx")
SKIP_DIRECTORIES = frozenset({"node_modules", ".git"})
MAX_FILES = 5000
MAX_FILE_BYTES = 8 * 1024 * 1024

LIMIT_FILE_TOO_LARGE = "skipped_files_too_large"
LIMIT_FILE_LIMIT = "file_count_limit_reached"
LIMIT_PARSE_ERRORS = "parse_failures"
LIMIT_UNREADABLE = "unreadable_files"

_VERSION_FIELD = (
    "engine_version"
    if "engine_version" in {f.name for f in dataclasses.fields(StaticNormalization)}
    else "provider_version"
)


@dataclass(frozen=True)
class NativeResult:
    """解析の結果。normalization をそのまま service が使う。evidence_id は結果全体の commitment。"""

    status: str  # complete | partial | unavailable | failed | cancelled
    engine_version: str | None
    diagnostics: tuple[Diagnostic, ...]
    normalization: StaticNormalization
    files: tuple[VerifiedFile, ...] = ()
    evidence_id: str | None = None


class _Cancelled(Exception):
    pass


def analyze(
    js_input: str | Path,
    cancel_event: threading.Event | None = None,
    *,
    parser: Any = None,
    extract_fn: Callable[[Any], Iterable[StaticCandidate]] | None = None,
    graph_fn: Callable[[list[Any]], Any] | None = None,
    sourcemap_fn: Callable[[Any, Path], Any] | None = None,
) -> NativeResult:
    """js_input（実在ディレクトリ）の JS を解析する。引数の *_fn は結合部を差し替える試験用の口。"""
    root, rejected = validate_input_directory(str(js_input))
    if root is None:
        diagnostics = (rejected,) if rejected else ()
        return _empty("unavailable", diagnostics, "invalid_static_input")
    try:
        return _analyze(
            root, cancel_event or threading.Event(),
            parser or _parser.get_parser(), extract_fn or _extract.extract_api_candidates,
            graph_fn or _module_graph.build_module_graph, sourcemap_fn or _sourcemap.resolve_source_map,
        )
    except _Cancelled:
        diag = Diagnostic(
            "static_analysis_cancelled", "warning", "static_analysis",
            "静的解析を取り消しました。結果は保存されていません。", "必要なら同じ入力で再実行してください。",
        )
        return _empty("cancelled", (diag,), "static_analysis_cancelled")


def run_static_analysis(js_input: str | Path, *, cancel_event: threading.Event | None = None) -> NativeResult:
    """service が呼ぶ入口。外部プロセスを起動しない。"""
    return analyze(js_input, cancel_event)


def _empty(status: str, diagnostics: tuple[Diagnostic, ...], reason: str) -> NativeResult:
    coverage = Coverage(status if status != "complete" else "unavailable", False, None, (reason,))
    return NativeResult(status, None, diagnostics, _normalization(status, None, (), (), coverage, (), diagnostics))


def _normalization(
    status: str, digest: str | None, artifacts: tuple[Artifact, ...], candidates: tuple[StaticCandidate, ...],
    coverage: Coverage, unsupported: tuple[Any, ...], diagnostics: tuple[Diagnostic, ...], **extra: Any,
) -> StaticNormalization:
    version = ENGINE_VERSION if status not in ("unavailable", "cancelled") else None
    return StaticNormalization(**{
        "status": status, _VERSION_FIELD: version, "root_artifact_sha256": digest, "artifacts": artifacts,
        "candidates": candidates, "coverage": coverage, "unsupported": unsupported, "diagnostics": diagnostics,
        **extra,
    })


# ---------------------------------------------------------------- 本体


def _analyze(root: Path, cancel: threading.Event, parser: Any, extract_fn: Any, graph_fn: Any, map_fn: Any) -> NativeResult:
    sources, verified, notes = _read_inputs(root, cancel)
    diagnostics: list[Diagnostic] = []
    limits: list[str] = list(notes)
    parsed_files: list[Any] = []
    for relative, data in sources:
        _check(cancel)
        try:
            parsed = parser.parse(relative, data)
        except Exception as error:  # 1 ファイルの失敗で全体を止めない
            limits.append(f"{LIMIT_PARSE_ERRORS}:{relative}")
            diagnostics.append(_parse_diagnostic(relative, type(error).__name__))
            continue
        if getattr(parsed, "has_error", False):
            limits.append(f"{LIMIT_PARSE_ERRORS}:{relative}")
        parsed_files.append(parsed)
    if not verified:
        diag = Diagnostic(
            "static_input_no_javascript", "error", "static_analysis",
            "入力ディレクトリに解析できる JavaScript ファイルがありませんでした。",
            "JS を保存したディレクトリを指定してください。",
        )
        return _empty("unavailable", (*diagnostics, diag), "no_javascript_files")

    candidates, provenance, edges, findings, map_files = _collect(parsed_files, root, cancel, extract_fn, graph_fn, map_fn)
    verified = {**{v.path: v for v in verified}, **{v.path: v for v in map_files}}
    route_result = _routes.extract_routes(parsed_files)
    route_cands = [_route_candidate(r, parsed_files) for r in route_result.candidates]
    candidates.extend(route_cands)
    provenance.extend(_route_provenance(route_cands, route_result.candidates))
    candidates.extend(_module_candidate(p) for p in parsed_files)

    grouped: dict[str, list[tuple[StaticCandidate, str]]] = {}
    for index, cand in enumerate(candidates):
        grouped.setdefault(cand.id, []).append((cand, f"{cand.kind}#{index}"))
    ordered = _mark_shared_endpoints(_separate_collisions(grouped))
    ids = {c.id for c in ordered}
    provenance_final = tuple(p for p in provenance if p.candidate_id in ids)

    diagnostics += _collision_diagnostics(ordered)
    diagnostics += [_finding_diagnostic(f) for f in findings]
    coverage = _coverage(limits, findings, route_result.limitations)
    status = "partial" if coverage.status == "partial" else "complete"
    files = tuple(sorted(verified.values(), key=lambda f: f.path))
    artifacts = tuple(
        Artifact(f.path, f.sha256 or "", f.size or 0, PRODUCER_NAME, ENGINE_VERSION)
        for f in files if f.status == "verified"
    )
    root_digest = canonical_digest([[a.path, a.sha256] for a in artifacts])
    normalization = _normalization(
        status, root_digest, artifacts, ordered, coverage, (), tuple(diagnostics),
        provenance=provenance_final, dependency_edges=tuple(edges), source_map_findings=tuple(findings),
    )
    commitment = canonical_digest({
        "provider": ENGINE_VERSION, "files": [[a.path, a.sha256] for a in artifacts],
        "candidates": sorted(c.id for c in ordered),
    })
    return NativeResult(status, ENGINE_VERSION, tuple(diagnostics), normalization, files, commitment)


def _check(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise _Cancelled


def _read_inputs(root: Path, cancel: threading.Event) -> tuple[list[tuple[str, bytes]], list[VerifiedFile], list[str]]:
    """JS を決定的な順序で 1 回だけ読む。sha256 は読んだ本文から取り、VerifiedFile と一致させる。"""
    sources: list[tuple[str, bytes]] = []
    verified: list[VerifiedFile] = []
    notes: list[str] = []
    too_large = unreadable = 0
    for directory, subdirs, names in os.walk(root, followlinks=False):
        subdirs[:] = sorted(d for d in subdirs if d not in SKIP_DIRECTORIES)
        for name in sorted(names):
            _check(cancel)
            full = Path(directory) / name
            if not name.endswith(JS_SUFFIXES) or full.is_symlink():
                continue
            relative = full.relative_to(root).as_posix()
            if len(sources) >= MAX_FILES:
                notes.append(f"{LIMIT_FILE_LIMIT}:{MAX_FILES}")
                return sources, verified, notes
            try:
                if full.stat().st_size > MAX_FILE_BYTES:
                    too_large += 1
                    continue
                data = full.read_bytes()
            except OSError:
                unreadable += 1
                continue
            sources.append((relative, data))
            verified.append(VerifiedFile(relative, "verified", hashlib.sha256(data).hexdigest(), len(data)))
    if too_large:
        notes.append(f"{LIMIT_FILE_TOO_LARGE}:{too_large}")
    if unreadable:
        notes.append(f"{LIMIT_UNREADABLE}:{unreadable}")
    return sources, verified, notes


def _collect(
    parsed_files: list[Any], root: Path, cancel: threading.Event, extract_fn: Any, graph_fn: Any, map_fn: Any
) -> tuple[list[StaticCandidate], list[CandidateProvenance], tuple[Any, ...], tuple[Any, ...], list[VerifiedFile]]:
    candidates: list[StaticCandidate] = []
    provenance: list[CandidateProvenance] = []
    findings: list[Any] = []
    map_files: list[VerifiedFile] = []
    for parsed in parsed_files:
        _check(cancel)
        for cand in extract_fn(parsed):
            candidates.append(cand)
            provenance.append(_provenance(cand, "api", cand.expression, "native.extract"))
        if getattr(parsed, "source_map_ref", None):
            result = map_fn(parsed, root)
            findings.extend(result.findings)
            if result.map_path and result.map_sha256:
                map_files.append(VerifiedFile(result.map_path, "verified", result.map_sha256, None))
            candidates.extend(_source_candidates(result))
    _check(cancel)
    graph = graph_fn(parsed_files)
    edges = tuple(sorted(graph.edges, key=lambda e: e.edge_id))
    return candidates, provenance, edges, tuple(sorted(findings, key=lambda f: (f.path or "", f.finding, f.node_id))), map_files


# ---------------------------------------------------------------- 候補の生成


def _route_candidate(route: _routes.RouteCandidate, parsed_files: list[Any]) -> StaticCandidate:
    sha = next((p.sha256 for p in parsed_files if p.path == route.file), "")
    location = SourceLocation(route.file, "line_column_utf16", route.line, route.col, route.end_line, route.end_col)
    limits = (
        LIMIT_ROUTE_CANDIDATE, f"route_confidence:{route.confidence}", f"route_basis:{route.basis}", *route.limitations,
    )
    return StaticCandidate(
        id=static_candidate_id(sha, location, "route"), kind="route", artifact_path=route.file, artifact_sha256=sha,
        location=location, resolution=route.resolution, epistemic_state="inferred", authority=AUTHORITY,
        path=route.path, expression=route.expression or None, limitations=tuple(dict.fromkeys(limits)),
    )


def _module_candidate(parsed: Any) -> StaticCandidate:
    location = SourceLocation(parsed.path, "line_column_utf16", 1, 0, 1, 0)
    return StaticCandidate(
        id=static_candidate_id(parsed.sha256, location, "module"), kind="module", artifact_path=parsed.path,
        artifact_sha256=parsed.sha256, location=location, resolution="exact", epistemic_state="observed",
        authority=AUTHORITY, limitations=(LIMIT_MODULE_IDENTITY_ONLY,),
    )


def _source_candidates(result: Any) -> list[StaticCandidate]:
    if not result.map_path or not result.map_sha256:
        return []
    location = SourceLocation(result.map_path, "unknown", unavailable_reason="generated_to_original_range_not_provided")
    return [
        StaticCandidate(
            id=static_candidate_id(result.map_sha256 + name, location, "source"),
            kind="source", artifact_path=result.map_path, artifact_sha256=result.map_sha256, location=location,
            resolution="partial", epistemic_state="observed", authority=AUTHORITY, path=name[:256],
            limitations=("source_map_freshness_not_verified", "generated_to_original_range_not_provided"),
        )
        for name in result.sources
    ]


def _provenance(cand: StaticCandidate, kind: str, value: str | None, operation: str) -> CandidateProvenance:
    observation = canonical_digest({
        "candidate": cand.id, "location": to_json_value(cand.location), "expression": value, "operation": operation,
    })[:16]
    return CandidateProvenance(
        cand.id, cand.artifact_path, observation, kind, value, operation, cand.epistemic_state, cand.authority,
        None, operation, to_json_value(cand.location), None, cand.limitations,
    )


def _route_provenance(cands: list[StaticCandidate], routes: tuple[_routes.RouteCandidate, ...]) -> list[CandidateProvenance]:
    records = []
    for cand, route in zip(cands, routes, strict=True):
        record = _provenance(cand, "route", route.expression, "native.routes")
        records.append(replace(record, mechanism=route.basis, provider_confidence=route.confidence))
    return records


# ---------------------------------------------------------------- 診断・coverage


def _parse_diagnostic(relative: str, error_name: str) -> Diagnostic:
    return Diagnostic(
        "static_parse_failed", "warning", "static_analysis",
        f"{relative} を構文解析できませんでした（{error_name}）。このファイルの候補は含まれません。",
        "ファイルが壊れていないか、JavaScript として読めるか確認してください。",
    )


def _finding_diagnostic(finding: Any) -> Diagnostic:
    return Diagnostic(
        f"source_map_{finding.finding.replace('-', '_')}", "warning", "static_analysis",
        f"source map を解決できませんでした（{finding.path or '不明'}・{finding.finding}）。元ソースは不明として扱います。",
        "source map を JS と同じ版で入力ディレクトリに置き、再実行してください。",
    )


def _coverage(limits: list[str], findings: tuple[Any, ...], route_limits: Iterable[str]) -> Coverage:
    counted = Counter(limit.split(":", 1)[0] for limit in limits)
    incomplete = bool(
        counted[LIMIT_PARSE_ERRORS] or counted[LIMIT_FILE_TOO_LARGE] or counted[LIMIT_UNREADABLE]
        or counted[LIMIT_FILE_LIMIT] or findings
    )
    all_limits = list(limits) + [f"source_map:{f.finding}:{f.path or '<unknown>'}" for f in findings]
    all_limits += [lim for lim in route_limits if lim not in all_limits]
    return Coverage("partial" if incomplete else "complete", bool(counted[LIMIT_FILE_LIMIT]), None,
                    tuple(dict.fromkeys(all_limits)))
