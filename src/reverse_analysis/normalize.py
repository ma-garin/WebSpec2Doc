"""Native 解析結果を組み立てるための型と純関数（外部ツールの出力形式は持たない）。

候補の組立そのものは native 側が行う。ここには下流（reconcile・reporter・api_resolve）が使う
型（StaticNormalization・StaticCandidate 付随型）と、衝突分離・共有 endpoint の印付け・
ファイル検証の診断などの純関数だけを置く。ファイル I/O はしない。
- 候補の epistemic_state は「その構文が成果物内にある」事実の状態であり、API の実在や
  実行の証明ではない。source 本文は持たない。
- source-range は 1 始まりの行・0 始まりの UTF-16 列。
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlsplit

from reverse_analysis.files import VerifiedFile
from reverse_analysis.models import (
    Artifact,
    Coverage,
    Diagnostic,
    StaticCandidate,
    make_id,
)

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

# route は画面遷移の宣言候補であり API ではない。runtime の API 観測とは比べない。
ENDPOINT_KIND_ROUTE = "route"
LIMIT_ROUTE_CANDIDATE = "route_candidate_from_static_syntax"
LIMIT_SOURCE_MAP_FRESHNESS = "source_map_freshness_not_verified"
LIMIT_ORIGINAL_RANGE = "generated_to_original_range_not_provided"
SOURCE_MAP_PARSE_OPERATION = "parse-local-source-map"


@dataclass(frozen=True)
class CandidateProvenance:
    """route/api 候補の出典（opt-in 出力用）。解析エンジンの状態と候補の状態を分けて持つ。"""

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
    """imports edge。出典の node ID・kind をそのまま参照し、module と同一化しない。"""

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
    """source map の解決失敗・解析失敗。理由文と状態を意味そのまま残す。"""

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
    """静的側の解析結果（service が reverse_analysis.json へ組み込む）。"""

    status: str
    engine_version: str | None
    root_artifact_sha256: str | None
    artifacts: tuple[Artifact, ...]
    candidates: tuple[StaticCandidate, ...]
    coverage: Coverage
    unsupported: tuple[UnsupportedNode, ...]
    diagnostics: tuple[Diagnostic, ...]
    provenance: tuple[CandidateProvenance, ...] = ()
    dependency_edges: tuple[DependencyEdge, ...] = ()
    source_map_findings: tuple[SourceMapFinding, ...] = ()

    @property
    def provider_version(self) -> str | None:
        """旧名の別名（読取専用）。"""
        return self.engine_version




# ---------------------------------------------------------------- 候補








def _separate_collisions(grouped: Mapping[str, list[tuple[StaticCandidate, str]]]) -> list[StaticCandidate]:
    """同じ位置・kind の候補が複数あれば、どれも捨てずに出典（node と observation）で ID を分ける。

    1 位置から複数の endpoint 値・観測が出ることは 解析結果の形としてありうる。どれが正しいかは
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




# ---------------------------------------------------------------- coverage・診断






def _file_diagnostics(candidates: tuple[StaticCandidate, ...]) -> list[Diagnostic]:
    checks = (
        (LIMIT_DIGEST_MISMATCH, "static_artifact_digest_mismatch",
         "解析が参照したファイルの内容が、入力ディレクトリの現在の内容と一致しません。",
         "入力ディレクトリを変更せずに再実行してください。"),
        (LIMIT_FILE_NOT_VERIFIED, "static_artifact_not_verified",
         "解析が参照したファイルを入力ディレクトリ内で確認できませんでした（不在・リンク・範囲外）。",
         "入力ディレクトリにシンボリックリンクや外部参照が無いか確認してください。"),
        (LIMIT_SOURCE_MAP_STALE, "source_map_stale",
         "ソースマップが見つからないか、内容が解析時と一致しません。元ソースは不明として扱います。",
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


# ---------------------------------------------------------------- 出典（opt-in 出力用）








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
            f"{head}（{finding.path or '不明'}・解析の状態 {finding.provider_state}・"
            f"範囲 {finding.coverage_status}）。解析の理由: {reason or 'なし'}。元ソースは不明として扱います。",
            "source map を JS と同じ版で入力ディレクトリに置き、再実行してください。",
        ))  # fmt: skip
    return diagnostics


def expression_path_pattern(expression: str | None) -> str | None:
    """解析が path を解決できなかった呼び出し先の式から、表示用の path パターンを作る。

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
