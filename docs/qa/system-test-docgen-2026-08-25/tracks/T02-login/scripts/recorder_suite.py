"""T02 レコーダー試験（決定的・headless）。record_auth_session / _run_recorder_loop を
実オブジェクト・フェイク注入・環境操作で駆動し failure_mode を再現する。
実行: venv/bin/python scripts/recorder_suite.py  （CWD=repo ルート）"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path.cwd() / "src"))
from lib import DOMAIN, LOGIN_URL, save_evidence  # noqa: E402

R = []
def rec(cid, result, observed, evid=""):
    R.append({"id": cid, "result": result, "observed": observed, "evidence": evid})

SCRATCH = Path("/private/tmp/claude-501/-Users-fujimagariyuki-dev-active-webspec2doc/16aa1a8f-26d7-42ea-88a6-4301b87af6ee/scratchpad/t02rec")
SCRATCH.mkdir(parents=True, exist_ok=True)


def r_timeout():
    """recorder_timeout: headless 起動・signal 無し・timeout 2s -> PHASE_TIMEOUT"""
    from crawler.auth_recorder import record_auth_session, PHASE_TIMEOUT
    auth = SCRATCH / "to_auth.json"; sig = SCRATCH / "to_sig"; stat = SCRATCH / "to_status.json"
    for p in (auth, sig, stat):
        p.unlink(missing_ok=True)
    t0 = time.time()
    status = record_auth_session(LOGIN_URL, auth, sig, status_file=stat, timeout=2.0,
                                 headless=True, poll_interval=0.2)
    dur = round(time.time() - t0, 1)
    sf = stat.read_text() if stat.exists() else "(missing)"
    save_evidence("R_timeout.json", {"phase": status.phase, "duration_s": dur,
                                     "status_file": sf, "auth_saved": auth.exists()})
    rec("T02-C032", "PASS" if status.phase == PHASE_TIMEOUT and not auth.exists() else "FAIL",
        f"phase={status.phase} dur={dur}s auth_saved={auth.exists()}", "evidence/R_timeout.json")


def r_saved_via_cli():
    """status transitions + .login_status.json content: 実 CLI サブプロセス（headless）で
    signal を置いて PHASE_SAVED を得る。"""
    auth = SCRATCH / "sv_auth.json"; sig = SCRATCH / "sv_sig"; stat = SCRATCH / "sv_status.json"
    for p in (auth, sig, stat):
        p.unlink(missing_ok=True)
    env = dict(os.environ, WEBSPEC2DOC_RECORD_HEADLESS="1")
    cmd = [sys.executable, "src/main.py", "--login-record", "--login-record-url", LOGIN_URL,
           "--auth", str(auth), "--login-signal", str(sig), "--login-status", str(stat)]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    phases = []
    # poll status file up to 8s, then drop signal
    for i in range(40):
        if stat.exists():
            try:
                phases.append(json.loads(stat.read_text()).get("phase"))
            except Exception:  # noqa: BLE001
                pass
        if i == 12:  # ~2.4s in, request save
            sig.touch()
        if not proc.poll() is None:
            break
        time.sleep(0.2)
    proc.wait(timeout=20)
    final = json.loads(stat.read_text()) if stat.exists() else {}
    save_evidence("R_saved.json", {"phases_seen": phases, "final_status": final,
                                   "auth_saved": auth.exists(),
                                   "exit_code": proc.returncode})
    ok = final.get("phase") == "saved" and auth.exists() and "waiting" in phases
    rec("T02-C033", "PASS" if ok else "FAIL",
        f"phases={sorted(set(p for p in phases if p))} final={final.get('phase')} auth_saved={auth.exists()} verified={final.get('verified')}",
        "evidence/R_saved.json")


def r_closed():
    """browser_closed: page.evaluate が例外 -> PHASE_CLOSED（フェイク注入・モジュール想定の使い方）"""
    from crawler.auth_recorder import _run_recorder_loop, PHASE_CLOSED

    class FakePage:
        url = LOGIN_URL
        def evaluate(self, *_):
            raise RuntimeError("Target page, context or browser has been closed")

    class FakeCtx:
        def storage_state(self, **_):
            pass

    auth = SCRATCH / "cl_auth.json"; sig = SCRATCH / "cl_sig"; stat = SCRATCH / "cl_status.json"
    for p in (auth, sig, stat):
        p.unlink(missing_ok=True)
    status = _run_recorder_loop(page=FakePage(), context=FakeCtx(), login_url=LOGIN_URL,
                                auth_path=auth, signal_file=sig, status_file=stat,
                                timeout=5.0, poll_interval=0.1)
    save_evidence("R_closed.json", {"phase": status.phase, "detail": status.detail,
                                    "auth_saved": auth.exists()})
    rec("T02-C034", "PASS" if status.phase == PHASE_CLOSED and not auth.exists() else "FAIL",
        f"phase={status.phase} auth_saved={auth.exists()}", "evidence/R_closed.json")


def r_display_missing():
    """display_missing: ブラウザ起動失敗を PLAYWRIGHT_BROWSERS_PATH=不正 で誘発し PHASE_ERROR を確認。
    実運用では /api/login/record/start が headless 環境で同経路に入る（route は headless env を渡さない）。"""
    from crawler.auth_recorder import record_auth_session, PHASE_ERROR
    auth = SCRATCH / "dm_auth.json"; sig = SCRATCH / "dm_sig"; stat = SCRATCH / "dm_status.json"
    for p in (auth, sig, stat):
        p.unlink(missing_ok=True)
    old = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/nonexistent-browsers-xyz"
    try:
        status = record_auth_session(LOGIN_URL, auth, sig, status_file=stat, timeout=3.0,
                                     headless=False, poll_interval=0.2)
    finally:
        if old is None:
            os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
        else:
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = old
    sf = json.loads(stat.read_text()) if stat.exists() else {}
    save_evidence("R_display_missing.json", {"phase": status.phase, "detail": status.detail,
                                             "status_file": sf})
    ok = status.phase == PHASE_ERROR and not auth.exists()
    rec("T02-C035", "PASS" if ok else "FAIL",
        f"phase={status.phase} detail={status.detail[:50]} auth_saved={auth.exists()}",
        "evidence/R_display_missing.json")


def main():
    r_timeout()
    r_saved_via_cli()
    r_closed()
    r_display_missing()
    save_evidence("_recorder_results.json", R)
    for x in R:
        print(f"{x['id']}\t{x['result']}\t{x['observed']}")


if __name__ == "__main__":
    main()
