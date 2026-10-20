"""検証済み REA 6.7.0 Evidence から reverse analysis モデルへの純粋変換。

入力は rea_adapter.AdapterResult だけで、ファイル I/O をしない（参照ファイルの digest は
adapter が取得済み）。REA の upstream schema をそのまま標準型にしない。

- endpoint → api 候補。値は ``properties.value``、``properties.resolution == "partial"`` なら
  未解決の式（docs/javascript-application-workflows.md・javascript-application-graph.md）。
  REA の endpoint は HTTP method を持たないため method は常に None（GET と推定しない）。
- javascript-module → module 候補、source-module（source-map-original）→ source 候補。
- それ以外の kind（未知の kind を含む）は unsupported として件数と位置を保持する。
- source-range は 1 始まりの行・0 始まりの UTF-16 列（javascript-artifact-reconstruction.md）。

候補の epistemic_state は「その構文が成果物内にある」事実の状態であり、API の実在や
実行の証明ではない。source 本文・raw stdout は持たない。
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlsplit

from reverse_analysis.models import (
    Artifact,
    Coverage,
    Diagnostic,
    SourceLocation,
    StaticCandidate,
    make_id,
    static_candidate_id,
)
from reverse_analysis.rea_adapter import PRODUCER_NAME, AdapterResult, VerifiedFile

EXPRESSION_MAX_CHARS = 256
LIMITATION_MAX_CHARS = 300

LIMIT_METHOD_NOT_PROVIDED = "method_not_provided_by_provider"
LIMIT_UNRESOLVED_EXPRESSION = "provider_partial_resolution"
LIMIT_PATH_NOT_DETERMINED = "path_not_syntactically_determined"
LIMIT_QUERY_IN_VALUE = "static_value_has_query"
LIMIT_EXPRESSION_TRUNCATED = "expression_truncated"
LIMIT_DIGEST_MISMATCH = "artifact_digest_mismatch"
LIMIT_FILE_NOT_VERIFIED = "artifact_file_not_verified"
LIMIT_SOURCE_MAP_STALE = "source_map_digest_mismatch"
LIMIT_SOURCE_MAP_UNRESOLVED = "source_map_original_unresolved"
LIMIT_SOURCE_MAP_SUFFIX = "source_map_suffix_resolution"
LIMIT_ORIGINAL_CONTENT_UNAVAILABLE = "original_source_content_unavailable"
LIMIT_ORIGINAL_NOT_IN_INPUT = "original_source_not_verified_in_input"
LIMIT_MODULE_IDENTITY_ONLY = "module_identity_only"
LIMIT_LOCATION_COLLISION = "candidates_share_location"
LIMIT_SHARED_ENDPOINT = "endpoint_shared_by_candidates"

_ABSOLUTE_URL = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")
_ABSOLUTE_PATH_TEXT = re.compile(r"(?:(?<=\s)|^)/[^\s]+")

_CANDIDATE_KIND = {"endpoint": "api", "javascript-module": "module", "source-module": "source"}

# 実 REA 6.7.0 の endpoint は properties.endpoint_kind で route と network を分ける（Wave A1 実測）。
# route は画面遷移の宣言候補であり API ではない。runtime の API 観測とは比べない。
ENDPOINT_KIND_ROUTE = "route"
LIMIT_ROUTE_CANDIDATE = "route_candidate_from_static_syntax"
LIMIT_SOURCE_MAP_FRESHNESS = "source_map_freshness_not_verified"
LIMIT_ORIGINAL_RANGE = "generated_to_original_range_not_provided"
SOURCE_MAP_PARSE_OPERATION = "parse-local-source-map"


@dataclass(frozen=True)
class CandidateProvenance:
    """route/api 候補の上流出典（opt-in 出力用）。provider の状態と候補の状態を分けて持つ。"""

    candidate_id: str
    upstream_node_id: str
    upstream_observation_id: str
    endpoint_kind: str | None
    value: str | None
    mechanism: str | None
    provider_state: str
    provider_authority: str
    provider_confidence: str | None
    extractor_operation: str | None
    location: Any
    source_map_reference: Any
    provider_limitations: tuple[str, ...]


@dataclass(frozen=True)
class DependencyEdge:
    """REA graph の imports edge。上流の node ID・kind をそのまま参照し、module と同一化しない。"""

    edge_id: str
    relation: str
    source_node_id: str
    source_kind: str | None
    target_node_id: str
    target_kind: str | None
    properties: Any
    provider_state: str
    provider_authority: str
    provider_confidence: str | None
    location: Any
    extractor_operation: str | None
    coverage_status: str
    provider_limitations: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    identifier_strategy: Any


@dataclass(frozen=True)
class SourceMapFinding:
    """source map の解決失敗・解析失敗。provider の理由文と状態を意味そのまま残す。"""

    node_id: str
    kind: str
    path: str | None
    finding: str
    provider_state: str
    coverage_status: str
    provider_limitations: tuple[str, ...]


@dataclass(frozen=True)
class UnsupportedNode:
    """正規化しなかった node。黙って捨てず、kind と出力内の位置を残す。"""

    kind: str
    node_id: str
    json_pointer: str


@dataclass(frozen=True)
class StaticNormalization:
    """静的側の正規化結果（Task 3 の service が reverse_analysis.json へ組み込む）。"""

    status: str
    provider_version: str | None
    root_artifact_sha256: str | None
    artifacts: tuple[Artifact, ...]
    candidates: tuple[StaticCandidate, ...]
    coverage: Coverage
    unsupported: tuple[UnsupportedNode, ...]
    diagnostics: tuple[Diagnostic, ...]
    provenance: tuple[CandidateProvenance, ...] = ()
    dependency_edges: tuple[DependencyEdge, ...] = ()
    source_map_findings: tuple[SourceMapFinding, ...] = ()


def normalize_static(result: AdapterResult) -> StaticNormalization:
    """AdapterResult を正規化する。解析結果が無い場合は空配列と unavailable 等を明示する。"""
    if result.analysis is None:
        reason = result.diagnostics[0].code if result.diagnostics else "static_analysis_not_available"
        coverage = Coverage(result.status if result.status != "complete" else "unavailable", False, None, (reason,))
        return StaticNormalization(
            result.status, result.provider_version, None, (), (), coverage, (), result.diagnostics
        )
    analysis = result.analysis
    files = {f.path: f for f in result.files}
    version = result.provider_version or ""
    grouped: dict[str, list[tuple[StaticCandidate, str]]] = {}
    origins: dict[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = {}
    unsupported: list[UnsupportedNode] = []
    for index, node in enumerate(analysis["graph"]["nodes"]):
        kind = _node_candidate_kind(node)
        if kind is None:
            unsupported.append(UnsupportedNode(node["kind"], node["node_id"], f"/normalized_result/graph/nodes/{index}"))
            continue
        for obs in node["observations"]:
            candidate = _candidate(kind, node, obs, files)
            grouped.setdefault(candidate.id, []).append((candidate, f"{node['node_id']}#{obs['observation_id']}"))
            origins.setdefault(candidate.id, []).append((node, obs))
    ordered = _mark_shared_endpoints(_separate_collisions(grouped))
    findings = _source_map_findings(analysis["graph"]["nodes"])
    diagnostics = (
        list(result.diagnostics) + _file_diagnostics(ordered) + _collision_diagnostics(ordered)
        + _source_map_diagnostics(findings)
    )  # fmt: skip
    coverage = _coverage(analysis, unsupported, result.diagnostics)
    if findings:
        coverage = replace(coverage, limitations=tuple(dict.fromkeys(
            (*coverage.limitations, *(f"provider_source_map:{f.finding}:{f.path or '<unknown>'}" for f in findings))
        )))  # fmt: skip
    degraded = tuple(  # 候補に実在する理由だけを固定順で足す（無い理由を書かない）
        limit for limit in (LIMIT_DIGEST_MISMATCH, LIMIT_FILE_NOT_VERIFIED)
        if any(limit in c.limitations for c in ordered)
    )  # fmt: skip
    if degraded and coverage.status == "complete":
        coverage = Coverage("partial", False, None, coverage.limitations + degraded)
    status = "partial" if coverage.status == "partial" else result.status
    artifacts = tuple(
        Artifact(f.path, f.sha256 or "", f.size or 0, PRODUCER_NAME, version)
        for f in sorted(result.files, key=lambda f: f.path)
        if f.status == "verified"
    )
    return StaticNormalization(
        status, result.provider_version, analysis["root_artifact_sha256"], artifacts, ordered,
        coverage, tuple(unsupported), tuple(diagnostics),
        _provenance(ordered, grouped, origins), _dependency_edges(analysis["graph"]), findings,
    )  # fmt: skip


# ---------------------------------------------------------------- 候補


def _node_candidate_kind(node: Mapping[str, Any]) -> str | None:
    kind = _CANDIDATE_KIND.get(node["kind"])
    if kind != "api":
        return kind
    kinds = {_endpoint_kind(obs["properties"]) for obs in node["observations"]}
    return "route" if kinds == {ENDPOINT_KIND_ROUTE} else "api"


def _endpoint_kind(props: Mapping[str, Any]) -> str | None:
    """実 REA は endpoint_kind、旧手組み fixture は kind を使う。どちらも無ければ None。"""
    value = props.get("endpoint_kind", props.get("kind"))
    return value if isinstance(value, str) else None


def _candidate(kind: str, node: Mapping[str, Any], obs: Mapping[str, Any], files: Mapping[str, VerifiedFile]) -> StaticCandidate:
    ev = obs["evidence"]
    artifact_sha = ev["artifact"]["sha256"] if ev["artifact"]["available"] else ""
    location, file_limits = _location(ev, artifact_sha, files)
    state = ev["state"] if not file_limits else "unknown"
    if kind == "route":
        fields = _route_fields(obs["properties"], ev)
        if state == "observed":  # AST 構文の observed は provider 側の事実。route という意味づけは推論
            state = "inferred"
    elif kind == "api":
        fields = _api_fields(obs["properties"])
    elif kind == "source":
        fields = _source_fields(node["identity"], obs, files)
    else:
        fields = {"resolution": "exact" if state == "observed" else "unavailable", "limitations": (LIMIT_MODULE_IDENTITY_ONLY,)}
    limitations = tuple(fields.pop("limitations", ())) + file_limits + _provider_limits(ev["limitations"])
    if fields.pop("downgrade", False):
        state = "unknown"
    return StaticCandidate(
        id=static_candidate_id(artifact_sha, location, kind),
        kind=kind,
        artifact_path=location.artifact_path,
        artifact_sha256=artifact_sha,
        location=location,
        epistemic_state=state,
        authority=ev["authority"],
        limitations=tuple(dict.fromkeys(limitations)),
        **fields,
    )


def _separate_collisions(grouped: Mapping[str, list[tuple[StaticCandidate, str]]]) -> list[StaticCandidate]:
    """同じ位置・kind の候補が複数あれば、どれも捨てずに出典（node と observation）で ID を分ける。

    1 位置から複数の endpoint 値・観測が出ることは REA の schema 上ありうる。どれが正しいかは
    決められないため、全件に衝突の制限を付けて残す。
    """
    separated: list[StaticCandidate] = []
    for base_id, members in grouped.items():
        if len(members) == 1:
            separated.append(members[0][0])
            continue
        limit = f"{LIMIT_LOCATION_COLLISION}:{len(members)}"
        for candidate, provenance in members:
            separated.append(replace(
                candidate, id=make_id("sc", base_id, provenance),
                limitations=tuple(dict.fromkeys((*candidate.limitations, limit))),
            ))  # fmt: skip
    return separated


def _mark_shared_endpoints(candidates: list[StaticCandidate]) -> tuple[StaticCandidate, ...]:
    """同じ origin/path を持つ api 候補が複数あれば、照合時に 1 件へ縮めないよう件数を残す。"""
    keys = [(c.origin, c.path) if c.kind == "api" and c.path is not None else None for c in candidates]
    counts = Counter(key for key in keys if key is not None)
    marked = [
        replace(c, limitations=(*c.limitations, f"{LIMIT_SHARED_ENDPOINT}:{counts[key]}"))
        if key is not None and counts[key] > 1 else c
        for c, key in zip(candidates, keys, strict=False)
    ]  # fmt: skip
    return tuple(sorted(marked, key=lambda c: c.id))


def _location(ev: Mapping[str, Any], artifact_sha: str, files: Mapping[str, VerifiedFile]) -> tuple[SourceLocation, tuple[str, ...]]:
    loc = ev["location"]
    if not loc["available"]:
        return SourceLocation("", "unknown", unavailable_reason=f"provider_location_unavailable:{loc['reason']}"), ()
    value = loc["value"]
    if value["kind"] == "source-range":
        start, end = value["start"], value["end"]
        location = SourceLocation(
            value["source"], "line_column_utf16", start["line"], start["column"], end["line"], end["column"]
        )
        return location, _file_limits(value["source"], artifact_sha, files)
    if value["kind"] == "artifact-path":
        location = SourceLocation(value["path"], "unknown", unavailable_reason="provider_reported_artifact_path_only")
        return location, _file_limits(value["path"], artifact_sha, files)
    if value["kind"] == "file-offset-range":
        path = _unique_path_for_digest(artifact_sha, files)
        location = SourceLocation(path, "byte_range", start_byte=value["start"], end_byte=value["end"])
        return location, () if path else (LIMIT_FILE_NOT_VERIFIED,)
    return SourceLocation("", "unknown", unavailable_reason=f"unsupported_location_kind:{value['kind']}"), ()


def _file_limits(path: str, artifact_sha: str, files: Mapping[str, VerifiedFile]) -> tuple[str, ...]:
    verified = files.get(path)
    if verified is None or verified.status != "verified":
        return (LIMIT_FILE_NOT_VERIFIED,)
    if artifact_sha and verified.sha256 != artifact_sha:
        return (LIMIT_DIGEST_MISMATCH,)
    return ()


def _unique_path_for_digest(sha: str, files: Mapping[str, VerifiedFile]) -> str:
    matches = [f.path for f in files.values() if f.status == "verified" and f.sha256 == sha]
    return matches[0] if len(matches) == 1 else ""


def _api_fields(props: Mapping[str, Any]) -> dict[str, Any]:
    """endpoint の値から、構文的に確定する場合だけ origin/path を取り出す。"""
    value = props.get("value")
    limits = [LIMIT_METHOD_NOT_PROVIDED]
    if not isinstance(value, str):
        return {"resolution": "unavailable", "limitations": (*limits, LIMIT_PATH_NOT_DETERMINED)}
    expression = value[:EXPRESSION_MAX_CHARS]
    if len(value) > EXPRESSION_MAX_CHARS:
        limits.append(LIMIT_EXPRESSION_TRUNCATED)
    base = {"expression": expression, "method": None}
    if props.get("resolution") == "partial":
        return {**base, "resolution": "partial", "limitations": (*limits, LIMIT_UNRESOLVED_EXPRESSION)}
    origin, path, query = _split_static_url(value)
    if path is None:
        limits.append(LIMIT_PATH_NOT_DETERMINED)
    if query:
        limits.append(LIMIT_QUERY_IN_VALUE)
    return {**base, "resolution": "exact", "origin": origin, "path": path, "query_dependent": query, "limitations": tuple(limits)}


def _route_fields(props: Mapping[str, Any], ev: Mapping[str, Any]) -> dict[str, Any]:
    """route 宣言の値を path 候補として持つ。provider の構文状態・mechanism は制限欄で区別する。"""
    value = props.get("value")
    limits = [LIMIT_ROUTE_CANDIDATE, f"provider_syntax_state:{ev['state']}", f"provider_authority:{ev['authority']}"]
    mechanism = props.get("mechanism")
    if isinstance(mechanism, str):
        limits.append(f"provider_mechanism:{mechanism[:EXPRESSION_MAX_CHARS]}")
    if not isinstance(value, str):
        return {"resolution": "unavailable", "limitations": (*limits, LIMIT_PATH_NOT_DETERMINED)}
    expression = value[:EXPRESSION_MAX_CHARS]
    if len(value) > EXPRESSION_MAX_CHARS:
        limits.append(LIMIT_EXPRESSION_TRUNCATED)
    if props.get("resolution") == "partial" or not value.startswith("/"):
        return {"expression": expression, "resolution": "partial", "limitations": (*limits, LIMIT_PATH_NOT_DETERMINED)}
    return {"expression": expression, "path": value.split("#", 1)[0], "resolution": "exact", "limitations": tuple(limits)}


def _split_static_url(value: str) -> tuple[str | None, str | None, bool]:
    """``/path`` か ``scheme://host/path`` のときだけ分解する。正規化・補完はしない。"""
    if value.startswith("/") and not value.startswith("//"):
        without_fragment = value.split("#", 1)[0]
        path, _, query = without_fragment.partition("?")
        return None, path, "?" in without_fragment
    if _ABSOLUTE_URL.match(value):
        try:
            parts = urlsplit(value)
        except ValueError:
            return None, None, False
        if parts.scheme.lower() not in ("http", "https", "ws", "wss") or not parts.netloc:
            return None, None, False
        origin = f"{parts.scheme}://{parts.netloc}"
        return origin, parts.path or None, "?" in value.split("#", 1)[0]
    return None, None, False


def _source_fields(identity: Mapping[str, Any], obs: Mapping[str, Any], files: Mapping[str, VerifiedFile]) -> dict[str, Any]:
    """source map の正規化 path・digest・取得可否だけを信用する。原ソースは捏造しない。"""
    ref = obs["source_map_reference"]
    limits: list[str] = []
    if identity.get("strategy") != "source-map-original" or ref is None:
        return {"resolution": "unavailable", "downgrade": True, "limitations": (LIMIT_SOURCE_MAP_UNRESOLVED,)}
    map_file = files.get(ref["map_path"])
    if map_file is None or map_file.status != "verified" or map_file.sha256 != identity["source_map_sha256"]:
        return {"resolution": "unavailable", "downgrade": True, "limitations": (LIMIT_SOURCE_MAP_STALE,)}
    resolution = ref["resolution"]
    if resolution["kind"] == "unresolved":
        return {"resolution": "unavailable", "downgrade": True, "limitations": (LIMIT_SOURCE_MAP_UNRESOLVED,)}
    source_name = str(identity["original_source"])[:EXPRESSION_MAX_CHARS]
    # 元ソース名と digest は確認できるが、sourcesContent の鮮度と行単位の対応は REA が返さない（Wave A2）
    limits += [LIMIT_SOURCE_MAP_FRESHNESS, LIMIT_ORIGINAL_RANGE]
    if resolution["kind"] == "suffix":
        limits.append(LIMIT_SOURCE_MAP_SUFFIX)
    if identity["source_sha256"] is None:
        limits.append(LIMIT_ORIGINAL_CONTENT_UNAVAILABLE)
    else:
        original = files.get(resolution["path"]) if resolution["kind"] == "artifact-relative" else None
        if original is None or original.status != "verified" or original.sha256 != identity["source_sha256"]:
            limits.append(LIMIT_ORIGINAL_NOT_IN_INPUT)
    return {"resolution": "partial" if limits else "exact", "path": source_name, "limitations": tuple(limits)}


# ---------------------------------------------------------------- coverage・診断


def _coverage(analysis: Mapping[str, Any], unsupported: list[UnsupportedNode], diagnostics: tuple[Diagnostic, ...]) -> Coverage:
    graph_cov = analysis["graph"]["coverage"]
    stats = analysis["statistics"]
    limits = [f"provider_limit:{lim['name']}={lim['value']}{lim['unit']}" for lim in graph_cov["limits"]]
    status, truncated, omitted = graph_cov["status"], graph_cov["truncated"], graph_cov["omitted_count"]
    if status == "unknown":
        status, omitted = "partial", None
        limits.append("provider_coverage_unknown")
    incomplete = [f"{key}:{stats[key]}" for key in ("parse_failures", "invalid_utf8_files") if stats[key] > 0]
    if "skipped_javascript_files" not in stats:
        limits.append("skipped_javascript_files_unknown")
    elif stats["skipped_javascript_files"] > 0:
        incomplete.append(f"skipped_javascript_files:{stats['skipped_javascript_files']}")
    if analysis["integrity_contradictions"]:
        incomplete.append(f"integrity_contradictions:{len(analysis['integrity_contradictions'])}")
    if incomplete and status == "complete":
        status, omitted = "partial", None
    limits += incomplete
    if unsupported:
        kinds = sorted({u.kind for u in unsupported})
        limits.append(f"unsupported_nodes:{len(unsupported)}({','.join(kinds)})")
    limits += _provider_limits(list(analysis["graph"]["limitations"]) + list(analysis["limitations"]))
    return Coverage(status, bool(truncated), omitted, tuple(dict.fromkeys(limits)))


def _provider_limits(texts: list[str]) -> tuple[str, ...]:
    """provider の制限文を残す。絶対パスに見える部分は伏せる（stderr は使わない）。"""
    return tuple(
        "provider:" + _ABSOLUTE_PATH_TEXT.sub("<path>", text)[:LIMITATION_MAX_CHARS] for text in texts
    )


def _file_diagnostics(candidates: tuple[StaticCandidate, ...]) -> list[Diagnostic]:
    checks = (
        (LIMIT_DIGEST_MISMATCH, "static_artifact_digest_mismatch",
         "REA が参照したファイルの内容が、入力ディレクトリの現在の内容と一致しません。",
         "入力ディレクトリを変更せずに再実行してください。"),
        (LIMIT_FILE_NOT_VERIFIED, "static_artifact_not_verified",
         "REA が参照したファイルを入力ディレクトリ内で確認できませんでした（不在・リンク・範囲外）。",
         "入力ディレクトリにシンボリックリンクや外部参照が無いか確認してください。"),
        (LIMIT_SOURCE_MAP_STALE, "source_map_stale",
         "ソースマップが見つからないか、内容が REA の解析時と一致しません。元ソースは不明として扱います。",
         "ソースマップを JS と同じ版で置き直して再実行してください。"),
        (LIMIT_SOURCE_MAP_UNRESOLVED, "source_map_unresolved",
         "ソースマップから元ソースを特定できませんでした。元ソースは不明として扱います。",
         "ソースマップの sources と sourceRoot を確認してください。"),
    )  # fmt: skip
    found: list[Diagnostic] = []
    for limit, code, message, action in checks:
        count = sum(1 for c in candidates if limit in c.limitations)
        if count:
            found.append(Diagnostic(code, "warning", "static_normalize", f"{message}（{count} 件）", action))
    return found


def _collision_diagnostics(candidates: tuple[StaticCandidate, ...]) -> list[Diagnostic]:
    prefix = LIMIT_LOCATION_COLLISION + ":"
    count = sum(1 for c in candidates if any(lim.startswith(prefix) for lim in c.limitations))
    if not count:
        return []
    return [Diagnostic(
        "static_candidate_location_collision", "warning", "static_normalize",
        f"同じ位置から複数の候補が出たため、すべて別の候補として残しました（{count} 件）。どれが正しいかは判定していません。",
        "該当位置のコードを確認し、実通信の観測と照らしてください。",
    )]  # fmt: skip


# ---------------------------------------------------------------- 上流出典（opt-in 出力用）


def _provenance(
    ordered: tuple[StaticCandidate, ...],
    grouped: Mapping[str, list[tuple[StaticCandidate, str]]],
    origins: Mapping[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]],
) -> tuple[CandidateProvenance, ...]:
    """route/api 候補ごとに、REA が実際に返した node・observation の出典を残す。"""
    by_final_id: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    for base_id, members in grouped.items():
        for (_, key), origin in zip(members, origins[base_id], strict=True):
            final = base_id if len(members) == 1 else make_id("sc", base_id, key)
            by_final_id[final] = origin
    records = []
    for candidate in ordered:
        if candidate.kind not in ("route", "api"):
            continue
        node, obs = by_final_id[candidate.id]
        props, ev = obs["properties"], obs["evidence"]
        value, mechanism = props.get("value"), props.get("mechanism")
        records.append(CandidateProvenance(
            candidate.id, node["node_id"], obs["observation_id"], _endpoint_kind(props),
            value[:EXPRESSION_MAX_CHARS] if isinstance(value, str) else None,
            mechanism[:EXPRESSION_MAX_CHARS] if isinstance(mechanism, str) else None,
            ev["state"], ev["authority"], ev.get("confidence"), _operation(ev), ev["location"],
            obs.get("source_map_reference"), _provider_limits(ev["limitations"]),
        ))  # fmt: skip
    return tuple(records)


def _dependency_edges(graph: Mapping[str, Any]) -> tuple[DependencyEdge, ...]:
    """graph の imports edge だけを保存する（semantic_graph との合算・推測の補完はしない）。"""
    kinds = {node["node_id"]: node["kind"] for node in graph["nodes"]}
    edges = []
    for edge in graph["edges"]:
        if edge["relation"] != "imports":
            continue
        ev = edge["evidence"]
        edges.append(DependencyEdge(
            edge["edge_id"], edge["relation"], edge["source_node_id"], kinds.get(edge["source_node_id"]),
            edge["target_node_id"], kinds.get(edge["target_node_id"]), _bounded(edge["properties"]),
            ev["state"], ev["authority"], ev.get("confidence"), ev["location"], _operation(ev),
            ev["coverage"]["status"], _provider_limits(ev["limitations"]), tuple(ev.get("evidence_ids", ())),
            edge.get("identifier_strategy"),
        ))  # fmt: skip
    return tuple(sorted(edges, key=lambda e: e.edge_id))


def _operation(ev: Mapping[str, Any]) -> str | None:
    extractor = ev.get("extractor")
    return extractor.get("operation") if isinstance(extractor, Mapping) else None


def _bounded(value: Any) -> Any:
    """properties を保存用に写す。長い文字列は切り、絶対パスに見える部分は伏せる。"""
    if isinstance(value, Mapping):
        return {key: _bounded(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_bounded(item) for item in value]
    if isinstance(value, str):
        return _ABSOLUTE_PATH_TEXT.sub("<path>", value)[:EXPRESSION_MAX_CHARS]
    return value


# ---------------------------------------------------------------- source map の診断


def _source_map_findings(nodes: list[Mapping[str, Any]]) -> tuple[SourceMapFinding, ...]:
    """REA が返した source map の未解決（resolution_status）と解析失敗（unknown node）を拾う。"""
    findings = []
    for node in nodes:
        for obs in node["observations"]:
            props, ev = obs["properties"], obs["evidence"]
            if node["kind"] == "source-map" and props.get("resolution_status") not in (None, "resolved"):
                path, finding = props.get("declared_url"), f"map_{props['resolution_status']}"
            elif node["kind"] == "unknown" and props.get("operation") == SOURCE_MAP_PARSE_OPERATION:
                path, finding = props.get("path"), "map_parse_failed"
            else:
                continue
            findings.append(SourceMapFinding(
                node["node_id"], node["kind"], _bounded(path) if isinstance(path, str) else None, finding,
                ev["state"], ev["coverage"]["status"], _provider_limits(ev["limitations"]),
            ))  # fmt: skip
    return tuple(sorted(findings, key=lambda f: (f.path or "", f.finding, f.node_id)))


_SOURCE_MAP_TEXT = {
    "map_not-found": "宣言された source map が入力内に見つかりませんでした",
    "map_parse_failed": "source map を読めませんでした",
}


def _source_map_diagnostics(findings: tuple[SourceMapFinding, ...]) -> list[Diagnostic]:
    diagnostics = []
    for finding in findings:
        head = _SOURCE_MAP_TEXT.get(finding.finding, f"source map を解決できませんでした（{finding.finding}）")
        reason = "／".join(lim.removeprefix("provider:") for lim in finding.provider_limitations[:2])
        diagnostics.append(Diagnostic(
            f"provider_source_{finding.finding.replace('-', '_')}", "warning", "static_normalize",
            f"{head}（{finding.path or '不明'}・REA の状態 {finding.provider_state}・"
            f"範囲 {finding.coverage_status}）。REA の理由: {reason or 'なし'}。元ソースは不明として扱います。",
            "source map を JS と同じ版で入力ディレクトリに置き、再実行してください。",
        ))  # fmt: skip
    return diagnostics


def expression_path_pattern(expression: str | None) -> str | None:
    """REA が path を解決できなかった呼び出し先の式から、表示用の path パターンを作る。

    テンプレート文字列（`/a/${x}`）と文字列連結（'/a/' + x + '/b'）を扱い、変数部分を :param にする。
    先頭が変数（解決できないベース URL など）のときは、後ろだけを path と見なさず None を返す（推測しない）。
    推論した値なので、呼び出し側は「候補」としてだけ扱うこと。
    """
    text = (expression or "").strip()
    if not text:
        return None
    if text[0] == "`" and text[-1] == "`":
        body = re.sub(r"\$\{[^}]*\}", ":param", text[1:-1])
        return body if body.startswith("/") else None
    parts = [p.strip() for p in re.split(r"\s*\+\s*", text)]
    out: list[str] = []
    for i, part in enumerate(parts):
        lit = re.fullmatch(r"""(['"`])(.*)\1""", part, re.S)
        if lit:
            out.append(re.sub(r"\$\{[^}]*\}", ":param", lit.group(2)))
        elif out:
            out.append(":param")
        else:
            return None  # 先頭が解決できない値: 後ろの path だけでは呼び出し先にならない
    path = "".join(out)
    return path if path.startswith("/") else None
