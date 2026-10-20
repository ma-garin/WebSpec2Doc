"""明示 CLI 用の reverse analysis 実行（runtime 読込 → REA 静的解析 → 正規化 → 突合 → 保存）。

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
from reverse_analysis.normalize import StaticNormalization, UnsupportedNode, normalize_static
from reverse_analysis.rea_adapter import AdapterResult, run_static_analysis
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

# REA 6.7.0 の既知制限（対応できたと称さないため、毎回 JSON と CLI に明示する）
LIMIT_PROVIDER_NO_HTTP_METHOD = "provider_endpoint_http_method_not_provided"
LIMIT_PROVIDER_NO_ROUTE = "provider_route_nodes_not_provided"
LIMIT_STATIC_SYNTAX_ONLY = "static_candidate_is_syntax_presence_only"
PROVIDER_LIMITATIONS = (
    LIMIT_PROVIDER_NO_HTTP_METHOD,
    LIMIT_PROVIDER_NO_ROUTE,
    LIMIT_STATIC_SYNTAX_ONLY,
)
_ROUTE_ABSENT_CODE = "provider_route_not_provided"

_KNOWN_LIMIT_DIAGNOSTICS = (
    Diagnostic(
        "provider_endpoint_method_not_provided", "info", STAGE_RECONCILE,
        "REA 6.7.0 の endpoint は HTTP method を返さないため、静的 API 候補と実測の対応は unknown に留めています。",
        "対応付けが必要な候補は、表示された出典の位置を開いて呼び出しの method を目で確かめてください。",
    ),
    Diagnostic(
        _ROUTE_ABSENT_CODE, "info", STAGE_RECONCILE,
        "REA の出力に route 宣言（endpoint_kind=route）がありません。REA が route として出すのは対応するルーターの宣言だけで、独自の遷移処理からは取得できません（利用不可。0 件見つかったという意味ではありません）。",
        "画面ルートは既存クロールの画面一覧で確認してください。",
    ),
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
    rea_command: str
    output_dir: str
    include_provider_evidence: bool = False


@dataclass(frozen=True)
class ReverseAnalysisOutcome:
    """実行結果。output_path が None なら成果物は保存されていない。"""

    status: str
    exit_code: int
    document: dict[str, Any] | None
    output_path: Path | None
    diagnostics: tuple[Diagnostic, ...]


StaticRunner = Callable[..., AdapterResult]


def run_reverse_analysis(
    request: ReverseAnalysisRequest,
    *,
    cancel_event: threading.Event | None = None,
    static_runner: StaticRunner = run_static_analysis,
) -> ReverseAnalysisOutcome:
    """全段を結線して reverse_analysis.json を保存する。保存できたときだけ output_path を返す。"""
    output_dir, problem = prepare_output_dir(
        request.output_dir, request.js_input, request.runtime_snapshot
    )
    if output_dir is None:
        return _not_saved("failed", (problem,) if problem else ())
    cancel = cancel_event or threading.Event()

    runtime: RuntimeInput | None = None
    adapter: AdapterResult | None = None
    try:
        runtime = load_runtime_observations(Path(request.runtime_snapshot))
        if cancel.is_set():
            adapter = _cancelled_adapter()
        else:
            adapter = static_runner(request.rea_command, request.js_input, cancel_event=cancel)
    except KeyboardInterrupt:
        cancel.set()
        adapter = _cancelled_adapter()
    if runtime is None:
        runtime = _cancelled_runtime()
    static = _with_provider_limits(normalize_static(adapter))
    if static.status in ("complete", "partial"):  # REA が解析できた入力だけを補う（失敗・中止は候補を足さない）
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
        provider_version=static.provider_version,
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
            if request.include_provider_evidence
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
        *(
            diag
            for diag in _KNOWN_LIMIT_DIAGNOSTICS
            if diag.code != _ROUTE_ABSENT_CODE or not _has_route(static)
        ),
    ]


def _has_route(static: StaticNormalization) -> bool:
    return any(c.kind == "route" for c in static.candidates)


def _unsupported_diagnostic(node: UnsupportedNode) -> Diagnostic:
    return Diagnostic(
        "static_node_unsupported",
        "info",
        "normalize",
        f"未対応の node を候補にしていません（kind={node.kind} node_id={node.node_id} "
        f"provider_pointer={node.json_pointer}）。",
        "この node の内容が必要な場合は、REA の出力の該当位置を直接確認してください。",
    )


def _with_provider_limits(static: StaticNormalization) -> StaticNormalization:
    known = tuple(
        lim for lim in PROVIDER_LIMITATIONS if lim != LIMIT_PROVIDER_NO_ROUTE or not _has_route(static)
    )
    limits = tuple(dict.fromkeys(static.coverage.limitations + known))
    return replace(static, coverage=replace(static.coverage, limitations=limits))


def _cancelled_adapter() -> AdapterResult:
    diag = Diagnostic(
        "provider_cancelled", "warning", "provider",
        "静的解析を取り消しました。静的候補は保存されていません。",
        "必要なら同じ入力で再実行してください。",
    )  # fmt: skip
    return AdapterResult("cancelled", None, (diag,))


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
