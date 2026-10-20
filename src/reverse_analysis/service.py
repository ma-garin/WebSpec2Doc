"""明示 CLI 用の reverse analysis 実行（runtime 読込 → Native 静的解析 → 突合 → 保存）。

既存の report.json・snapshot は読み取りのみ。出力は専用ディレクトリの
reverse_analysis.json だけで、入力 root 内・snapshot の親ディレクトリ内・symlink へは書かない。
static candidate は「構文が JS 内にある」事実であり、API が実行された仕様へ昇格させない。
"""

from __future__ import annotations

import os
import stat
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from reverse_analysis import api_resolve
from reverse_analysis.models import Coverage, Diagnostic
from reverse_analysis.native import run_static_analysis
from reverse_analysis.normalize import StaticNormalization, UnsupportedNode
from reverse_analysis.reconcile import reconcile, summarize
from reverse_analysis.reporter import (
    EXIT_CODES,
    OUTPUT_FILENAME,
    TMP_PREFIX,
    TMP_SUFFIX,
    build_document,
    write_document,
)
from reverse_analysis.runtime import RuntimeInput, load_runtime_observations

STAGE_OUTPUT = "output"
STAGE_RECONCILE = "reconcile"

# Native 解析の既知制限（対応できたと称さないため、毎回 JSON と CLI に明示する）
LIMIT_STATIC_SYNTAX_ONLY = "static_candidate_is_syntax_presence_only"
LIMIT_DYNAMIC_IMPORT_CANDIDATE_ONLY = "dynamic_import_or_unconventional_router_is_candidate_only"
LIMIT_NO_RUNTIME_VALUE_EVALUATION = "runtime_values_not_evaluated_ast_syntax_only"
ENGINE_LIMITATIONS = (
    LIMIT_STATIC_SYNTAX_ONLY,
    LIMIT_DYNAMIC_IMPORT_CANDIDATE_ONLY,
    LIMIT_NO_RUNTIME_VALUE_EVALUATION,
)
# 旧名（外部から参照されている場合の別名）
PROVIDER_LIMITATIONS = ENGINE_LIMITATIONS

_KNOWN_LIMIT_DIAGNOSTICS = (
    Diagnostic(
        "runtime_origin_not_recorded", "info", STAGE_RECONCILE,
        "既存 snapshot は API の接続先 origin と query を記録していないため、一致しても同一の呼び出しとは断定しません。",
        "接続先の確認が必要な場合は、ブラウザの開発者ツールで実際の通信先を確かめてください。",
    ),
)  # fmt: skip


@dataclass(frozen=True)
class ReverseAnalysisRequest:
    js_input: str
    runtime_snapshot: str
    output_dir: str
    include_provenance: bool = False


@dataclass(frozen=True)
class ReverseAnalysisOutcome:
    """実行結果。output_path が None なら成果物は保存されていない。"""

    status: str
    exit_code: int
    document: dict[str, Any] | None
    output_path: Path | None
    diagnostics: tuple[Diagnostic, ...]


StaticRunner = Callable[..., Any]  # run_static_analysis(js_input, *, cancel_event) -> .normalization を持つ結果


def run_reverse_analysis(
    request: ReverseAnalysisRequest,
    *,
    cancel_event: threading.Event | None = None,
    static_runner: StaticRunner | None = None,
) -> ReverseAnalysisOutcome:
    """全段を結線して reverse_analysis.json を保存する。保存できたときだけ output_path を返す。"""
    output_dir, problem = prepare_output_dir(
        request.output_dir, request.js_input, request.runtime_snapshot
    )
    if output_dir is None:
        return _not_saved("failed", (problem,) if problem else ())
    cancel = cancel_event or threading.Event()

    runtime: RuntimeInput | None = None
    static: StaticNormalization | None = None
    try:
        runtime = load_runtime_observations(Path(request.runtime_snapshot))
        if cancel.is_set():
            static = _cancelled_static()
        else:
            runner = static_runner or run_static_analysis  # 既定は同一プロセス内の Native 解析
            static = runner(request.js_input, cancel_event=cancel).normalization
    except KeyboardInterrupt:
        cancel.set()
        static = _cancelled_static()
    if runtime is None:
        runtime = _cancelled_runtime()
    if static is None:
        static = _cancelled_static()
    static = _with_engine_limits(static)
    if static.status in ("complete", "partial"):  # 解析できた入力だけを補う（失敗・中止は候補を足さない）
        refined, extra = api_resolve.refine(static.candidates, Path(request.js_input), "",
                                            {a.path: a.sha256 for a in static.artifacts})
        static = replace(static, candidates=refined, diagnostics=(*static.diagnostics, *extra))
    document = _document(request, runtime, static)

    try:
        path = write_document(output_dir, document)
    except OSError:
        return _not_saved(document["status"], (_write_failed(),), document)
    status = document["status"]
    return ReverseAnalysisOutcome(
        status, EXIT_CODES[status], document, path, tuple(_diagnostics(runtime, static))
    )


def prepare_output_dir(
    output_text: str, js_input: str, snapshot: str
) -> tuple[Path | None, Diagnostic | None]:
    """専用出力ディレクトリを検証して作る。入力 root 内・snapshot 親内・symlink・共用 dir は拒否。"""
    output = Path(output_text)
    try:
        return _prepare_output_dir(output, Path(js_input), Path(snapshot))
    except (OSError, RuntimeError):  # 権限不正・symlink loop など。生の例外文（path 入り）は出さない
        return None, _write_failed()


def _prepare_output_dir(
    output: Path, js_input: Path, snapshot: Path
) -> tuple[Path | None, Diagnostic | None]:
    if _has_symlink_component(output) or _is_link(output / OUTPUT_FILENAME):
        return None, _output_rejected("出力先またはその親ディレクトリに symlink は指定できません。")
    resolved = output.resolve()
    for protected in (js_input.resolve(), snapshot.resolve().parent):
        if resolved == protected or protected in resolved.parents:
            return None, _output_rejected(
                "出力先が入力ディレクトリまたは snapshot と同じ場所の中にあります。"
            )
    if output.exists() and not output.is_dir():
        return None, _output_rejected("出力先がディレクトリではありません。")
    if output.is_dir() and any(not _owned_entry(p.name) for p in output.iterdir()):
        return None, _output_rejected("出力先に reverse_analysis.json 以外のファイルがあります。")
    output.mkdir(parents=True, exist_ok=True)
    return output, None


def _has_symlink_component(output: Path) -> bool:
    """出力先自身と既存の親成分を lstat で調べる（resolve 前なので symlink 経由を見逃さない）。"""
    absolute = Path(os.path.abspath(output))
    return any(_is_link(part) for part in (absolute, *absolute.parents))


def _is_link(path: Path) -> bool:
    try:
        return stat.S_ISLNK(path.lstat().st_mode)
    except FileNotFoundError:
        return False


def _owned_entry(name: str) -> bool:
    return name == OUTPUT_FILENAME or (name.startswith(TMP_PREFIX) and name.endswith(TMP_SUFFIX))


def _document(
    request: ReverseAnalysisRequest, runtime: RuntimeInput, static: StaticNormalization
) -> dict[str, Any]:
    relations = reconcile(static.candidates, runtime.observations)
    return build_document(
        status=_overall_status(static.status, runtime.coverage.status),
        engine_version=static.engine_version,
        static_root_label=Path(request.js_input).name,
        static_artifact_sha256=static.root_artifact_sha256,
        runtime_snapshot_sha256=runtime.snapshot_sha256,
        artifacts=static.artifacts,
        static_candidates=static.candidates,
        runtime_observations=runtime.observations,
        relations=relations,
        static_coverage=static.coverage,
        runtime_coverage=runtime.coverage,
        diagnostics=_diagnostics(runtime, static),
        summary=summarize(static.candidates, runtime.observations, relations),
        provider_evidence=(
            {
                "candidate_provenance": static.provenance,
                "dependency_edges": static.dependency_edges,
                "source_map_findings": static.source_map_findings,
            }
            if request.include_provenance
            else None
        ),
    )


def _overall_status(static_status: str, runtime_status: str) -> str:
    statuses = {static_status, runtime_status}
    for status in ("cancelled", "failed", "unavailable", "partial"):
        if status in statuses:
            return status
    return "complete"


def _diagnostics(runtime: RuntimeInput, static: StaticNormalization) -> list[Diagnostic]:
    return [
        *runtime.diagnostics,
        *static.diagnostics,
        *(_unsupported_diagnostic(node) for node in static.unsupported),
        *_KNOWN_LIMIT_DIAGNOSTICS,
    ]


def _unsupported_diagnostic(node: UnsupportedNode) -> Diagnostic:
    return Diagnostic(
        "static_node_unsupported",
        "info",
        "normalize",
        f"未対応の node を候補にしていません（kind={node.kind} node_id={node.node_id} "
        f"provider_pointer={node.json_pointer}）。",
        "この node の内容が必要な場合は、--reverse-provenance で保存される出典（provenance）の該当位置を確認してください。",
    )


def _with_engine_limits(static: StaticNormalization) -> StaticNormalization:
    limits = tuple(dict.fromkeys(static.coverage.limitations + ENGINE_LIMITATIONS))
    return replace(static, coverage=replace(static.coverage, limitations=limits))


def _cancelled_static() -> StaticNormalization:
    diag = Diagnostic(
        "static_analysis_cancelled", "warning", "static_analysis",
        "静的解析を取り消しました。静的候補は保存されていません。",
        "必要なら同じ入力で再実行してください。",
    )  # fmt: skip
    coverage = Coverage("cancelled", False, None, (diag.code,))
    return StaticNormalization("cancelled", None, None, (), (), coverage, (), (diag,))


def _cancelled_runtime() -> RuntimeInput:
    diag = Diagnostic(
        "runtime_input_cancelled", "warning", "runtime_input",
        "snapshot の読み込み中に取り消しました。実測は保存されていません。",
        "必要なら同じ入力で再実行してください。",
    )  # fmt: skip
    return RuntimeInput(None, (), Coverage("cancelled", False, None), (diag,))


def _output_rejected(message: str) -> Diagnostic:
    return Diagnostic(
        "output_location_rejected", "error", STAGE_OUTPUT, message,
        "入力とは別の、reverse analysis 専用の空のディレクトリを --output に指定してください。",
    )  # fmt: skip


def _write_failed() -> Diagnostic:
    return Diagnostic(
        "output_write_failed", "error", STAGE_OUTPUT,
        "reverse_analysis.json を保存できませんでした。成果物はありません。",
        "出力先ディレクトリの書き込み権限と空き容量を確認して再実行してください。",
    )  # fmt: skip


def _not_saved(
    status: str, diagnostics: tuple[Diagnostic, ...], document: dict[str, Any] | None = None
) -> ReverseAnalysisOutcome:
    code = EXIT_CODES[status] or EXIT_CODES["failed"]
    return ReverseAnalysisOutcome(status, code, document, None, diagnostics)
