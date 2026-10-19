"""REA（rea-agents 6.7.0 固定）の実行境界と出力検証。

責務は「利用者管理の REA 実行ファイルを argv で 1 回呼び、出力が 6.7.0 の
JavaScript application analysis Evidence として整合しているかを確かめる」ところまで。
モデルへの変換は normalize.py が行う。

契約の出所（すべて公式 repository の固定タグ rea-agents-6.7.0）:
- src/cli/javascriptApplicationAnalysis.ts: CLI は Evidence を返し、失敗時は
  ``{"error": "JavaScript application analysis failed", ...}`` を返す。進捗は stderr。
- src/domain/evidence.ts: Evidence の外枠と ``ev_`` + 正規 JSON の SHA-256 による commitment。
- src/domain/javascript/javascriptApplicationAnalysis.ts: normalized_result の形と束縛。
- src/domain/javascript/javascriptApplicationGraph{,Schemas}.ts・
  javascriptApplicationEvidenceSchemas.ts: graph/node/observation/edge の形と commitment。
- src/domain/canonicalDigest.ts: 正規 JSON（キーは UTF-16 code unit 順・空白なし）。
- src/application/InvestigationProviders.ts: provider の id/name/version。
- src/cli/electronCommands.ts・src/cliCommandNames.ts: argv は
  ``analyze-javascript-application <path>``（位置引数 1 個）。scripts/rea.mjs・src/cliOutput.ts・
  src/cli/cliResultOutput.ts: ``--json`` は ``--full-output`` が無ければ結果値そのもの
  （``{ok, data, meta}`` の外枠なし）を stdout に 1 文書で書く。
- src/domain/javascript/javascriptSemanticGraph{,Schemas}.ts: semantic_graph の形と ``jsrg_`` 系 ID。
いずれも一次ソースの読解で、実 provider の実行による確認ではない。

識別子と内容の整合検査であり、暗号的な真正性（署名）の検証ではない。
provider の stderr・raw stdout は利用者に表示せず、診断にも含めない。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from reverse_analysis.models import Diagnostic

SUPPORTED_PROVIDER_VERSION = "6.7.0"
PRODUCER_NAME = "rea-agents"
ANALYZE_SUBCOMMAND = "analyze-javascript-application"

VERSION_TIMEOUT_SECONDS = 5.0
ANALYSIS_TIMEOUT_SECONDS = 120.0
STDOUT_LIMIT_BYTES = 32 * 1024 * 1024
STDERR_LIMIT_BYTES = 1024 * 1024
TERMINATE_GRACE_SECONDS = 3.0
_READ_CHUNK_BYTES = 64 * 1024
_POLL_SECONDS = 0.02

EVIDENCE_PROVIDER = {
    "id": "rea-javascript-application",
    "name": "REA JavaScript application analyzer",
    "version": "1",
}
EVIDENCE_PREDICATE = "rea.javascript-application-analysis"
EVIDENCE_OPERATION = "analyze_javascript_application"
PROVIDER_ERROR_TEXT = "JavaScript application analysis failed"

NODE_KINDS = frozenset(
    {
        "package", "installer", "artifact", "asar-entry", "electron-main",
        "electron-preload", "electron-renderer", "electron-utility", "javascript-asset",
        "javascript-chunk", "javascript-module", "javascript-expression", "source-map",
        "source-module", "browser-window", "frame", "target", "context-bridge-api",
        "ipc-channel", "ipc-handler", "worker", "service-worker", "endpoint", "storage",
        "native-addon", "native-export", "managed-assembly", "managed-module",
        "managed-type", "managed-method", "managed-field", "managed-pinvoke-import",
        "managed-native-implementation", "runtime-script-instance", "unknown",
    }
)  # fmt: skip
RELATIONS = frozenset(
    {
        "contains", "loads", "imports", "maps_to", "exposes", "sends", "invokes",
        "handles", "calls", "persists_to", "observed_as", "changed_from",
    }
)  # fmt: skip
AUTHORITIES = frozenset(
    {
        "artifact-bytes", "ast-static-analysis", "static-relationship-inference",
        "passive-cdp-runtime", "cross-layer-reconciliation", "cross-version-comparison",
        "controlled-replay", "native-analysis-provider", "managed-static-analysis",
        "historical-reference", "user-assertion", "unknown",
    }
)  # fmt: skip
_ARTIFACT_BACKED = frozenset(
    {
        "artifact-bytes", "ast-static-analysis", "controlled-replay",
        "native-analysis-provider", "managed-static-analysis",
    }
)  # fmt: skip
FACT_STATES = frozenset({"observed", "inferred", "unknown", "unavailable"})
CONFIDENCES = frozenset({"exact", "high", "medium", "low", "unknown"})
UNAVAILABLE_REASONS = frozenset(
    {"not-applicable", "not-observed", "truncated", "provider-unavailable", "unresolved", "unknown"}
)
LIMIT_UNITS = frozenset(
    {"items", "bytes", "milliseconds", "depth", "characters", "instructions", "other"}
)

_EVIDENCE_KEYS = frozenset(
    {
        "evidence_id", "subject", "provider", "analysis_profile", "predicate_type",
        "operation", "parameters", "raw_result", "normalized_result", "confidence",
        "authority", "environment", "limitations", "relationship_coverage", "locations",
        "evidence_links",
    }
)  # fmt: skip
_RESULT_KEYS = frozenset(
    {
        "input_path", "format", "root_artifact_sha256", "inventory_manifest_id",
        "inventory_graph_sha256", "integrity_contradictions", "graph", "summary",
        "statistics", "limitations", "semantic_graph",
    }
)  # fmt: skip
_STATISTICS_KEYS = frozenset(
    {
        "relevant_files", "nested_asar_containers", "text_bytes_read", "invalid_utf8_files",
        "parsed_javascript_files", "visited_ast_nodes", "findings", "modules",
        "parse_failures",
    }
)  # fmt: skip
_GRAPH_KEYS = frozenset(
    {"schema", "root_node_ids", "nodes", "edges", "coverage", "limitations", "graph_id"}
)
_OBSERVATION_KEYS = frozenset(
    {"label", "source_map_reference", "properties", "evidence", "observation_id",
     "identifier_strategy"}
)  # fmt: skip
_EDGE_KEYS = frozenset(
    {"source_node_id", "target_node_id", "relation", "properties", "evidence", "edge_id",
     "identifier_strategy"}
)  # fmt: skip
_GRAPH_EVIDENCE_KEYS = frozenset(
    {"authority", "state", "confidence", "artifact", "location", "extractor", "coverage",
     "limitations", "evidence_ids"}
)  # fmt: skip
SEMANTIC_NODE_KINDS = frozenset(
    {
        "module", "function", "parameter", "binding", "expression", "literal", "property-slot",
        "call-site", "return-site", "closure-capture", "promise", "task", "event", "listener",
        "timer", "child-process", "stdio", "signal", "config-source", "request", "response",
        "boundary", "resource", "unknown-frontier",
    }
)  # fmt: skip
SEMANTIC_FAMILIES = frozenset(
    {
        "boundary", "call-flow", "child-process", "closure", "configuration", "data-flow",
        "event", "object-flow", "promise-ownership", "request", "resource-lifecycle", "timer",
    }
)  # fmt: skip
_SEMANTIC_GRAPH_KEYS = frozenset(
    {
        "schema", "root_artifact_sha256", "application_graph_id", "root_node_ids",
        "evidence_contexts", "nodes", "relations", "fingerprints", "unknowns", "coverage",
        "limitations", "graph_id",
    }
)  # fmt: skip
_SEMANTIC_NODE_KEYS = frozenset(
    {"kind", "identity", "function_node_id", "application_node_ids", "label", "properties",
     "evidence", "node_id"}
)  # fmt: skip
_SEMANTIC_FACTS = {
    "relations": ("relation_id", "jsrg_relation_", frozenset(
        {"source_node_id", "target_node_id", "relation", "resolution", "properties", "evidence", "relation_id"})),
    "unknowns": ("unknown_id", "jsrg_unknown_", frozenset(
        {"node_id", "family", "relation_kinds", "reason", "detail", "candidate_node_ids", "evidence", "unknown_id"})),
    "fingerprints": ("fingerprint_id", "jsrg_fingerprint_", frozenset(
        {"function_node_id", "algorithm", "status", "components", "limitations", "evidence",
         "fingerprint_id", "fingerprint_sha256"})),
}  # fmt: skip
_SEMANTIC_COVERAGE_KEYS = frozenset(
    {"status", "truncated", "omitted_nodes", "omitted_relations", "limits", "families"}
)
_LOCATION_KEYS = {
    "artifact-path": frozenset({"kind", "path"}),
    "source-range": frozenset({"kind", "source", "start", "end"}),
    "file-offset-range": frozenset({"kind", "start", "end"}),
    "url": frozenset({"kind", "url"}),
    "runtime": frozenset({"kind", "capture_sha256", "target_key", "frame_key", "script_key"}),
    "native-address": frozenset({"kind", "address", "symbol"}),
    "package-export": frozenset({"kind", "package_name", "export_path"}),
}
_IDENTITY_KEYS = {
    "content-digest": ("global-exact", frozenset({"sha256"})),
    "source-map-original": (
        "source-map-exact",
        frozenset({"source_map_sha256", "original_source", "source_root", "source_sha256"}),
    ),
    "canonical-path": ("artifact-version", frozenset({"artifact_sha256", "path"})),
    "structural-fingerprint": (
        "cross-version-inference",
        frozenset({"algorithm", "fingerprint_sha256", "basis"}),
    ),
    "artifact-local-key": ("artifact-version", frozenset({"artifact_sha256", "namespace", "key"})),
    "runtime-instance": ("capture-only", frozenset({"capture_sha256", "runtime_key"})),
    "observation-fingerprint": ("observation-only", frozenset({"observation_sha256", "scope"})),
}

_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_VERSION_TOKEN = re.compile(r"^(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?)$")
_UNSAFE_SEGMENTS = frozenset({"", ".", ".."})
_LONE_SURROGATE = re.compile(r"[\ud800-\udfff]")


class InvalidProviderOutput(ValueError):
    """6.7.0 の Evidence 契約に合わない provider 出力。pointer は出力内の位置。"""

    def __init__(self, pointer: str, reason: str) -> None:
        super().__init__(f"{pointer or '/'}: {reason}")
        self.pointer = pointer or "/"
        self.reason = reason


# ---------------------------------------------------------------- 正規 JSON


def canonical_json(value: Any) -> str:
    """REA の digestCanonicalValue と同じ規則で正規 JSON 文字列を作る。"""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _js_number(value)
    if isinstance(value, str):
        return _js_string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical_json(item) for item in value) + "]"
    if isinstance(value, Mapping):
        keys = sorted(value, key=lambda key: str(key).encode("utf-16-be", "surrogatepass"))
        return "{" + ",".join(f"{_js_string(str(k))}:{canonical_json(value[k])}" for k in keys) + "}"
    raise TypeError(f"正規化できない値です: {type(value).__name__}")


def canonical_digest(value: Any) -> str:
    """正規 JSON の UTF-8 の SHA-256（hex）。"""
    encoded = canonical_json(value).encode("utf-8", "surrogatepass")
    return hashlib.sha256(encoded).hexdigest()


def _js_string(text: str) -> str:
    encoded = json.dumps(text, ensure_ascii=False)
    return _LONE_SURROGATE.sub(lambda m: f"\\u{ord(m.group()):04x}", encoded)


def _js_number(number: float) -> str:
    """ECMAScript Number::toString と同じ表記（最短の往復表現）。"""
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError("NaN・Infinity は正規化できません")
    if number == 0:
        return "0"
    sign = "-" if number < 0 else ""
    _, digit_tuple, exponent = Decimal(repr(abs(number))).normalize().as_tuple()
    digits = "".join(str(d) for d in digit_tuple)
    k = len(digits)
    n = int(exponent) + k
    if k <= n <= 21:
        body = digits + "0" * (n - k)
    elif 0 < n <= 21:
        body = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + digits
    else:
        e = n - 1
        mantissa = digits if k == 1 else digits[0] + "." + digits[1:]
        body = f"{mantissa}e{'+' if e > 0 else '-'}{abs(e)}"
    return sign + body


def parse_provider_json(data: bytes) -> Any:
    """重複キー・NaN/Infinity・不正 UTF-8 を拒否して JSON を読む。"""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidProviderOutput("", "stdout が UTF-8 ではありません") from exc

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise InvalidProviderOutput("", f"重複したキーがあります: {key!r}")
            result[key] = value
        return result

    def reject_constant(name: str) -> Any:
        raise InvalidProviderOutput("", f"JSON に {name} は使えません")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=reject_constant)
    except json.JSONDecodeError as exc:
        raise InvalidProviderOutput("", "stdout が JSON として読めません") from exc


# ---------------------------------------------------------------- プロセス境界


@dataclass(frozen=True)
class ProcessOutcome:
    """子プロセス 1 回分の結果。stderr は件数だけを持ち、本文を保持しない。"""

    state: str  # exited | timeout | cancelled | stdout_limit | stderr_limit | spawn_failed
    returncode: int | None
    stdout: bytes
    stderr_bytes: int


class _BoundedReader(threading.Thread):
    def __init__(self, stream: Any, limit: int, keep: bool, overflow: threading.Event) -> None:
        super().__init__(daemon=True)
        self._stream = stream
        self._limit = limit
        self._keep = keep
        self._overflow = overflow
        self.chunks: list[bytes] = []
        self.total = 0
        self.exceeded = False

    def run(self) -> None:
        try:
            while True:
                chunk = self._stream.read1(_READ_CHUNK_BYTES)
                if not chunk:
                    return
                self.total += len(chunk)
                if self.total > self._limit:
                    self.exceeded = True
                    self._overflow.set()
                    return
                if self._keep:
                    self.chunks.append(chunk)
        except (OSError, ValueError):
            return


def _stop_process_group(process: subprocess.Popen[bytes], grace: float) -> None:
    """自分が作った process group だけを止める。SIGTERM → grace 秒 → SIGKILL → reap。"""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            process.wait(timeout=grace if sig == signal.SIGTERM else None)
            break
        except subprocess.TimeoutExpired:
            continue
    try:
        os.killpg(process.pid, signal.SIGKILL)  # leader 終了後に残った同 group の子
    except (ProcessLookupError, PermissionError):
        pass


def run_bounded(
    argv: Sequence[str],
    *,
    timeout: float,
    cancel_event: threading.Event | None = None,
    stdout_limit: int = STDOUT_LIMIT_BYTES,
    stderr_limit: int = STDERR_LIMIT_BYTES,
    grace: float = TERMINATE_GRACE_SECONDS,
) -> ProcessOutcome:
    """argv だけで子プロセスを起動し、上限・timeout・cancel を親が管理する。

    shell を介さない。cwd と TMPDIR は自分が作った一時ディレクトリで、終了時に片付ける。
    """
    workdir = tempfile.mkdtemp(prefix="ws2d-rea-")
    try:
        env = {**os.environ, "TMPDIR": workdir}
        try:
            process = subprocess.Popen(
                list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, cwd=workdir, env=env, start_new_session=True,
                close_fds=True,
            )  # fmt: skip
        except OSError:
            return ProcessOutcome("spawn_failed", None, b"", 0)
        return _supervise(process, timeout, cancel_event, stdout_limit, stderr_limit, grace)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _supervise(
    process: subprocess.Popen[bytes],
    timeout: float,
    cancel_event: threading.Event | None,
    stdout_limit: int,
    stderr_limit: int,
    grace: float,
) -> ProcessOutcome:
    overflow = threading.Event()
    out = _BoundedReader(process.stdout, stdout_limit, True, overflow)
    err = _BoundedReader(process.stderr, stderr_limit, False, overflow)
    out.start()
    err.start()
    deadline = time.monotonic() + timeout
    state = "exited"
    try:
        while process.poll() is None:
            if overflow.is_set():
                state = "stdout_limit" if out.exceeded else "stderr_limit"
            elif cancel_event is not None and cancel_event.is_set():
                state = "cancelled"
            elif time.monotonic() >= deadline:
                state = "timeout"
            if state != "exited":
                break
            overflow.wait(_POLL_SECONDS)
    except KeyboardInterrupt:
        state = "cancelled"
    _stop_process_group(process, grace)
    for reader in (out, err):
        reader.join(timeout=grace)
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            stream.close()
    if state == "exited" and overflow.is_set():
        state = "stdout_limit" if out.exceeded else "stderr_limit"
    if state == "exited" and out.is_alive():
        state = "timeout"  # stdout を読み切れていない出力は採用しない
    stdout = b"".join(out.chunks) if state == "exited" else b""
    return ProcessOutcome(state, process.returncode, stdout, err.total)


# ---------------------------------------------------------------- 入力検証


def _diag(code: str, severity: str, stage: str, message: str, next_action: str) -> Diagnostic:
    return Diagnostic(code, severity, stage, message, next_action)


def validate_executable(command: str) -> Diagnostic | None:
    """絶対 path の利用者管理 executable だけを受け付ける（探索・導入はしない）。"""
    if not command or not os.path.isabs(command):
        return _diag(
            "missing_provider", "error", "provider",
            "REA の実行ファイルは絶対パスで指定してください。",
            "導入済みの rea 実行ファイルの絶対パスを --rea-command に指定してください。",
        )  # fmt: skip
    path = Path(command)
    if not path.exists():
        return _diag(
            "missing_provider", "error", "provider",
            "指定された REA の実行ファイルが見つかりません。",
            "rea-agents 6.7.0 を導入したうえで、その実行ファイルの絶対パスを指定してください。",
        )  # fmt: skip
    if not path.is_file() or not os.access(path, os.X_OK):
        return _diag(
            "provider_not_executable", "error", "provider",
            "指定された REA のパスは実行可能なファイルではありません。",
            "実行権限のある rea 実行ファイルを指定してください。",
        )  # fmt: skip
    return None


def validate_input_directory(path_text: str) -> tuple[Path | None, Diagnostic | None]:
    """実在する local directory だけを受け付ける。symlink・traversal・単体ファイルは拒否。"""
    rejected = _diag(
        "invalid_static_input", "error", "input",
        "静的解析の入力は、実在するローカルのディレクトリ（シンボリックリンク不可）に限ります。",
        "JS とソースマップを置いたディレクトリを --js-input に指定してください。",
    )  # fmt: skip
    if not path_text or "\x00" in path_text or ".." in Path(path_text).parts:
        return None, rejected
    candidate = Path(os.path.abspath(path_text))
    # 親成分を含む全成分を lstat し、どこかに symlink があれば root 外を指しうるため拒否する。
    for component in (*reversed(candidate.parents), candidate):
        try:
            mode = component.lstat().st_mode
        except OSError:
            return None, rejected
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            return None, rejected
    if not _tree_is_plain(candidate):
        return None, _diag(
            "invalid_static_input", "error", "input",
            "入力ディレクトリの中にシンボリックリンクまたは特殊なファイルがあるため、解析を始めませんでした。",
            "シンボリックリンク・パイプ・デバイスなどを除いた、通常のファイルとディレクトリだけの入力を指定してください。",
        )  # fmt: skip
    return candidate, None


def _tree_is_plain(root: Path) -> bool:
    """root 配下が通常ファイルとディレクトリだけか（symlink は辿らない）。読めない箇所も不可。"""
    pending = [root]
    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    mode = entry.stat(follow_symlinks=False).st_mode
                    if stat.S_ISDIR(mode):
                        pending.append(Path(entry.path))
                    elif not stat.S_ISREG(mode):
                        return False
        except OSError:
            return False
    return True


def probe_version(
    command: str,
    *,
    timeout: float = VERSION_TIMEOUT_SECONDS,
    grace: float = TERMINATE_GRACE_SECONDS,
    cancel_event: threading.Event | None = None,
) -> tuple[str | None, Diagnostic | None]:
    """``<rea> --version`` の出力全体が版 1 行だけのときに版とみなす。6.7.0 以外は unsupported。

    6.7.0 の ``rea`` は scripts/rea.mjs → cli.ts の ``Cli.create(..., {version})`` で、incur 0.6.1 の
    Cli.ts が ``writeln(options.version)`` だけを出す（e2e.test.ts の ``--version`` は ``"3.5.0\\n"``）。
    接頭辞付き（``rea 6.7.0`` 等）や複数行は別物の実行ファイルとして扱う。実 provider では未実行。
    版確認中の取り消し（cancel_event・KeyboardInterrupt）は ``provider_cancelled`` で返す。
    """
    outcome = run_bounded(
        [command, "--version"], timeout=timeout, cancel_event=cancel_event, stdout_limit=4096,
        stderr_limit=STDERR_LIMIT_BYTES, grace=grace,
    )  # fmt: skip
    if outcome.state == "cancelled":
        return None, _outcome_diag("cancelled")[1]
    if outcome.state != "exited" or outcome.returncode != 0:
        return None, _diag(
            "provider_version_unavailable", "error", "provider",
            "REA の版を確認できませんでした（応答なし・異常終了・出力超過のいずれか）。",
            "指定した実行ファイルが rea-agents 6.7.0 か確認してください。",
        )  # fmt: skip
    text = outcome.stdout.decode("utf-8", "replace")
    line = text[:-1] if text.endswith("\n") else text
    match = _VERSION_TOKEN.fullmatch(line.removesuffix("\r"))
    version = match.group(1) if match else None
    if version != SUPPORTED_PROVIDER_VERSION:
        shown = version if version else "不明"
        return version, _diag(
            "unsupported_provider_version", "error", "provider",
            f"REA の版 {shown} は対象外です（対応は {SUPPORTED_PROVIDER_VERSION} のみ。自動の代替はしません）。",
            f"rea-agents {SUPPORTED_PROVIDER_VERSION} の実行ファイルを指定してください。",
        )  # fmt: skip
    return version, None


# ---------------------------------------------------------------- Evidence 検証


def _expect(condition: bool, pointer: str, reason: str) -> None:
    if not condition:
        raise InvalidProviderOutput(pointer, reason)


def _obj(value: Any, pointer: str, keys: frozenset[str], optional: frozenset[str] = frozenset()) -> dict[str, Any]:
    _expect(isinstance(value, dict), pointer, "object ではありません")
    present = set(value)
    missing = keys - present
    extra = present - keys - optional
    _expect(not missing, pointer, f"必須キーがありません: {sorted(missing)}")
    _expect(not extra, pointer, f"未知のキーがあります: {sorted(extra)}")
    return value


def _digest(value: Any, pointer: str, prefix: str = "") -> str:
    ok = isinstance(value, str) and value.startswith(prefix) and bool(_SHA256.match(value[len(prefix):]))
    _expect(ok, pointer, f"{prefix or ''}SHA-256 の形式ではありません")
    return str(value)


def _count(value: Any, pointer: str) -> int:
    _expect(isinstance(value, int) and not isinstance(value, bool) and value >= 0, pointer, "0 以上の整数ではありません")
    return int(value)


def _text_list(value: Any, pointer: str) -> list[str]:
    _expect(isinstance(value, list), pointer, "配列ではありません")
    for index, item in enumerate(value):
        _expect(isinstance(item, str) and item != "", f"{pointer}/{index}", "空でない文字列ではありません")
    return value


def is_safe_relative_path(path: Any) -> bool:
    """REA の relativePathSchema と同じ規則に、NUL と区切り文字の混在拒否を足したもの。"""
    if not isinstance(path, str) or not path or path.startswith("/") or "\x00" in path or "\\" in path:
        return False
    return all(part not in _UNSAFE_SEGMENTS for part in path.split("/"))


def _validate_coverage(value: Any, pointer: str) -> None:
    _expect(isinstance(value, dict), pointer, "coverage が object ではありません")
    _obj(value, pointer, frozenset({"status", "truncated", "omitted_count", "limits"}))
    status, truncated, omitted = value["status"], value["truncated"], value["omitted_count"]
    _expect(isinstance(value["limits"], list), f"{pointer}/limits", "配列ではありません")
    for index, limit in enumerate(value["limits"]):
        lp = f"{pointer}/limits/{index}"
        _obj(limit, lp, frozenset({"name", "value", "unit"}))
        _expect(isinstance(limit["name"], str) and limit["name"] != "", lp, "name が不正です")
        _count(limit["value"], f"{lp}/value")
        _expect(limit["unit"] in LIMIT_UNITS, f"{lp}/unit", "unit が不正です")
    if status == "complete":
        _expect(truncated is False and omitted == 0, pointer, "complete の truncated/omitted_count が不正です")
    elif status == "partial":
        _expect(isinstance(truncated, bool), pointer, "truncated が真偽値ではありません")
        if omitted is not None:
            _count(omitted, f"{pointer}/omitted_count")
        if truncated:
            _expect(omitted is None or omitted > 0, pointer, "truncated の omitted_count は正の値か null です")
            _expect(len(value["limits"]) >= 1, pointer, "truncated には limits が必要です")
    elif status in ("unknown", "unavailable"):
        _expect(truncated is False and omitted is None, pointer, f"{status} の truncated/omitted_count が不正です")
    else:
        raise InvalidProviderOutput(f"{pointer}/status", "coverage.status が不正です")


def _validate_location(value: Any, pointer: str) -> None:
    _expect(isinstance(value, dict) and isinstance(value.get("available"), bool), pointer, "location が不正です")
    if value["available"] is False:
        _validate_unavailable(value, pointer)
        return
    _obj(value, pointer, frozenset({"available", "value"}))
    loc = value["value"]
    kind = loc.get("kind") if isinstance(loc, dict) else None
    _expect(kind in _LOCATION_KEYS, f"{pointer}/value/kind", "location.kind が不正です")
    _obj(loc, f"{pointer}/value", _LOCATION_KEYS[str(kind)])
    if kind == "artifact-path":
        _expect(is_safe_relative_path(loc["path"]), f"{pointer}/value/path", "安全な相対パスではありません")
    elif kind == "source-range":
        _expect(is_safe_relative_path(loc["source"]), f"{pointer}/value/source", "安全な相対パスではありません")
        for end in ("start", "end"):
            ep = f"{pointer}/value/{end}"
            _obj(loc[end], ep, frozenset({"line", "column"}))
            _expect(_count(loc[end]["line"], f"{ep}/line") >= 1, f"{ep}/line", "line は 1 以上です")
            _count(loc[end]["column"], f"{ep}/column")
        start, finish = loc["start"], loc["end"]
        _expect((finish["line"], finish["column"]) >= (start["line"], start["column"]), pointer, "範囲の終端が始端より前です")
    elif kind == "file-offset-range":
        _expect(_count(loc["end"], f"{pointer}/value/end") >= _count(loc["start"], f"{pointer}/value/start"), pointer, "範囲の終端が始端より前です")


def _validate_unavailable(value: Any, pointer: str) -> None:
    _obj(value, pointer, frozenset({"available", "reason", "detail"}))
    _expect(value["reason"] in UNAVAILABLE_REASONS, f"{pointer}/reason", "reason が不正です")
    _expect(isinstance(value["detail"], str) and value["detail"] != "", f"{pointer}/detail", "detail が不正です")


def _validate_graph_evidence(value: Any, pointer: str) -> None:
    ev = _obj(value, pointer, _GRAPH_EVIDENCE_KEYS)
    _expect(ev["authority"] in AUTHORITIES, f"{pointer}/authority", "authority が不正です")
    _expect(ev["state"] in FACT_STATES, f"{pointer}/state", "state が不正です")
    _expect(ev["confidence"] in CONFIDENCES, f"{pointer}/confidence", "confidence が不正です")
    artifact = ev["artifact"]
    _expect(isinstance(artifact, dict) and isinstance(artifact.get("available"), bool), f"{pointer}/artifact", "artifact が不正です")
    if artifact["available"]:
        _obj(artifact, f"{pointer}/artifact", frozenset({"available", "artifact_id", "sha256"}))
        sha = _digest(artifact["sha256"], f"{pointer}/artifact/sha256")
        _expect(artifact["artifact_id"] == f"art_{sha}", f"{pointer}/artifact/artifact_id", "artifact_id が digest を commit していません")
    else:
        _validate_unavailable(artifact, f"{pointer}/artifact")
    _validate_location(ev["location"], f"{pointer}/location")
    extractor = _obj(ev["extractor"], f"{pointer}/extractor", frozenset({"name", "version", "operation", "executable_sha256"}))
    for key in ("name", "version", "operation"):
        _expect(isinstance(extractor[key], str) and extractor[key] != "", f"{pointer}/extractor/{key}", "空でない文字列ではありません")
    if extractor["executable_sha256"] is not None:
        _digest(extractor["executable_sha256"], f"{pointer}/extractor/executable_sha256")
    _validate_coverage(ev["coverage"], f"{pointer}/coverage")
    _text_list(ev["limitations"], f"{pointer}/limitations")
    for index, item in enumerate(ev["evidence_ids"] if isinstance(ev["evidence_ids"], list) else [None]):
        _digest(item, f"{pointer}/evidence_ids/{index}", "ev_")
    _validate_evidence_rules(ev, pointer)


def _validate_evidence_rules(ev: dict[str, Any], pointer: str) -> None:
    """applicationGraphEvidenceSchema の superRefine と同じ状態規則。"""
    authority, state, confidence = ev["authority"], ev["state"], ev["confidence"]
    inferred_only = {"static-relationship-inference", "cross-layer-reconciliation", "cross-version-comparison"}
    _expect(authority not in inferred_only or state == "inferred", pointer, "推論 authority は inferred に限ります")
    _expect(authority != "unknown" or state in ("unknown", "unavailable"), pointer, "unknown authority は observed にできません")
    if state in ("unknown", "unavailable"):
        _expect(confidence == "unknown" and bool(ev["limitations"]), pointer, "unknown/unavailable は confidence=unknown と制限が必要です")
    _expect(state != "observed" or confidence != "unknown", pointer, "observed は confidence=unknown にできません")
    _expect(state != "inferred" or confidence in ("high", "medium", "low"), pointer, "inferred の confidence が不正です")
    _expect(confidence != "exact" or state == "observed", pointer, "exact は observed に限ります")
    _expect(state != "observed" or ev["location"]["available"], pointer, "observed には位置が必要です")
    _expect(state != "inferred" or bool(ev["limitations"]), pointer, "inferred には制限が必要です")
    _expect(ev["coverage"]["status"] == "complete" or bool(ev["limitations"]), pointer, "非 complete の coverage には制限が必要です")
    _expect(
        authority not in _ARTIFACT_BACKED or state == "unavailable" or ev["artifact"]["available"],
        pointer, "artifact 由来の事実には digest が必要です",
    )  # fmt: skip


def _validate_identity(value: Any, pointer: str) -> dict[str, Any]:
    strategy = value.get("strategy") if isinstance(value, dict) else None
    _expect(strategy in _IDENTITY_KEYS, f"{pointer}/strategy", "identity.strategy が不正です")
    stability, keys = _IDENTITY_KEYS[str(strategy)]
    identity = _obj(value, pointer, keys | {"strategy", "stability"})
    _expect(identity["stability"] == stability, f"{pointer}/stability", "stability が strategy と合いません")
    for key in ("sha256", "source_map_sha256", "artifact_sha256", "fingerprint_sha256", "capture_sha256", "observation_sha256"):
        if key in identity:
            _digest(identity[key], f"{pointer}/{key}")
    if strategy == "source-map-original" and identity["source_sha256"] is not None:
        _digest(identity["source_sha256"], f"{pointer}/source_sha256")
    if strategy == "canonical-path":
        _expect(is_safe_relative_path(identity["path"]), f"{pointer}/path", "安全な相対パスではありません")
    return identity


def _validate_source_map_reference(value: Any, pointer: str) -> None:
    if value is None:
        return
    ref = _obj(value, pointer, frozenset({"source_name", "source_root", "map_path", "resolution"}))
    _expect(isinstance(ref["source_name"], str), f"{pointer}/source_name", "文字列ではありません")
    _expect(ref["source_root"] is None or isinstance(ref["source_root"], str), f"{pointer}/source_root", "文字列か null です")
    # source_name は source map 内の原ソース名（../src/foo 等）であり入力 root 内の path ではないので制限しない
    _expect(is_safe_relative_path(ref["map_path"]), f"{pointer}/map_path", "安全な相対パスではありません")
    res = ref["resolution"]
    kind = res.get("kind") if isinstance(res, dict) else None
    _expect(kind in ("artifact-relative", "suffix", "unresolved"), f"{pointer}/resolution/kind", "resolution.kind が不正です")
    field = "reason" if kind == "unresolved" else "path"
    _obj(res, f"{pointer}/resolution", frozenset({"kind", field}))
    _expect(isinstance(res[field], str) and res[field] != "", f"{pointer}/resolution/{field}", "空でない文字列ではありません")
    if kind == "artifact-relative":
        _expect(is_safe_relative_path(res["path"]), f"{pointer}/resolution/path", "安全な相対パスではありません")


def _observation_matches_identity(identity: dict[str, Any], observation: dict[str, Any]) -> bool:
    """javascriptApplicationGraph.ts の observationMatchesIdentity の移植。"""
    ev = observation["evidence"]
    art, loc = ev["artifact"], ev["location"]
    art_sha = art.get("sha256") if art["available"] else None
    loc_value = loc.get("value") if loc["available"] else None
    strategy = identity["strategy"]
    if strategy == "content-digest":
        return ev["state"] == "observed" and art_sha == identity["sha256"]
    if strategy == "source-map-original":
        return _source_map_observation_matches(identity, observation, art_sha, loc_value)
    if strategy == "canonical-path":
        return (
            art_sha == identity["artifact_sha256"] and loc_value is not None
            and loc_value["kind"] == "artifact-path" and loc_value["path"] == identity["path"]
        )  # fmt: skip
    if strategy == "artifact-local-key":
        return art_sha == identity["artifact_sha256"]
    if strategy == "runtime-instance":
        return (
            ev["authority"] in ("passive-cdp-runtime", "controlled-replay") and loc_value is not None
            and loc_value["kind"] == "runtime" and loc_value["capture_sha256"] == identity["capture_sha256"]
            and identity["runtime_key"] in (loc_value["target_key"], loc_value["frame_key"], loc_value["script_key"])
        )  # fmt: skip
    if strategy == "structural-fingerprint":
        return ev["state"] == "inferred"
    return ev["state"] == "observed"


def _source_map_observation_matches(
    identity: dict[str, Any], observation: dict[str, Any], art_sha: str | None, loc_value: Any
) -> bool:
    props, ref = observation["properties"], observation["source_map_reference"]
    known = identity["source_sha256"]
    digests = [props.get("content_sha256"), props.get("source_sha256")]
    digest_ok = all(d is None or d == known for d in digests) and (known is None or known in digests)
    available = props.get("content_available")
    availability_ok = (available is not True or known is not None) and (available is not False or known is None)
    return (
        digest_ok and availability_ok and ref is not None
        and observation["evidence"]["state"] == "observed" and art_sha == identity["source_map_sha256"]
        and ref["source_name"] == identity["original_source"] and ref["source_root"] == identity["source_root"]
        and loc_value is not None and loc_value["kind"] == "artifact-path" and ref["map_path"] == loc_value["path"]
    )  # fmt: skip


def _validate_node(node: Any, pointer: str) -> dict[str, Any]:
    node = _obj(node, pointer, frozenset({"node_id", "kind", "identity", "observations"}))
    _digest(node["node_id"], f"{pointer}/node_id", "jag_node_")
    _expect(isinstance(node["kind"], str) and node["kind"] != "", f"{pointer}/kind", "kind が不正です")
    identity = _validate_identity(node["identity"], f"{pointer}/identity")
    expected = f"jag_node_{canonical_digest({'kind': node['kind'], 'identity': identity})}"
    _expect(node["node_id"] == expected, f"{pointer}/node_id", "node_id が kind と identity を commit していません")
    observations = node["observations"]
    _expect(isinstance(observations, list) and len(observations) >= 1, f"{pointer}/observations", "observation がありません")
    for index, obs in enumerate(observations):
        op = f"{pointer}/observations/{index}"
        _obj(obs, op, _OBSERVATION_KEYS)
        _expect(obs["label"] is None or (isinstance(obs["label"], str) and obs["label"] != ""), f"{op}/label", "label が不正です")
        _validate_source_map_reference(obs["source_map_reference"], f"{op}/source_map_reference")
        _expect(isinstance(obs["properties"], dict), f"{op}/properties", "properties が object ではありません")
        _validate_graph_evidence(obs["evidence"], f"{op}/evidence")
        _expect(
            obs["identifier_strategy"] == {"strategy": "semantic-content-sha256", "stability": "observation-exact"},
            f"{op}/identifier_strategy", "identifier_strategy が不正です",
        )  # fmt: skip
        semantic = {"node_id": node["node_id"], **{k: v for k, v in obs.items() if k != "observation_id"}}
        expected_obs = f"jag_observation_{canonical_digest(semantic)}"
        _expect(obs["observation_id"] == expected_obs, f"{op}/observation_id", "observation_id が内容を commit していません")
    _expect(
        any(_observation_matches_identity(identity, obs) for obs in observations),
        f"{pointer}/identity", "identity を支える observation がありません",
    )  # fmt: skip
    return node


def _validate_edge(edge: Any, pointer: str, node_kinds: Mapping[str, str]) -> None:
    edge = _obj(edge, pointer, _EDGE_KEYS)
    _expect(edge["relation"] in RELATIONS, f"{pointer}/relation", "relation が不正です")
    _expect(isinstance(edge["properties"], dict), f"{pointer}/properties", "properties が object ではありません")
    _validate_graph_evidence(edge["evidence"], f"{pointer}/evidence")
    _expect(
        edge["identifier_strategy"] == {"strategy": "semantic-content-sha256", "stability": "relationship-exact"},
        f"{pointer}/identifier_strategy", "identifier_strategy が不正です",
    )  # fmt: skip
    source, target = edge["source_node_id"], edge["target_node_id"]
    _expect(source in node_kinds and target in node_kinds, pointer, "存在しない node を参照しています")
    _expect(source != target, pointer, "自己参照の edge です")
    semantic = {k: v for k, v in edge.items() if k != "edge_id"}
    _expect(edge["edge_id"] == f"jag_edge_{canonical_digest(semantic)}", f"{pointer}/edge_id", "edge_id が内容を commit していません")


def validate_application_graph(graph: Any, pointer: str = "/normalized_result/graph") -> dict[str, Any]:
    """graph の形と、node/observation/edge/graph の各 commitment を検証する。"""
    graph = _obj(graph, pointer, _GRAPH_KEYS)
    _expect(graph["schema"] == "JavaScriptApplicationGraph", f"{pointer}/schema", "schema が不正です")
    nodes, edges, roots = graph["nodes"], graph["edges"], graph["root_node_ids"]
    _expect(isinstance(nodes, list) and len(nodes) >= 1, f"{pointer}/nodes", "node がありません")
    _expect(isinstance(edges, list), f"{pointer}/edges", "配列ではありません")
    _expect(isinstance(roots, list) and len(roots) >= 1, f"{pointer}/root_node_ids", "root がありません")
    node_kinds: dict[str, str] = {}
    for index, node in enumerate(nodes):
        checked = _validate_node(node, f"{pointer}/nodes/{index}")
        _expect(checked["node_id"] not in node_kinds, f"{pointer}/nodes/{index}", "node_id が重複しています")
        node_kinds[checked["node_id"]] = checked["kind"]
    for index, root in enumerate(roots):
        _expect(root in node_kinds, f"{pointer}/root_node_ids/{index}", "存在しない root です")
    for index, edge in enumerate(edges):
        _validate_edge(edge, f"{pointer}/edges/{index}", node_kinds)
    _validate_coverage(graph["coverage"], f"{pointer}/coverage")
    _text_list(graph["limitations"], f"{pointer}/limitations")
    semantic = {k: v for k, v in graph.items() if k != "graph_id"}
    _expect(graph["graph_id"] == f"jag_{canonical_digest(semantic)}", f"{pointer}/graph_id", "graph_id が内容を commit していません")
    return graph


def _validate_result(result: Any, subject: Any) -> dict[str, Any]:
    pointer = "/normalized_result"
    result = _obj(result, pointer, _RESULT_KEYS, frozenset({"source_selection"}))
    _expect(result["format"] == "directory", f"{pointer}/format", "directory 以外の解析結果です")
    _expect(isinstance(result["input_path"], str) and result["input_path"] != "", f"{pointer}/input_path", "input_path が不正です")
    root_sha = _digest(result["root_artifact_sha256"], f"{pointer}/root_artifact_sha256")
    _digest(result["inventory_manifest_id"], f"{pointer}/inventory_manifest_id", "agm_")
    _digest(result["inventory_graph_sha256"], f"{pointer}/inventory_graph_sha256")
    _expect(isinstance(result["integrity_contradictions"], list), f"{pointer}/integrity_contradictions", "配列ではありません")
    _text_list(result["limitations"], f"{pointer}/limitations")
    _expect(isinstance(result["summary"], dict), f"{pointer}/summary", "object ではありません")
    stats = _obj(result["statistics"], f"{pointer}/statistics", _STATISTICS_KEYS, frozenset({"skipped_javascript_files"}))
    for key, value in stats.items():
        _count(value, f"{pointer}/statistics/{key}")
    graph = validate_application_graph(result["graph"])
    _validate_semantic_graph(result["semantic_graph"], graph, root_sha)
    subject_ok = (
        isinstance(subject, dict) and subject.get("format") == "directory"
        and isinstance(subject.get("digest"), dict) and subject["digest"].get("sha256") == root_sha
    )  # fmt: skip
    _expect(subject_ok, "/subject", "subject が解析した directory の digest と一致しません")
    return result


def semantic_graph_id(semantic: Mapping[str, Any]) -> str:
    """javascriptSemanticGraph.ts の graph_id（graph_id 以外の全内容の digest）。"""
    return f"jsrg_{canonical_digest({k: v for k, v in semantic.items() if k != 'graph_id'})}"


def semantic_context_id(context: Mapping[str, Any]) -> str:
    """evidence context（location と context_id を除いた provenance）の ID。"""
    return f"jsrg_evidence_{canonical_digest({k: v for k, v in context.items() if k != 'context_id'})}"


def _sorted_unique(values: list[Any], pointer: str) -> None:
    _expect(all(_utf16(a) < _utf16(b) for a, b in zip(values, values[1:])), pointer, "整列・一意になっていません")


def _kind_of(nodes: Mapping[str, str], node_id: Any) -> str | None:
    return nodes.get(node_id) if isinstance(node_id, str) else None


def _utf16(value: Any) -> bytes:
    return str(value).encode("utf-16-be", "surrogatepass")


def _validate_semantic_graph(semantic: Any, graph: dict[str, Any], root_sha: str) -> None:
    """semantic_graph は使わないが、javascriptSemanticGraph.ts の checkGraph と analysis.ts の
    束縛のうち、内容の commitment・参照の閉包・整列を確かめる（上流の全検査ではない）。"""
    pointer = "/normalized_result/semantic_graph"
    sg = _obj(semantic, pointer, _SEMANTIC_GRAPH_KEYS)
    _expect(sg["schema"] == "JavaScriptSemanticRelationGraph", f"{pointer}/schema", "schema が不正です")
    _expect(sg["application_graph_id"] == graph["graph_id"], f"{pointer}/application_graph_id", "包含 graph を commit していません")
    _expect(sg["root_artifact_sha256"] == root_sha, f"{pointer}/root_artifact_sha256", "root artifact を commit していません")
    contexts = _semantic_contexts(sg["evidence_contexts"], f"{pointer}/evidence_contexts")
    used: set[str] = set()
    nodes = _semantic_nodes(sg["nodes"], f"{pointer}/nodes", {n["node_id"] for n in graph["nodes"]}, contexts, used)
    roots = sg["root_node_ids"]
    _expect(isinstance(roots, list) and roots and all(_kind_of(nodes, r) for r in roots), f"{pointer}/root_node_ids", "semantic node を指していません")
    _sorted_unique(roots, f"{pointer}/root_node_ids")
    for name, (id_key, prefix, keys) in _SEMANTIC_FACTS.items():
        _semantic_facts(sg[name], f"{pointer}/{name}", (id_key, prefix, keys), nodes, contexts, used)
    _expect(used == set(contexts), f"{pointer}/evidence_contexts", "参照されない context があります")
    _semantic_coverage(sg["coverage"], f"{pointer}/coverage", sg["limitations"])
    _text_list(sg["limitations"], f"{pointer}/limitations")
    _sorted_unique(sg["limitations"], f"{pointer}/limitations")
    _expect(sg["graph_id"] == semantic_graph_id(sg), f"{pointer}/graph_id", "graph_id が内容を commit していません")


def _semantic_contexts(value: Any, pointer: str) -> dict[str, dict[str, Any]]:
    _expect(isinstance(value, list), pointer, "配列ではありません")
    contexts: dict[str, dict[str, Any]] = {}
    for index, context in enumerate(value):
        cp = f"{pointer}/{index}"
        _obj(context, cp, (_GRAPH_EVIDENCE_KEYS - {"location"}) | {"context_id"})
        _expect(context["context_id"] == semantic_context_id(context), f"{cp}/context_id", "context_id が内容を commit していません")
        contexts[context["context_id"]] = context
    _sorted_unique(list(contexts) if len(contexts) == len(value) else [0, 0], pointer)
    return contexts


def _semantic_reference(value: Any, pointer: str, contexts: Mapping[str, Any], used: set[str]) -> None:
    ref = _obj(value, pointer, frozenset({"context_id", "location"}))
    context = contexts.get(ref["context_id"])
    _expect(context is not None, f"{pointer}/context_id", "存在しない context を参照しています")
    evidence = {k: v for k, v in context.items() if k != "context_id"} | {"location": ref["location"]}
    _validate_graph_evidence(evidence, pointer)
    used.add(ref["context_id"])


def _semantic_nodes(
    value: Any, pointer: str, app_ids: set[str], contexts: Mapping[str, Any], used: set[str]
) -> dict[str, str]:
    _expect(isinstance(value, list) and value, pointer, "空でない配列ではありません")
    nodes: dict[str, str] = {}
    for index, node in enumerate(value):
        np_ = f"{pointer}/{index}"
        _obj(node, np_, _SEMANTIC_NODE_KEYS)
        _expect(node["kind"] in SEMANTIC_NODE_KINDS, f"{np_}/kind", "kind が不正です")
        identity = _obj(node["identity"], f"{np_}/identity", frozenset({"artifact_sha256", "module_path", "source_range", "role_key"}))
        _digest(identity["artifact_sha256"], f"{np_}/identity/artifact_sha256")
        _expect(is_safe_relative_path(identity["module_path"]), f"{np_}/identity/module_path", "安全な相対パスではありません")
        _expect(isinstance(identity["role_key"], str) and identity["role_key"] != "", f"{np_}/identity/role_key", "role_key が不正です")
        expected = f"jsrg_node_{canonical_digest({'kind': node['kind'], 'identity': identity})}"
        _expect(node["node_id"] == expected, f"{np_}/node_id", "node_id が内容を commit していません")
        refs = node["application_node_ids"]
        _expect(isinstance(refs, list) and all(isinstance(r, str) and r in app_ids for r in refs), f"{np_}/application_node_ids", "存在しない application node を参照しています")
        _sorted_unique(refs, f"{np_}/application_node_ids")
        _expect(isinstance(node["properties"], dict), f"{np_}/properties", "object ではありません")
        _semantic_reference(node["evidence"], f"{np_}/evidence", contexts, used)
        nodes[node["node_id"]] = node["kind"]
    _sorted_unique([n["node_id"] for n in value], pointer)
    for index, node in enumerate(value):
        owner = node["function_node_id"]
        _expect(owner is None or _kind_of(nodes, owner) == "function", f"{pointer}/{index}/function_node_id", "function node を指していません")
    return nodes


def _semantic_facts(
    value: Any, pointer: str, spec: tuple[str, str, frozenset[str]],
    nodes: Mapping[str, str], contexts: Mapping[str, Any], used: set[str],
) -> None:  # fmt: skip
    """relation・unknown・fingerprint。ID は id_key 以外の全内容（fingerprint は上流の 3 項目）の digest。"""
    id_key, prefix, keys = spec
    _expect(isinstance(value, list), pointer, "配列ではありません")
    for index, fact in enumerate(value):
        fp = f"{pointer}/{index}"
        _obj(fact, fp, keys)
        _semantic_reference(fact["evidence"], f"{fp}/evidence", contexts, used)
        if id_key == "fingerprint_id":
            _expect(_kind_of(nodes, fact["function_node_id"]) == "function", f"{fp}/function_node_id", "function node を指していません")
            _expect(fact.get("fingerprint_sha256") == canonical_digest(fact.get("components")), f"{fp}/fingerprint_sha256", "components を commit していません")
            content = {k: fact.get(k) for k in ("function_node_id", "algorithm", "fingerprint_sha256")}
        else:
            ends = [fact.get(k) for k in ("source_node_id", "target_node_id", "node_id") if fact.get(k) is not None]
            ends += fact.get("candidate_node_ids") if isinstance(fact.get("candidate_node_ids"), list) else []
            _expect(all(_kind_of(nodes, e) for e in ends), fp, "存在しない semantic node を参照しています")
            content = {k: v for k, v in fact.items() if k != id_key}
        _expect(fact[id_key] == f"{prefix}{canonical_digest(content)}", f"{fp}/{id_key}", f"{id_key} が内容を commit していません")
    _sorted_unique([f[id_key] for f in value], pointer)


def _semantic_coverage(value: Any, pointer: str, limitations: Any) -> None:
    cov = _obj(value, pointer, _SEMANTIC_COVERAGE_KEYS, frozenset({"omitted_unknown_occurrences"}))
    _expect(cov["status"] in {"complete", "partial", "unknown", "unavailable"}, f"{pointer}/status", "status が不正です")
    _expect(isinstance(cov["truncated"], bool), f"{pointer}/truncated", "真偽値ではありません")
    families = cov["families"]
    _expect(isinstance(families, list) and [f.get("family") for f in families] == sorted(SEMANTIC_FAMILIES), f"{pointer}/families", "12 family が整列して揃っていません")
    for index, family in enumerate(families):
        _obj(family, f"{pointer}/families/{index}", frozenset({"family", "status", "retained_relations", "omitted_relations", "unknown_ids"}))
    if cov["status"] != "complete":
        _expect(isinstance(limitations, list) and bool(limitations), pointer, "完全でない coverage に limitation がありません")


def evidence_semantic_projection(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """evidence.ts の semanticProjection（subject は表示用の name/local_path を除く）。"""
    subject = evidence["subject"]
    return {
        "subject": None if subject is None else {
            "digest": subject.get("digest"), "format": subject.get("format"),
            "architecture": subject.get("architecture"),
        },
        **{key: evidence[key] for key in sorted(_EVIDENCE_KEYS - {"evidence_id", "subject"})},
    }  # fmt: skip


def validate_evidence(evidence: Any) -> dict[str, Any]:
    """6.7.0 の JavaScript application analysis Evidence を検証し、normalized_result を返す。"""
    if isinstance(evidence, dict) and evidence.get("error") == PROVIDER_ERROR_TEXT:
        raise InvalidProviderOutput("/error", "provider_reported_error")
    evidence = _obj(evidence, "", _EVIDENCE_KEYS)
    evidence_id = _digest(evidence["evidence_id"], "/evidence_id", "ev_")
    _expect(evidence["provider"] == EVIDENCE_PROVIDER, "/provider", "provider が 6.7.0 の JavaScript application analyzer ではありません")
    _expect(evidence["predicate_type"] == EVIDENCE_PREDICATE, "/predicate_type", "predicate_type が不正です")
    _expect(evidence["operation"] == EVIDENCE_OPERATION, "/operation", "operation が不正です")
    _expect(evidence["authority"] == "shipped-artifact", "/authority", "authority が不正です")
    _expect(evidence["confidence"] == "derived", "/confidence", "confidence が不正です")
    _expect(isinstance(evidence["parameters"], dict), "/parameters", "object ではありません")
    _expect(isinstance(evidence["limitations"], list), "/limitations", "配列ではありません")
    result = _validate_result(evidence["normalized_result"], evidence["subject"])
    expected = f"ev_{canonical_digest(evidence_semantic_projection(evidence))}"
    _expect(evidence_id == expected, "/evidence_id", "evidence_id が内容を commit していません")
    return result


# ---------------------------------------------------------------- 参照ファイルの検証


@dataclass(frozen=True)
class VerifiedFile:
    """Evidence が参照する入力 root 内のファイル。本文は保持しない。"""

    path: str
    status: str  # verified | missing | unsafe | not_regular | unreadable
    sha256: str | None = None
    size: int | None = None


def referenced_paths(result: Mapping[str, Any]) -> tuple[str, ...]:
    """Evidence が入力 root 内として参照する path（位置・source map・原ソース）。"""
    found: set[str] = set()
    graph = result["graph"]
    evidences = [obs["evidence"] for node in graph["nodes"] for obs in node["observations"]]
    evidences += [edge["evidence"] for edge in graph["edges"]]
    for ev in evidences:
        loc = ev["location"].get("value") if ev["location"]["available"] else None
        if loc and loc["kind"] == "artifact-path":
            found.add(loc["path"])
        elif loc and loc["kind"] == "source-range":
            found.add(loc["source"])
    for node in graph["nodes"]:
        for obs in node["observations"]:
            ref = obs["source_map_reference"]
            if ref is not None:
                found.add(ref["map_path"])
                if ref["resolution"]["kind"] == "artifact-relative":
                    found.add(ref["resolution"]["path"])
    return tuple(sorted(found))


def verify_file(root: Path, relative: str) -> VerifiedFile:
    """root 外・symlink・traversal を拒否し、通常ファイルなら digest と size を取る。"""
    if not is_safe_relative_path(relative):
        return VerifiedFile(relative, "unsafe")
    current = root
    for part in relative.split("/"):
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError:
            return VerifiedFile(relative, "missing")
        if stat.S_ISLNK(mode):
            return VerifiedFile(relative, "unsafe")
    if not stat.S_ISREG(mode):
        return VerifiedFile(relative, "not_regular")
    digest = hashlib.sha256()
    size = 0
    try:
        with current.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_READ_CHUNK_BYTES), b""):
                digest.update(chunk)
                size += len(chunk)
    except OSError:
        return VerifiedFile(relative, "unreadable")
    return VerifiedFile(relative, "verified", digest.hexdigest(), size)


# ---------------------------------------------------------------- 入口


@dataclass(frozen=True)
class AdapterResult:
    """adapter の結果。analysis は検証済み normalized_result（永続化しない・表示しない）。"""

    status: str  # complete | partial | unavailable | failed | cancelled
    provider_version: str | None
    diagnostics: tuple[Diagnostic, ...]
    analysis: Mapping[str, Any] | None = None
    evidence_id: str | None = None
    files: tuple[VerifiedFile, ...] = ()


_OUTCOME_DIAGNOSTICS: dict[str, tuple[str, str, str, str]] = {
    "timeout": ("failed", "provider_timeout", "REA の解析が上限時間内に終わらなかったため停止しました。",
                "入力ディレクトリを小さく分けて再実行してください。"),
    "cancelled": ("cancelled", "provider_cancelled", "REA の解析を取り消しました。結果は保存されていません。",
                  "必要なら同じ入力で再実行してください。"),
    "stdout_limit": ("failed", "provider_output_limit_exceeded", "REA の出力が上限（32MiB）を超えたため停止しました。途中までの出力は採用していません。",
                     "入力ディレクトリを小さく分けて再実行してください。"),
    "stderr_limit": ("failed", "provider_stderr_limit_exceeded", "REA の診断出力が上限（1MiB）を超えたため停止しました。",
                     "REA 単体で同じ入力を解析し、異常がないか確認してください。"),
    "spawn_failed": ("unavailable", "missing_provider", "REA を起動できませんでした。",
                     "指定した実行ファイルが起動できるか確認してください。"),
}  # fmt: skip


def run_static_analysis(
    rea_command: str,
    input_dir: str,
    *,
    cancel_event: threading.Event | None = None,
    version_timeout: float = VERSION_TIMEOUT_SECONDS,
    analysis_timeout: float = ANALYSIS_TIMEOUT_SECONDS,
    stdout_limit: int = STDOUT_LIMIT_BYTES,
    stderr_limit: int = STDERR_LIMIT_BYTES,
    grace: float = TERMINATE_GRACE_SECONDS,
    probe: Callable[..., tuple[str | None, Diagnostic | None]] = probe_version,
) -> AdapterResult:
    """Task 3 の service が呼ぶ入口。版確認 → 解析 → Evidence 検証 → 参照ファイル検証。"""
    problem = validate_executable(rea_command)
    if problem is not None:
        return AdapterResult("unavailable", None, (problem,))
    root, problem = validate_input_directory(input_dir)
    if root is None:
        return AdapterResult("failed", None, (problem,) if problem else ())
    version, problem = probe(rea_command, timeout=version_timeout, grace=grace, cancel_event=cancel_event)
    if problem is not None:
        status = "cancelled" if problem.code == "provider_cancelled" else "unavailable"
        return AdapterResult(status, version, (problem,))
    outcome = run_bounded(
        [rea_command, ANALYZE_SUBCOMMAND, str(root), "--json"], timeout=analysis_timeout,
        cancel_event=cancel_event, stdout_limit=stdout_limit, stderr_limit=stderr_limit, grace=grace,
    )  # fmt: skip
    if outcome.state in _OUTCOME_DIAGNOSTICS:
        status, diag = _outcome_diag(outcome.state)
        return AdapterResult(status, version, (diag,))
    return _accept_output(outcome, root, version)


def _outcome_diag(state: str) -> tuple[str, Diagnostic]:
    status, code, message, action = _OUTCOME_DIAGNOSTICS[state]
    severity = "warning" if status == "cancelled" else "error"
    return status, _diag(code, severity, "provider", message, action)


_STRUCTURAL_ERRORS = (TypeError, KeyError, ValueError, IndexError, AttributeError, RecursionError)


def _validate_evidence_bounded(evidence: Any) -> dict[str, Any]:
    """型不正（authority=[] 等）で検証器が落ちた場合も契約違反として扱う。KeyboardInterrupt は通す。"""
    try:
        return validate_evidence(evidence)
    except InvalidProviderOutput:
        raise
    except _STRUCTURAL_ERRORS:
        raise InvalidProviderOutput("/", "schema の型が不正です") from None


def _accept_output(outcome: ProcessOutcome, root: Path, version: str | None) -> AdapterResult:
    stage = "provider_output"
    try:
        evidence = parse_provider_json(outcome.stdout)
        result = _validate_evidence_bounded(evidence)
    except InvalidProviderOutput as exc:
        if outcome.returncode != 0 and exc.reason != "provider_reported_error":
            diag = _diag("provider_exit_nonzero", "error", stage,
                         f"REA が終了コード {outcome.returncode} で終わり、結果を返しませんでした。",
                         "REA 単体で同じ入力を解析し、異常がないか確認してください。")  # fmt: skip
        elif exc.reason == "provider_reported_error":
            diag = _diag("provider_reported_error", "error", stage,
                         "REA が解析の失敗を返しました（終了コード " + str(outcome.returncode) + "）。",
                         "REA 単体で同じ入力を解析し、失敗の理由を確認してください。")  # fmt: skip
        else:
            diag = _diag("invalid_provider_output", "error", stage,
                         f"REA の出力が 6.7.0 の Evidence 契約と一致しません（位置 {exc.pointer}）。",
                         "rea-agents 6.7.0 の実行ファイルか確認し、再実行してください。")  # fmt: skip
        return AdapterResult("failed", version, (diag,))
    if outcome.returncode != 0:
        diag = _diag("provider_exit_nonzero", "error", stage,
                     f"REA が終了コード {outcome.returncode} で終わったため、出力を採用しません。",
                     "REA 単体で同じ入力を解析し、異常がないか確認してください。")  # fmt: skip
        return AdapterResult("failed", version, (diag,))
    files = tuple(verify_file(root, path) for path in referenced_paths(result))
    if any(f.status == "unreadable" for f in files):
        diag = _diag("static_input_unreadable", "error", "input",
                     "Evidence が参照する入力ファイルの一部を読めなかったため、結果を採用しません。",
                     "入力ディレクトリ内のファイルの読み取り権限を確認して再実行してください。")  # fmt: skip
        return AdapterResult("failed", version, (diag,), files=files)
    status = "complete" if result["graph"]["coverage"]["status"] == "complete" else "partial"
    return AdapterResult(status, version, (), result, str(evidence["evidence_id"]), files)
