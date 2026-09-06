"""03 AutoRun を指揮者から呼ぶためのアダプタ（テスト実行）。

02 が作ったテストを回して、通ったか落ちたかを返すだけ。実行そのものは
playwright_executor が持っており、ここは呼び方を monitor.py::run_now に
揃える以上のことをしない。同じ実行を 2 通りの呼び方で持つと、
結果の置き場所がずれて「実行結果」画面から見えなくなる。

**非同期で走る。**run() は Playwright の完了を待たずに handle を返し、続きは
スレッドが進める。同期で待っていたとき、指揮者の `_await_step`（10 秒ごとの
確認・2 時間の上限・中止の確認）が一度も通らず、801 件のテストで数時間
ブロックし、その間の中止が効かなかった（実測）。

進捗と結果は `<domain>/qa_process/.run/<handle>.json` に書く。プロセスを跨いで
読めるものだけが「起きたこと」であり、メモリの上だけの状態は再起動で消える。
子プロセスの pid も同じ JSON に書く。書いておかないと、指揮者のプロセスが
落ちたあとに node（playwright test）を止める手段が誰にも無くなる。
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from web.services.orchestration.ports import (
    Context,
    Readiness,
    StepResult,
    StepStatus,
)

logger = logging.getLogger(__name__)

#: 回すテストファイル。02 が作ったものを優先し、無ければ 03 のものを使う。
_SPEC_CANDIDATES: tuple[tuple[str, ...], ...] = (
    ("testcases", "testcases.spec.ts"),
    ("qa_process", "autorun.spec.ts"),
)

_NO_SPEC = "02 テスト自動化でこのサイトのテストを作ってください"
_NO_HANDLE = "実行の記録がありません"
_NO_TESTS = "テストが 1 件も実行されませんでした。テストファイルを確認してください"
_UNREADABLE = "テスト結果を読めませんでした（{path}）"
_RUNNING = "テストを実行しています"
_PROC_GONE = "実行中にプロセスが止まりました。もう一度実行してください"
_CANCELLED = "テスト実行を中止しました"
_STALE = "テスト結果が更新されませんでした（前の実行の結果が残っています）"

#: 1 回の実行に許す時間。指揮者の段の上限（params）をそのまま使う。
_DEFAULT_TIMEOUT_SEC = 7200

#: 実行中カードの見込み表示（案・T2/T8）。1 件あたりの目安秒数
#: （実測: 801 件 ≒ 10 分 → 801*0.75秒 ≒ 600秒）。
_SEC_PER_TEST = 0.75

_STATE_DIR = ".run"
_HANDLE_PREFIX = "run-"
_HEX = frozenset("0123456789abcdef")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _spec_path(out_dir: Path, domain: str) -> Path | None:
    for parts in _SPEC_CANDIDATES:
        candidate = out_dir / domain / Path(*parts)
        if candidate.is_file():
            return candidate
    return None


def _report_relpath(domain: str) -> str:
    """結果ファイルの out_dir からの相対パス。画面もこのファイルを読む。"""
    return f"{domain}/qa_process/playwright_report.json"


def _meta_path(out_dir: Path, domain: str) -> Path:
    """02 が生成したテストケース表のメタ（総件数）。spec と同じ場所に並ぶ。"""
    return out_dir / domain / "testcases" / "testcases.spec.meta.json"


def _progress_path(out_dir: Path, domain: str) -> Path:
    """Playwright 実行の進捗 ndjson。run() が使う output_dir と同じ場所
    （playwright_executor.run_playwright が 1 件終わるごとに 1 行追記する）。
    """
    return out_dir / domain / "qa_process" / "playwright_progress.ndjson"


def _test_total(out_dir: Path, domain: str) -> int:
    """テストの総件数。読めなければ 0（無いことを『多い』と誤解させない）。"""
    try:
        data = json.loads(_meta_path(out_dir, domain).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    tests = data.get("tests") if isinstance(data, dict) else None
    return len(tests) if isinstance(tests, list) else 0


def _test_done(out_dir: Path, domain: str) -> int:
    """終わった件数。進捗 ndjson は 1 行 = 1 件の完了通知なので行数で数える。"""
    try:
        with _progress_path(out_dir, domain).open("r", encoding="utf-8") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def _progress_summary(out_dir: Path, domain: str) -> str:
    """実行中カードの 1 文（案・T2/T8）。総件数が分からなければ空文字を返し、
    呼び出し側の既定文言（テストを実行しています）に任せる——0 件と言い切ると
    「進んでいない」と誤読される。
    """
    total = _test_total(out_dir, domain)
    if total <= 0:
        return ""
    done = min(_test_done(out_dir, domain), total)
    eta_min = max(1, round(total * _SEC_PER_TEST / 60))
    return f"テスト {total} 件を実行中（済み {done} 件・目安 約 {eta_min} 分）"


def _state_path(out_dir: Path, domain: str, handle: str) -> Path | None:
    """handle が指す進捗ファイル。形が違えば None（外から来た文字列なので）。"""
    text = str(handle or "").strip()
    ident = text[len(_HANDLE_PREFIX):] if text.startswith(_HANDLE_PREFIX) else ""
    if not ident or not set(ident) <= _HEX:
        return None
    return out_dir / domain / "qa_process" / _STATE_DIR / f"{text}.json"


def _load_state(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _patch_state(path: Path, **fields: Any) -> None:
    """進捗ファイルを書き換える。ここを通した変更だけが外から見える。"""
    data = _load_state(path) or {}
    data.update(fields)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        logger.warning("テスト実行の記録を保存できませんでした（%s）", path, exc_info=True)


def _read_report(report_path: Path) -> tuple[dict[str, Any] | None, str]:
    """保存された結果を読む。読めなければ (None, 人が読む理由)。

    「読めなかった」を 0 件として返してはいけない。0 件は「全部通った」と
    同じ形になり、結果が壊れている事実が消える。
    """
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # JSONDecodeError は ValueError の一種
        return None, _UNREADABLE.format(path=report_path)
    if not isinstance(data, dict) or not isinstance(data.get("tests"), list):
        return None, _UNREADABLE.format(path=report_path)
    return data, ""


def _mtime_ns(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return -1


def _report_data(result: Any, report_path: Path,
                 before_ns: int) -> tuple[dict[str, Any] | None, str]:
    """実行の戻り値を優先し、壊れていたら保存された JSON を読み直す。

    結果ファイルは毎回同じ場所へ上書きされる。更新されていないものを読むと、
    前の実行の成否を今回の成否として報告することになる（実測で、中止した
    実行が前回の「1 件中 1 件失敗」を自分の結果として拾った）。
    """
    if isinstance(result, dict) and isinstance(result.get("tests"), list):
        return result, ""
    if _mtime_ns(report_path) == before_ns:
        return None, _STALE
    return _read_report(report_path)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _judge(data: dict[str, Any]) -> tuple[str, str, str]:
    """読めた結果から (状態, 人が読む 1 文, エラー) を決める。"""
    error = str(data.get("error") or "")
    tests = data.get("tests") or []
    total = _int(data.get("total")) or len(tests)
    failed = _int(data.get("failed"))
    if total == 0:
        # 0 件を succeeded にすると「テストが 1 件も無い」と「全部通った」が
        # 同じ報告になる。前者はテストが壊れている合図なので失敗にする。
        if error:
            return "failed", "実行結果を読み取れませんでした", error
        return "failed", _NO_TESTS, _NO_TESTS
    return "succeeded", f"{total} 件中 {failed} 件失敗", error


def _alive(pid: int) -> bool:
    """そのプロセスがまだ居るか。権限が無い＝居る（他人のもの）。"""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def _descendants(pid: int) -> list[int]:
    """pid とその子孫。playwright は node の下にワーカーとブラウザを持つ。

    Popen は start_new_session を使っていない（playwright_executor 側）ので
    プロセスグループごとの kill は自分自身を巻き込む。pgrep で辿る。
    """
    found = [pid]
    frontier = [pid]
    while frontier:
        children: list[int] = []
        for parent in frontier:
            try:
                out = subprocess.run(["pgrep", "-P", str(parent)], capture_output=True,
                                     text=True, timeout=5).stdout
            except (OSError, subprocess.SubprocessError):
                continue
            children += [int(t) for t in out.split() if t.isdigit() and int(t) not in found]
        found += children
        frontier = children
    return found


def _kill_tree(pid: int) -> None:
    """子孫ごと止める。SIGTERM → 3 秒 → SIGKILL。"""
    if pid <= 0:
        return
    targets = _descendants(pid)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        alive = [p for p in targets if _alive(p)]
        if not alive:
            return
        for target in alive:
            try:
                os.kill(target, sig)
            except OSError:
                pass
        if sig is signal.SIGTERM:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and any(_alive(p) for p in targets):
                time.sleep(0.2)


@dataclass
class _Live:
    """このプロセスが進めている実行。status() の孤児判定にも使う。"""

    path: Path
    proc: Any = None
    cancelled: bool = False


_LIVE: dict[str, _Live] = {}
_LIVE_LOCK = threading.Lock()
_SHUTDOWN = threading.Event()


def _attach(handle: str, path: Path, proc: Any) -> None:
    """起動した子プロセスを記録する。中止と孤児検知はこの pid が頼り。"""
    pid = _int(getattr(proc, "pid", 0))
    with _LIVE_LOCK:
        live = _LIVE.get(handle)
        if live is not None:
            live.proc = proc
        cancelled = bool(live is not None and live.cancelled)
    _patch_state(path, pid=pid)
    if cancelled:  # 起動前に中止された。起動した瞬間に止める
        _kill_tree(pid)


def _finish(handle: str, path: Path, **fields: Any) -> bool:
    """終わりを書く。中止済み・プロセス終了中なら書かない（上書きしない）。"""
    if _SHUTDOWN.is_set():
        return False
    with _LIVE_LOCK:
        live = _LIVE.get(handle)
        if live is not None and live.cancelled:
            return False
    _patch_state(path, finished_at=_now(), **fields)
    return True


def _execute(handle: str, path: Path, ctx: Context, spec: Path, output_dir: Path,
             timeout_sec: int) -> None:
    """Playwright を回して結果を書く。どの経路で抜けても状態を必ず書く。"""
    from web.services.egress_gateway import EgressPolicy
    from web.services.playwright_executor import run_playwright
    try:
        from crawler.url_safety import _local_targets_allowed
    except ImportError:  # noqa: BLE001 - src が sys.path に無い経路への保険
        def _local_targets_allowed() -> bool:
            return False

    report_path = output_dir / "playwright_report.json"
    before_ns = _mtime_ns(report_path)
    try:
        # 02/03 と同じ通信ポリシー。無いとローカルの対象へ一切つながらず
        # 全テストが net::ERR_FAILED になる（2026-09-07 実測 257/257）
        policy = EgressPolicy(allow_local=_local_targets_allowed())
        result = run_playwright(spec_path=spec, output_dir=output_dir,
                                timeout_sec=timeout_sec,
                                egress_policy=policy,
                                on_proc=lambda proc: _attach(handle, path, proc))
    except Exception as exc:  # noqa: BLE001 - 例外は握らず結果として書く
        _finish(handle, path, state="failed", summary="テストを実行できませんでした",
                error=f"テストの実行に失敗しました: {exc}", artifacts={})
    else:
        artifacts = {"report": _report_relpath(ctx.domain)} if report_path.is_file() else {}
        data, read_error = _report_data(result, report_path, before_ns)
        if data is None:
            _finish(handle, path, state="failed", summary="テスト結果を読めませんでした",
                    error=read_error, artifacts=artifacts)
        else:
            state, summary, error = _judge(data)
            # 書けたときだけ報告する。中止された実行の結果を「終わりました」と
            # 言うと、止めた人には止まっていないように見える。
            if _finish(handle, path, state=state, summary=summary, error=error,
                       artifacts=artifacts):
                try:
                    ctx.log(summary)
                except Exception:  # noqa: BLE001 - ログの失敗で結果を失わない
                    logger.warning("テスト実行の報告に失敗しました", exc_info=True)
    finally:
        with _LIVE_LOCK:
            _LIVE.pop(handle, None)


def _shutdown() -> None:
    """プロセス終了時に、走っている Playwright を残さない。

    進捗ファイルは running のまま残す。次に status() を読んだ人が
    「プロセスが止まった」と正しく知れるのは、この記録が残っているから。
    """
    _SHUTDOWN.set()
    with _LIVE_LOCK:
        procs = [live.proc for live in _LIVE.values() if live.proc is not None]
        _LIVE.clear()
    for proc in procs:
        _kill_tree(_int(getattr(proc, "pid", 0)))


atexit.register(_shutdown)


def _stopped(handle: str, data: dict[str, Any]) -> bool:
    """running と書いてあるのに、進める者が居なくなっていないか。"""
    owner = _int(data.get("owner_pid"))
    if owner == os.getpid():
        with _LIVE_LOCK:
            return handle not in _LIVE  # 自分のスレッドが結果を書かずに消えた
    if owner > 0 and not _alive(owner):
        return True
    pid = _int(data.get("pid"))
    return pid > 0 and not _alive(pid)


class RunAgent:
    """03: 作ってあるテストを 1 回まわす（非同期）。"""

    name = "run"
    label = "テスト実行"

    def ready(self, ctx: Context) -> Readiness:
        spec = _spec_path(ctx.out_dir, ctx.domain)
        if spec is None:
            return Readiness(
                ok=False,
                human_action=_NO_SPEC,
                detail=f"{ctx.domain} に回せるテストがありません",
            )
        return Readiness(ok=True, detail=f"テスト: {spec.name}")

    def run(self, ctx: Context) -> StepResult:
        spec = _spec_path(ctx.out_dir, ctx.domain)
        if spec is None:
            return StepResult(
                status="waiting_human", summary="回せるテストがありません",
                human_action=_NO_SPEC,
            )
        # 実行結果は 03 と同じ場所へ置く。画面の「実行結果」からも同じものが見える。
        output_dir = ctx.out_dir / ctx.domain / "qa_process"
        output_dir.mkdir(parents=True, exist_ok=True)
        handle = f"{_HANDLE_PREFIX}{uuid.uuid4().hex[:12]}"
        path = _state_path(ctx.out_dir, ctx.domain, handle)
        if path is None:  # 起こりえないが、書けない場所へ書きに行かない
            return StepResult(status="failed", summary="実行の記録を作れませんでした",
                              error=_NO_HANDLE)
        _patch_state(path, state="running", started_at=_now(), finished_at="",
                     pid=0, owner_pid=os.getpid(), summary=_RUNNING,
                     artifacts={}, error="")
        with _LIVE_LOCK:
            _LIVE[handle] = _Live(path=path)
        ctx.log(f"テストを実行します（{spec.name}）")
        timeout_sec = _int(ctx.params.get("step_timeout_sec")) or _DEFAULT_TIMEOUT_SEC
        threading.Thread(
            target=_execute, args=(handle, path, ctx, spec, output_dir, timeout_sec),
            name=f"run-{handle}", daemon=True,
        ).start()
        return StepResult(status="running", summary=_RUNNING, handle=handle)

    def status(self, ctx: Context, handle: str) -> StepStatus:
        path = _state_path(ctx.out_dir, ctx.domain, handle)
        data = _load_state(path) if path is not None else None
        if path is None or not data:
            return StepStatus(state="failed", label="実行の記録なし",
                              summary=_NO_HANDLE, error=_NO_HANDLE)
        state = str(data.get("state") or "")
        summary = str(data.get("summary") or "")
        error = str(data.get("error") or "")
        artifacts = {str(k): str(v) for k, v in dict(data.get("artifacts") or {}).items()}
        if state == "running":
            if _stopped(handle, data):
                _patch_state(path, state="failed", summary=_PROC_GONE,
                             error=_PROC_GONE, finished_at=_now())
                return StepStatus(state="failed", label="実行が止まりました",
                                  summary=_PROC_GONE, error=_PROC_GONE)
            progress = _progress_summary(ctx.out_dir, ctx.domain)
            return StepStatus(state="running", label="テスト実行中", summary=progress or summary)
        if state == "cancelled":
            return StepStatus(state="cancelled", label="テスト実行 中止", summary=summary)
        if state == "succeeded":
            return StepStatus(state="succeeded", label="テスト実行 完了",
                              summary=summary, artifacts=artifacts, error=error)
        return StepStatus(state="failed", label="テスト実行 失敗",
                          summary=summary or _NO_HANDLE,
                          artifacts=artifacts, error=error or summary or _NO_HANDLE)

    def cancel(self, ctx: Context, handle: str) -> bool:
        """走っている Playwright を子孫ごと止める。

        指揮の記録だけを cancelled にして子プロセスを放置すると、node が
        孤児として残り CPU を食い続ける（実測で確認）。止めてから記録する。
        """
        path = _state_path(ctx.out_dir, ctx.domain, handle)
        if path is None:
            return False
        key = str(handle).strip()
        with _LIVE_LOCK:
            live = _LIVE.get(key)
            if live is not None:
                live.cancelled = True
            pid = _int(getattr(getattr(live, "proc", None), "pid", 0))
        data = _load_state(path)
        if data is None and live is None:
            return False
        _kill_tree(pid or _int((data or {}).get("pid")))
        _patch_state(path, state="cancelled", summary=_CANCELLED, finished_at=_now())
        return True
