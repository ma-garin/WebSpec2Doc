"""オートヒーリング（System 05）の検証層。

利用者が指定した検証コマンドをリポジトリ内で実行し、失敗を Defect の元になる
VerifyFailure / VerifyResult へ構造化する。ここでは「何が壊れているか」という
事実だけを扱う。原因の推定や直し方の判断は agents.py 側が持つ（types.py の
方針どおり、事実と判断を型で分ける）。
"""

from __future__ import annotations

import re
import shlex
import subprocess  # nosec B404 - shell=False固定・is_command_allowedで検証済みのコマンドのみ実行
import time
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

from web.services.healing.types import Defect, VerifyFailure, VerifyResult

# ─────────────────────────── コマンド許可 ───────────────────────────

#: 破壊的操作として拒否するトークン（小文字化した文字列に対する部分一致）。
#: 利用者がコマンド文字列を自由入力するため、ここが唯一のガードになる。
#: 誤検知より見逃しを避ける方針（多少過検知でも弾く）。
DENIED_TOKENS: tuple[str, ...] = (
    "rm -rf",
    "git push",
    "git reset --hard",
    "git clean -f",
    "git clean -x",
    "sudo ",
    "mkfs",
    "shutdown",
    "reboot",
    ":(){",  # fork bomb
    "chmod 777 /",
    "chmod -r 777 /",
)

#: `curl ... | sh` のような「外部取得物をそのままシェルへ渡す」パターン。
_PIPE_TO_SHELL_RE = re.compile(r"(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(sh|bash|zsh)\b")

#: `dd if=... of=/dev/sda` 等、ディスクデバイスへ直接書き込むパターン。
_DEVICE_WRITE_RE = re.compile(r">\s*/dev/sd")

MAX_LOG_BYTES = 64 * 1024


def is_command_allowed(command: str) -> tuple[bool, str]:
    """検証コマンドが安全に実行してよいものかを判定する。

    利用者入力を検証するここが唯一のガード。手を抜かない。
    """
    if not command or not command.strip():
        return False, "検証コマンドが空です"

    lowered = command.lower()

    if _PIPE_TO_SHELL_RE.search(lowered):
        return False, "外部取得物をそのままシェルへ渡すコマンドは実行できません"

    if _DEVICE_WRITE_RE.search(lowered):
        return False, "ディスクデバイスへの書き込みを含むため実行できません"

    for token in DENIED_TOKENS:
        if token in lowered:
            return False, f"危険な操作（{token.strip()}）を含むため実行できません"

    return True, ""


# ─────────────────────────── 実行 ───────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tail_bytes(text: str, limit: int = MAX_LOG_BYTES) -> str:
    data = text.encode("utf-8", errors="replace")
    if len(data) <= limit:
        return text
    return data[-limit:].decode("utf-8", errors="replace")


def _looks_like_pytest(text: str) -> bool:
    if re.search(r"=+\s*FAILURES\s*=+", text):
        return True
    return bool(re.search(r"\d+\s+(passed|failed|error|skipped)\b", text))


def run_verification(
    *,
    repo: Path,
    command: str,
    timeout_sec: int = 1800,
    env: Mapping[str, str] | None = None,
) -> VerifyResult:
    """repo 直下で検証コマンドを実行し、構造化された結果を返す。例外は投げない。"""
    allowed, reason = is_command_allowed(command)
    if not allowed:
        return VerifyResult(
            ok=False,
            command=command,
            exit_code=-1,
            duration_sec=0.0,
            error=f"検証コマンドを拒否しました: {reason}",
        )

    try:
        args = shlex.split(command)
    except ValueError as exc:
        return VerifyResult(
            ok=False,
            command=command,
            exit_code=-1,
            duration_sec=0.0,
            error=f"検証コマンドを解釈できませんでした: {exc}",
        )

    if not args:
        return VerifyResult(
            ok=False,
            command=command,
            exit_code=-1,
            duration_sec=0.0,
            error="検証コマンドが空です",
        )

    started_at = _now_iso()
    start = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(  # nosec B603 - shell=False固定・shlex分解済み・許可リストで検証済み
            args,
            cwd=str(repo),
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        exit_code = proc.returncode
        output = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = -9
        out = exc.stdout if isinstance(exc.stdout, str) else ""
        err = exc.stderr if isinstance(exc.stderr, str) else ""
        output = out + err
    except OSError as exc:
        duration = time.monotonic() - start
        return VerifyResult(
            ok=False,
            command=command,
            exit_code=-1,
            duration_sec=duration,
            started_at=started_at,
            finished_at=_now_iso(),
            error=f"検証コマンドを起動できませんでした: {exc}",
        )

    duration = time.monotonic() - start
    finished_at = _now_iso()
    log_tail = _tail_bytes(output)

    if timed_out:
        return VerifyResult(
            ok=False,
            command=command,
            exit_code=exit_code,
            duration_sec=duration,
            log_tail=log_tail,
            started_at=started_at,
            finished_at=finished_at,
            error=f"検証が {timeout_sec} 秒で時間切れになりました",
        )

    if _looks_like_pytest(output):
        failures, counts = parse_pytest_output(output)
    else:
        failures, counts = parse_generic_output(output, exit_code)

    return VerifyResult(
        ok=exit_code == 0,
        command=command,
        exit_code=exit_code,
        duration_sec=duration,
        total=counts.get("total", 0),
        passed=counts.get("passed", 0),
        failed=counts.get("failed", 0),
        failures=tuple(failures),
        log_tail=log_tail,
        started_at=started_at,
        finished_at=finished_at,
    )


# ─────────────────────────── パース ───────────────────────────

_FAILED_LINE_RE = re.compile(r"^FAILED\s+(?P<test_id>\S+?)(?:\s+-\s+(?P<message>.+))?\s*$", re.MULTILINE)
_SECTION_HEADER_RE = re.compile(r"^_{3,}\s*(?P<name>.+?)\s*_{3,}\s*$", re.MULTILINE)
_TRACE_LOCATION_RE = re.compile(r"^(?P<file>[\w./\\-]+\.py):(?P<line>\d+): in ")
_E_LINE_RE = re.compile(r"^E\s+(?P<msg>.+)$")
_COUNT_RE = re.compile(r"(\d+)\s+(passed|failed|error|errors|skipped|xfailed|xpassed)")
#: 所要時間の表記（`in 0.02s` / `in 1.23 seconds`）。サマリ行を見分けるのに使う。
_SUMMARY_TAIL_RE = re.compile(r"\bin\s+[\d.]+\s*(s|sec|secs|seconds)\b")


def _parse_summary_counts(line: str) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0}
    for num, word in _COUNT_RE.findall(line):
        n = int(num)
        if word == "passed":
            counts["passed"] += n
        elif word in ("failed", "error", "errors"):
            # サマリ上は error も「緑ではない」という意味で failed に畳む
            counts["failed"] += n
    counts["total"] = counts["passed"] + counts["failed"]
    return counts


def parse_pytest_output(text: str) -> tuple[list[VerifyFailure], dict[str, int]]:
    """pytest の標準出力から失敗一覧とサマリを取り出す。

    失敗が 1 件も取れなくても例外は投げない（空リストを返す）。
    """
    counts = {"total": 0, "passed": 0, "failed": 0}
    for line in reversed(text.splitlines()):
        # サマリ行は `=== 3 failed, 117 passed in 12.34s ===` の形とは限らない。
        # `-q` を付けると装飾の `=` が付かず `1 failed in 0.02s` だけになるため、
        # `=` を必須にすると件数が 0 のままになり、画面に「失敗 0 / 全 0」と出る。
        # 判定条件は「所要時間の表記があり、かつ件数の語を含む」に緩める。
        if not _SUMMARY_TAIL_RE.search(line):
            continue
        parsed = _parse_summary_counts(line)
        if parsed["total"] > 0:
            counts = parsed
            break

    # `_____ test_y _____` セクション本文を先に集めておく（失敗の詳細を引くため）
    sections: dict[str, str] = {}
    headers = list(_SECTION_HEADER_RE.finditer(text))
    for idx, header in enumerate(headers):
        name = header.group("name").strip()
        if not name or name.lower().startswith("short test summary"):
            continue
        start = header.end()
        end = headers[idx + 1].start() if idx + 1 < len(headers) else len(text)
        sections[name] = text[start:end]

    failures: list[VerifyFailure] = []
    seen_ids: set[str] = set()
    for match in _FAILED_LINE_RE.finditer(text):
        test_id = match.group("test_id")
        if test_id in seen_ids:
            continue
        seen_ids.add(test_id)
        message = (match.group("message") or "").strip()

        short_name = test_id.split("::")[-1]
        section_text = ""
        for name, body in sections.items():
            if short_name in name or name in test_id:
                section_text = body
                break

        file = ""
        line_no = 0
        trace_lines: list[str] = []
        e_lines: list[str] = []
        for section_line in section_text.splitlines():
            loc = _TRACE_LOCATION_RE.match(section_line)
            if loc:
                file = loc.group("file")
                line_no = int(loc.group("line"))
            e_match = _E_LINE_RE.match(section_line)
            if e_match:
                e_lines.append(e_match.group("msg"))
            if loc or e_match:
                trace_lines.append(section_line)

        if not message and e_lines:
            message = e_lines[0]
        if not message:
            message = f"{test_id} が失敗しました"
        if not file:
            file_part = test_id.split("::")[0]
            if file_part.endswith(".py"):
                file = file_part

        traceback_tail = "\n".join(trace_lines[-20:]) if trace_lines else section_text[-2000:]

        failures.append(
            VerifyFailure(
                test_id=test_id,
                message=message,
                file=file,
                line=line_no,
                traceback_tail=traceback_tail,
            )
        )

    return failures, counts


_GENERIC_MARKERS = ("Error:", "error:", "FAIL ", "✗", "AssertionError")


def parse_generic_output(text: str, exit_code: int) -> tuple[list[VerifyFailure], dict[str, int]]:
    """pytest 以外（npm test / make / vitest 等）の出力から失敗行を拾う。

    1 件も取れず exit_code が非 0 なら、失敗を握りつぶさず 1 件だけ作る。
    """
    failures: list[VerifyFailure] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(marker in line for marker in _GENERIC_MARKERS):
            failures.append(VerifyFailure(test_id="", message=stripped[:500]))
        if len(failures) >= 20:
            break

    if not failures and exit_code != 0:
        failures.append(
            VerifyFailure(test_id="", message=f"コマンドが終了コード {exit_code} で失敗しました")
        )

    total = len(failures)
    counts = {"total": total, "passed": 0, "failed": total}
    return failures, counts


# ─────────────────────────── 欠陥化 ───────────────────────────

_STACK_LOCATION_RE = re.compile(r"([\w/.\-]+\.(?:py|js|ts|tsx|jsx)):(\d+)")


def _is_test_file(path: str) -> bool:
    name = Path(path).name
    return (
        name.startswith("test_")
        or f"/{path}/".find("/tests/") != -1
        or ".test." in name
        or ".spec." in name
    )


def guess_suspect_files(failure: VerifyFailure, repo: Path) -> list[str]:
    """failure から「直すべきファイル」の候補を最大 5 件推定する。

    repo 配下に実在するものだけを候補にし、テストファイルは後ろへ回す
    （直すべきは実装側であることが多いため）。
    """
    candidates: list[str] = []
    seen: set[str] = set()

    def add(path: str) -> None:
        if path and path not in seen and (repo / path).is_file():
            seen.add(path)
            candidates.append(path)

    if failure.file:
        add(failure.file)

    for match in _STACK_LOCATION_RE.finditer(failure.traceback_tail or ""):
        add(match.group(1))

    non_test = [c for c in candidates if not _is_test_file(c)]
    test_files = [c for c in candidates if _is_test_file(c)]
    return (non_test + test_files)[:5]


def failures_to_defects(
    failures: Sequence[VerifyFailure], *, repo: Path, source: str = "verify"
) -> list[Defect]:
    """VerifyFailure 群を Defect（事実の記録）へ変換する。原因や直し方は含めない。"""
    detected_at = _now_iso()
    defects: list[Defect] = []
    for failure in failures:
        defects.append(
            Defect(
                defect_id=uuid.uuid4().hex[:12],
                title=_build_title(failure.message),
                severity=_guess_severity(failure),
                source=source,
                test_id=failure.test_id,
                message=failure.message,
                evidence=failure.traceback_tail or failure.message,
                suspect_files=tuple(guess_suspect_files(failure, repo)),
                detected_at=detected_at,
            )
        )
    return defects


def _build_title(message: str) -> str:
    first_line = message.splitlines()[0] if message else ""
    first_line = first_line or "不明な失敗"
    if len(first_line) > 120:
        return first_line[:117] + "..."
    return first_line


def _guess_severity(failure: VerifyFailure) -> str:
    haystack = f"{failure.message}\n{failure.traceback_tail}".lower()
    if "timeout" in haystack or "importerror" in haystack or "modulenotfounderror" in haystack:
        return "critical"
    if "assertionerror" in haystack:
        return "medium"
    if "error" in haystack or "exception" in haystack or "crash" in haystack:
        return "high"
    return "medium"
