"""recorder_timeout / browser_closed / session_expired をコア関数の直接呼び出しで実証する。
GUI ブラウザを開かず（フェイク page/context を注入）、evidence-only で phase 遷移を観測する。
実行: リポジトリ直下で venv/bin/python (PYTHONPATH=src) このファイル。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "src")

from crawler.auth_recorder import (  # noqa: E402
    PHASE_CLOSED,
    PHASE_TIMEOUT,
    _run_recorder_loop,
)
from crawler.session_guard import is_session_expired  # noqa: E402
from analyzer.login_wall import PageAuthSignals  # noqa: E402

EVID = Path(__file__).resolve().parent.parent / "evidence"
EVID.mkdir(parents=True, exist_ok=True)
OUT = []


class FakePageNeverLogin:
    """ログインしないページ（パスワード欄が残り続ける＝タイムアウト誘発）。"""

    url = "http://127.0.0.1:9102/login"

    def evaluate(self, _js):
        return True  # password field 常在


class FakePageClosed:
    """ブラウザ/ページが閉じられた状態（url/evaluate が例外）。"""

    @property
    def url(self):
        raise RuntimeError("Target page, context or browser has been closed")

    def evaluate(self, _js):
        raise RuntimeError("Target page, context or browser has been closed")


class FakeCtx:
    def storage_state(self, path=None):
        return {}


def run_timeout():
    """recorder_timeout: deadline を即超過させ PHASE_TIMEOUT を得る。"""
    sig = Path("/nonexistent/never_created.signal")
    status_path = EVID / "d07_timeout_status.json"
    # clock を 2 回目で deadline 超過させる（timeout=0.0）
    calls = {"n": 0}

    def clock():
        calls["n"] += 1
        return 0.0 if calls["n"] == 1 else 100.0

    status = _run_recorder_loop(
        page=FakePageNeverLogin(), context=FakeCtx(),
        login_url="http://127.0.0.1:9102/login", auth_path=EVID / "_unused_auth.json",
        signal_file=sig, status_file=status_path, timeout=0.0, poll_interval=0.0,
        clock=clock, sleeper=lambda _s: None,
    )
    OUT.append({"case": "D07_recorder_timeout", "phase": status.phase,
                "expected": PHASE_TIMEOUT, "pass": status.phase == PHASE_TIMEOUT,
                "detail": status.detail, "evidence": "evidence/d07_timeout_status.json"})


def run_closed():
    """browser_closed: page.url/evaluate 例外で PHASE_CLOSED を得る。"""
    sig = Path("/nonexistent/never_created2.signal")
    status_path = EVID / "d08_closed_status.json"
    status = _run_recorder_loop(
        page=FakePageClosed(), context=FakeCtx(),
        login_url="http://127.0.0.1:9102/login", auth_path=EVID / "_unused_auth2.json",
        signal_file=sig, status_file=status_path, timeout=600.0, poll_interval=0.0,
        clock=lambda: 0.0, sleeper=lambda _s: None,
    )
    OUT.append({"case": "D08_browser_closed", "phase": status.phase,
                "expected": PHASE_CLOSED, "pass": status.phase == PHASE_CLOSED,
                "detail": status.detail, "evidence": "evidence/d08_closed_status.json"})


def run_session_expired():
    """session_expired: is_session_expired の判定を実証する。"""
    login_wall = PageAuthSignals(requested_url="http://x/dashboard",
                                 final_url="http://x/login", status=200, has_password_field=True)
    ok_page = PageAuthSignals(requested_url="http://x/dashboard",
                              final_url="http://x/dashboard", status=200, has_password_field=False)
    r_none = is_session_expired(None, login_wall)          # 認証なし → False
    r_expired = is_session_expired(Path("auth.json"), login_wall)  # auth付き+login wall → True
    r_valid = is_session_expired(Path("auth.json"), ok_page)       # auth付き+正常 → False
    res = {"auth_none__loginwall": r_none, "auth_set__loginwall": r_expired,
           "auth_set__ok_page": r_valid}
    (EVID / "d10_session_expired.json").write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                                   encoding="utf-8")
    ok = (r_none is False and r_expired is True and r_valid is False)
    OUT.append({"case": "D10_session_expired", "pass": ok, "observed": res,
                "evidence": "evidence/d10_session_expired.json"})


if __name__ == "__main__":
    run_timeout()
    run_closed()
    run_session_expired()
    for o in OUT:
        print(json.dumps(o, ensure_ascii=False))
