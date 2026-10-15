"""System 08 段階 7。生成した pytest をサブプロセスで実行し、止め、部分結果と証跡を残す。

方式は BD-008 6 章。これは製品機能としての実行であり、開発用のテストゲートではない。
- 親の環境変数を引き継がず、PATH・LANG・TZ・HOME・PYTHONPATH と WS2D_BT_* だけを渡す
- パスワードは子プロセスの環境変数にだけ載せる。ログ・証跡・戻り値には出さない（ログは scrub 済み）
- 停止は killpg(SIGTERM) → GRACE_SEC 秒後 SIGKILL。完了済みケースは results.jsonl に残る
- 同時実行はテナントあたり 1 本（メモリ内のレジストリ＋<テナント>/backendtest/.running）
"""
from __future__ import annotations

import functools
import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import dbconn, evidence, redact, store

DEFAULT_TIMEOUT_SEC = 60 * 60
MAX_TIMEOUT_SEC = 24 * 60 * 60
GRACE_SEC = 5
POLL_SEC = 0.2
RLIMIT_FSIZE_BYTES = 200 * 1024 * 1024
RLIMIT_AS_BYTES = 2 * 1024 ** 3
RUNNING_FILE = ".running"
ACTIVE = ("queued", "running")
_DONE_RC = (0, 1)  # 0=全合格 1=不合格あり。5（該当テスト 0 件）と結果 0 件は完走に数えない
_ENV_KEEP = ("PATH", "LANG", "TZ")
_CASE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_READ_CHUNK = 64 * 1024
_log = logging.getLogger(__name__)

_LOCK = threading.Lock()
_RUNS: dict[str, "_Run"] = {}
_ACTIVE_BY_TENANT: dict[str, str] = {}


class _Run:
    """実行 1 本の内部状態。外へは _summary() の新しい dict だけを返す。"""

    def __init__(self, run_id: str, jid: str, workdir: Path, case_ids: list[str],
                 business_date: str, env_name: str, timeout_sec: int):
        self.run_id, self.jid, self.workdir = run_id, jid, workdir
        self.dir = workdir / "evidence" / run_id
        self.tenant_root = workdir.parent
        self.tenant_key = str(self.tenant_root.resolve())
        self.case_ids, self.business_date, self.env_name = case_ids, business_date, env_name
        self.timeout_sec = timeout_sec
        self.status, self.reason, self.rc = "queued", "", None
        self.started_at, self.ended_at = store.now(), ""
        self.t0, self.elapsed = time.monotonic(), None
        self.cancel_event, self.stop_cause, self.limited, self.written = threading.Event(), "", False, 0
        self.secrets: list[str] = []
        self.proc: subprocess.Popen | None = None
        self.thread: threading.Thread | None = None
        self.io_lock = threading.Lock()


# ---- 公開関数 -------------------------------------------------------------

def start(jid: str, env: dict, secrets=None, timeout_sec: int = DEFAULT_TIMEOUT_SEC, *,
          case_ids: list[str] | None = None, business_date: str = "",
          workdir: Path | None = None) -> str:
    """案件の code/ に対して pytest を起動し run_id を返す。

    secrets: {"password": ...} の dict（文字列・文字列のリストも可）。メモリ内だけで扱う。
    workdir: 案件フォルダ。省略時は store.job_dir(jid)（検証用に一時フォルダを渡せる）。
    """
    root = (Path(workdir) if workdir else store.job_dir(jid)).resolve()  # 子は cwd が変わるので絶対パスで渡す
    if not (root / "code").is_dir():
        raise store.StoreError("テストコードがまだありません。段階 6 でテストコードを生成してから実行してください。")
    timeout, cases = _check_timeout(timeout_sec), _check_cases(case_ids)
    with _LOCK:
        run = _reserve(root, jid, cases, business_date, str((env or {}).get("name") or ""), timeout)
    run.secrets = _secret_values(secrets)
    try:
        run.proc = _spawn(run, env or {}, _password(secrets))
    except (OSError, ValueError) as exc:
        _log.error("テスト実行の起動に失敗: %s", redact.scrub(str(exc), run.secrets))
        _finish(run, "error", "テストの実行を開始できませんでした。設定を確認してから再実行してください。", None)
        raise store.StoreError("テストの実行を開始できませんでした。設定を確認してから再実行してください。") from None
    run.status = "running"
    evidence.write_run(run.dir, _public(run))
    pumps = [threading.Thread(target=_pump, args=(run, run.proc.stdout, "stdout"), daemon=True),
             threading.Thread(target=_pump, args=(run, run.proc.stderr, "stderr"), daemon=True)]
    for t in pumps:
        t.start()
    run.thread = threading.Thread(target=_watch, args=(run, pumps), daemon=True)
    run.thread.start()
    return run.run_id


def status(run_id: str, jid: str | None = None) -> dict:
    """実行の要約。メモリに無ければ（再起動後など）jid から run.json を読む。無ければ KeyError。"""
    run = _RUNS.get(run_id)
    if run is not None:
        return _summary(run)
    if jid:
        directory = evidence.run_dir(jid, run_id)
        data = evidence.read_run(directory)
        if data is not None:
            return {**data, "results": evidence.read_results(directory)}
    raise KeyError(run_id)


def cancel(run_id: str, actor: str = "") -> dict:
    """実行を止める。SIGTERM → 猶予 → SIGKILL。完了済みケースの結果は残す。"""
    run = _RUNS.get(run_id)
    if run is None:
        raise KeyError(run_id)
    if run.status in ACTIVE:
        _log.info("実行 %s の停止を受け付けました（%s）", run_id, actor or "不明")
        run.cancel_event.set()
        if run.thread is not None:
            run.thread.join(timeout=GRACE_SEC + 3)
    return _summary(run)


def recover_stale(tenant_root: Path | None = None) -> str | None:
    """製品の再起動で残った .running を片付け、その実行を error として確定する。"""
    tenant_root = Path(tenant_root) if tenant_root else store.job_dir("0" * 12).parent
    marker = tenant_root / RUNNING_FILE
    try:
        info = json.loads(marker.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        info = {}
    run_id, jid = str(info.get("run_id") or ""), str(info.get("jid") or "")
    directory = tenant_root / jid / "evidence" / run_id if run_id and jid else None
    data = evidence.read_run(directory) if directory and directory.is_dir() else None
    if data and data.get("status") in ACTIVE:
        evidence.write_run(directory, {
            **data, "status": "error", "ended_at": store.now(),
            "reason": "製品の再起動で実行が中断されました。完了済みのケースの結果は残っています。未実行のケースを再実行してください。"})
    marker.unlink(missing_ok=True)
    return run_id or None


# ---- 受付・排他 -----------------------------------------------------------

def _check_timeout(value) -> int:
    try:
        sec = int(value)
    except (TypeError, ValueError):
        raise store.StoreError("制限時間が数字ではありません。秒数を数字で指定してください。") from None
    if not 0 < sec <= MAX_TIMEOUT_SEC:
        raise store.StoreError("制限時間が範囲外です。1 秒から 24 時間の間で指定してください。")
    return sec


def _check_cases(case_ids) -> list[str]:
    cases = [str(c) for c in (case_ids or [])]
    bad = [c for c in cases if not _CASE.match(c)]
    if bad:
        raise store.StoreError("ケース番号の形式が正しくありません。英数字・ハイフン・下線で指定してください。")
    return cases


def _reserve(root: Path, jid: str, cases: list[str], business_date: str,
             env_name: str, timeout: int) -> _Run:
    """_LOCK を持った状態で呼ぶ。テナントで実行中なら StoreError。"""
    key = str(root.parent.resolve())
    current = _RUNS.get(_ACTIVE_BY_TENANT.get(key, ""))
    if current is not None and current.status in ACTIVE:
        raise store.StoreError("この組織では別のテスト実行が進行中です。終わるのを待つか、止めてから実行してください。")
    if current is None and (root.parent / RUNNING_FILE).exists():
        recover_stale(root.parent)
    run = _Run(evidence.new_run_id(root / "evidence"), jid, root, cases,
               str(business_date or ""), env_name, timeout)
    run.dir.mkdir(parents=True, exist_ok=False)
    _RUNS[run.run_id] = run
    _ACTIVE_BY_TENANT[key] = run.run_id
    marker = {"jid": jid, "run_id": run.run_id, "started_at": run.started_at}
    (run.tenant_root / RUNNING_FILE).write_text(json.dumps(marker), encoding="utf-8")
    evidence.write_run(run.dir, _public(run))
    return run


def _release(run: _Run) -> None:
    """_LOCK を持った状態で呼ぶ。"""
    if _ACTIVE_BY_TENANT.get(run.tenant_key) == run.run_id:
        del _ACTIVE_BY_TENANT[run.tenant_key]
    marker = run.tenant_root / RUNNING_FILE
    try:
        if json.loads(marker.read_text(encoding="utf-8")).get("run_id") == run.run_id:
            marker.unlink()
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        _log.warning("実行中の印を片付けられません: %s", exc)


# ---- 起動 -----------------------------------------------------------------

def _secret_values(secrets) -> list[str]:
    if isinstance(secrets, str):
        return [secrets] if secrets else []
    if isinstance(secrets, dict):
        return [str(v) for v in secrets.values() if v]
    return [str(v) for v in (secrets or []) if v]


def _password(secrets) -> str:
    if isinstance(secrets, dict):
        return str(secrets.get("password") or "")
    values = _secret_values(secrets)
    return values[0] if values else ""


def _child_env(run: _Run, env: dict, password: str) -> dict:
    base = {k: os.environ[k] for k in _ENV_KEEP if os.environ.get(k)}
    home = run.workdir / "work"
    home.mkdir(exist_ok=True)
    db = env.get("db") or {}
    child = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", **base,
             "HOME": str(home), "PYTHONPATH": str(run.workdir / "code"),
             "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8",
             "WS2D_BT_RUN_ID": run.run_id, "WS2D_BT_EVIDENCE_DIR": str(run.dir),
             "WS2D_BT_BUSINESS_DATE": run.business_date, "WS2D_BT_ENV_NAME": run.env_name,
             "WS2D_BT_PRODUCTION": "1" if env.get("production") else "0",
             "WS2D_BT_READ_ONLY": "1" if dbconn.must_read_only(env) else "0",
             "WS2D_BT_DB_HOST": str(db.get("host") or ""), "WS2D_BT_DB_PORT": str(db.get("port") or 5432),
             "WS2D_BT_DB_NAME": str(db.get("dbname") or ""), "WS2D_BT_DB_USER": str(db.get("user") or ""),
             "WS2D_BT_DB_SSLMODE": str(db.get("sslmode") or "prefer")}
    if password:
        child["WS2D_BT_DB_PASSWORD"] = password
    return child


def _case_selector(case_id: str) -> str:
    cid = re.sub(r"\W+", "_", str(case_id), flags=re.ASCII).strip("_").lower() or "case"
    return f"test_{cid}_"


def _command(run: _Run) -> list[str]:
    code = run.workdir / "code"
    junit = (run.dir / evidence.JUNIT_FILE).relative_to(run.workdir).as_posix()
    cmd = [sys.executable, "-m", "pytest", "code/tests" if (code / "tests").is_dir() else "code",
           "-q", "-p", "no:cacheprovider", f"--junitxml={junit}"]
    if (code / "bt_runtime.py").is_file():
        cmd += ["-p", "bt_runtime"]
    if run.case_ids:
        # 生成テスト名は test_<id 小文字>_<slug>（codegen._test_names）。ID の直後の "_" まで含めて完全一致させる
        cmd += ["-k", " or ".join(_case_selector(c) for c in run.case_ids)]
    return cmd


def _limits(cpu_sec: int) -> None:
    """子プロセス側で資源上限を掛ける（preexec_fn）。掛けられない OS では素通りする。"""
    import resource
    caps = [(resource.RLIMIT_FSIZE, RLIMIT_FSIZE_BYTES), (resource.RLIMIT_CPU, cpu_sec)]
    if sys.platform.startswith("linux"):  # macOS は RLIMIT_AS を実質扱えない
        caps.append((resource.RLIMIT_AS, RLIMIT_AS_BYTES))
    for kind, value in caps:
        try:
            resource.setrlimit(kind, (value, value))
        except (ValueError, OSError):
            pass  # 子プロセス内ではログを出せない。上限なしで続行し、全体の deadline で止める


def _spawn(run: _Run, env: dict, password: str) -> subprocess.Popen:
    child_env = _child_env(run, env, password)
    try:
        return subprocess.Popen(
            _command(run), cwd=str(run.workdir), env=child_env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, close_fds=True,
            preexec_fn=functools.partial(_limits, run.timeout_sec + GRACE_SEC) if os.name == "posix" else None)
    finally:
        child_env.clear()


# ---- 監視・停止 -----------------------------------------------------------

def _pump(run: _Run, pipe, name: str) -> None:
    """子の出力を scrub して <name>.log へ書く。合計が上限を超えたら以降は捨てて停止を促す。"""
    with (run.dir / f"{name}.log").open("w", encoding="utf-8") as out:
        for raw in iter(lambda: pipe.readline(_READ_CHUNK), b""):
            with run.io_lock:
                run.written += len(raw)
                over = run.written > evidence.OUTPUT_LIMIT_BYTES
                if over and not run.limited:
                    run.limited = True
                    evidence.record_output_limit(run.dir, name, run.written)
            if over:
                continue
            out.write(redact.scrub(raw.decode("utf-8", "replace"), run.secrets))
            out.flush()
    pipe.close()


def _stop_cause(run: _Run) -> str:
    if run.cancel_event.is_set():
        return "cancelled"
    if time.monotonic() > run.t0 + run.timeout_sec:
        return "timeout"
    return "output_limit" if run.limited else ""


def _killpg(pid: int, sig: int) -> bool:
    try:
        os.killpg(pid, sig)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _terminate(proc: subprocess.Popen) -> None:
    if not _killpg(proc.pid, signal.SIGTERM):
        return
    try:
        proc.wait(timeout=GRACE_SEC)
    except subprocess.TimeoutExpired:
        _killpg(proc.pid, signal.SIGKILL)
        proc.wait()


def _watch(run: _Run, pumps: list[threading.Thread]) -> None:
    proc = run.proc
    while proc.poll() is None:
        cause = _stop_cause(run)
        if cause:
            run.stop_cause = cause
            _terminate(proc)
            break
        time.sleep(POLL_SEC)
    rc = proc.wait()
    _killpg(proc.pid, signal.SIGKILL)  # 取り残された孫プロセスを片付ける
    for t in pumps:
        t.join(timeout=GRACE_SEC)
    _finish(run, *_final_state(run, rc))


def _final_state(run: _Run, rc: int) -> tuple[str, str, int]:
    stops = {
        "cancelled": ("cancelled", "実行を止めました。完了済みのケースの結果は残っています。未実行のケースは再実行できます。"),
        "timeout": ("timeout", f"制限時間 {run.timeout_sec} 秒を超えたため止めました。未実行のケースを再実行するか、制限時間を延ばしてください。"),
        "output_limit": ("error", "出力が上限を超えたため止めました。テストコードの出力を減らしてから再実行してください。"),
    }
    if run.stop_cause in stops:
        return (*stops[run.stop_cause], rc)
    if rc in _DONE_RC and evidence.read_results(run.dir):
        return "done", "", rc
    if rc in (*_DONE_RC, 5):
        return "error", f"テストが 1 件も実行されませんでした（終了コード {rc}）。選んだケースとエラーログを確認してから再実行してください。", rc
    return "error", f"テストの実行が異常終了しました（終了コード {rc}）。エラーログを確認してから再実行してください。", rc


def _scrub_file(path: Path, secrets: list[str]) -> None:
    """子が直接書いた証跡（junit xml 等）から入力された秘密を伏せる。"""
    if not secrets or not path.is_file():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    cleaned = redact.scrub(text, secrets)
    if cleaned != text:
        path.write_text(cleaned, encoding="utf-8")


def _finish(run: _Run, state: str, reason: str, rc: int | None) -> None:
    try:
        _scrub_file(run.dir / evidence.JUNIT_FILE, run.secrets)
    except OSError as exc:
        _log.error("junit xml の伏せ字に失敗: run=%s (%s)", run.run_id, exc)
    with _LOCK:
        run.status, run.reason, run.rc = state, reason, rc
        run.ended_at, run.elapsed = store.now(), round(time.monotonic() - run.t0, 1)
        run.secrets = []
        _release(run)
    try:
        evidence.write_run(run.dir, _public(run))
        evidence.manifest(run.dir, {"run_id": run.run_id, "env_name": run.env_name,
                                    "business_date": run.business_date})
    except OSError as exc:
        _log.error("証跡の確定に失敗: run=%s (%s)", run.run_id, exc)


# ---- 要約 -----------------------------------------------------------------

def _public(run: _Run) -> dict:
    """run.json と画面に出す要約（BD-008 3.2 runs の形＋停止理由）。結果の本文は含めない。"""
    results = evidence.read_results(run.dir)
    done = {str(r.get("case")) for r in results if r.get("case")}
    elapsed = run.elapsed if run.elapsed is not None else round(time.monotonic() - run.t0, 1)
    return {"id": run.run_id, "jid": run.jid, "env_name": run.env_name,
            "business_date": run.business_date, "case_ids": list(run.case_ids),
            "status": run.status, "reason": run.reason, "rc": run.rc,
            "started_at": run.started_at, "ended_at": run.ended_at, "elapsed_sec": elapsed,
            "progress": {"done": len(results), "total": len(run.case_ids) or None, "current": None},
            "not_run": [c for c in run.case_ids if c not in done],
            "output_limited": run.limited}


def _summary(run: _Run) -> dict:
    return {**_public(run), "results": evidence.read_results(run.dir)}
