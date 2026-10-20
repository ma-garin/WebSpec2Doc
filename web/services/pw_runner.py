"""Python Playwright（sync API）の薄いテストランナー。子プロセスで動かす。

    python -m web.services.pw_runner --spec X_spec.py --out DIR [--policy JSON|@file]
        [--device pc|mobile] [--headed] [--grep RE] [--per-test-timeout SEC]

入出力契約（executor / 生成器が依存する）:
- spec は `from web.services.pw_spec_api import case` で `@case(label, skip=False)` を使い、
  `def fn(page)` を定義する。runner は関数属性 `__pw_case__ = {"label", "skip"}` を持つ
  callable を定義順に実行する（無ければ `pw_spec_api.CASES` の同形 dict 列を使う）。
- 出力（DIR 配下）: `playwright_progress.ndjson`（begin / test を 1 行ずつ追記）、
  `playwright_raw.json`（Playwright JSON レポータ同形: suites→specs→tests→results、stats。
  加えて status / ok / passed / failed / skipped / total / reason）、`egress_log.ndjson`。
- 終了コード: 0 全件合格 / 1 失敗あり / 2 spec 読込失敗・0 件 / 3 BLOCKED（ブラウザ無し）。
- ブラウザ無し: status="BLOCKED"・reason="browser unavailable"・passed/failed=0・ok=False。
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import signal
import sys
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from browser_detect import (  # noqa: E402
    BLOCKED_STATUS,
    UNAVAILABLE_REASON,
    BrowserUnavailable,
    launch_browser,
)

POLICY_ENV = "WEBSPEC2DOC_EGRESS_POLICY"
PROGRESS_NAME = "playwright_progress.ndjson"
RAW_NAME = "playwright_raw.json"
EGRESS_LOG_NAME = "egress_log.ndjson"
EXIT_OK, EXIT_FAILED, EXIT_ERROR, EXIT_BLOCKED = 0, 1, 2, 3
DEFAULT_TIMEOUT_SEC = 30.0
LOCAL_SUFFIXES = (".local", ".localhost", ".internal")


@dataclass(frozen=True)
class Case:
    label: str
    fn: Callable[..., Any]
    skip: bool = False


# ───────────────────────── egress 判定（JS フィクスチャと同一仕様） ─────────────────────────


class Egress:
    def __init__(self, policy: dict[str, Any], log_path: Path) -> None:
        self.budget = int(policy.get("budgetPerWorker", 10**9))
        self.self_origins = [str(o).lower() for o in policy.get("selfOrigins") or []]
        self.denied_hosts = [str(h).lower() for h in policy.get("deniedHosts") or []]
        self.block_all = bool(policy.get("blockAll"))
        self.allow_local = bool(policy.get("allowLocal"))
        self.log_path = log_path
        self.used = 0

    @staticmethod
    def _is_private(host: str) -> bool:
        if host == "localhost" or host.endswith(LOCAL_SUFFIXES):
            return True
        try:
            addr = ipaddress.ip_address(host.strip("[]"))
        except ValueError:
            return False
        return not addr.is_global

    def deny_reason(self, raw_url: str) -> str | None:
        try:
            u = urlparse(raw_url)
            host = (u.hostname or "").lower()
            origin = f"{u.scheme}://{u.netloc}".lower()
        except ValueError:
            return "invalid_url"
        if self.block_all:
            return "block_all"
        if u.scheme not in ("http", "https"):
            return "scheme"
        if host in self.denied_hosts:
            return "denied_host"
        if self._is_private(host) and not self.allow_local:
            return "private_address"
        if origin in self.self_origins:
            return "self_origin"
        return None

    def record(self, entry: dict[str, Any]) -> None:
        try:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass  # 記録失敗で実行は止めない

    def handler(self, test_title: str) -> Callable[[Any], None]:
        def _handle(route: Any) -> None:
            url = route.request.url
            reason = self.deny_reason(url)
            if reason is None and self.used >= self.budget:
                reason = "budget"
            base = {"t": int(time.time() * 1000), "test": test_title, "url": url}
            if reason:
                self.record({**base, "action": "denied", "reason": reason})
                route.abort()
                return
            self.used += 1
            self.record({**base, "action": "allowed"})
            route.continue_()

        return _handle


def load_policy(raw: str | None) -> dict[str, Any]:
    text = raw if raw is not None else os.environ.get(POLICY_ENV, "")
    if text.startswith("@"):
        text = Path(text[1:]).read_text(encoding="utf-8")
    if not text.strip():
        return {}
    data = json.loads(text)
    return data if isinstance(data, dict) else {}


# ───────────────────────── spec 読込・出力 ─────────────────────────


def load_cases(spec_path: Path) -> list[Case]:
    import importlib.util

    mod_spec = importlib.util.spec_from_file_location(f"_pw_spec_{spec_path.stem}", spec_path)
    if mod_spec is None or mod_spec.loader is None:
        raise ImportError(f"spec を読み込めません: {spec_path}")
    module = importlib.util.module_from_spec(mod_spec)
    api = sys.modules.get("web.services.pw_spec_api")
    if api is not None and hasattr(api, "CASES"):
        api.CASES.clear()
    mod_spec.loader.exec_module(module)

    cases: list[Case] = []
    for obj in vars(module).values():
        meta = getattr(obj, "__pw_case__", None)
        if callable(obj) and isinstance(meta, dict):
            cases.append(Case(str(meta.get("label", obj.__name__)), obj, bool(meta.get("skip"))))
    if not cases:
        api = sys.modules.get("web.services.pw_spec_api")
        for meta in getattr(api, "CASES", []) or []:
            cases.append(Case(str(meta["label"]), meta["fn"], bool(meta.get("skip"))))
    return cases


def _append(path: Path, obj: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def build_raw(spec_name: str, results: list[dict[str, Any]], duration_ms: int, **extra: Any) -> dict[str, Any]:
    specs = []
    for r in results:
        pw_status = {"passed": "expected", "failed": "unexpected", "skipped": "skipped"}[r["status"]]
        specs.append(
            {
                "title": r["title"],
                "ok": r["status"] != "failed",
                "tests": [
                    {
                        "status": pw_status,
                        "results": [
                            {
                                "status": r["status"],
                                "duration": r["duration"],
                                "errors": [{"message": r["error"]}] if r["error"] else [],
                                "steps": (
                                    [{"title": r["failed_step"], "error": {"message": r["error"]}}]
                                    if r["failed_step"]
                                    else []
                                ),
                            }
                        ],
                    }
                ],
            }
        )
    count = lambda s: sum(1 for r in results if r["status"] == s)  # noqa: E731
    passed, failed, skipped = count("passed"), count("failed"), count("skipped")
    raw: dict[str, Any] = {
        "suites": [{"title": spec_name, "file": spec_name, "specs": specs}] if specs else [],
        "stats": {
            "duration": duration_ms,
            "expected": passed,
            "unexpected": failed,
            "skipped": skipped,
            "flaky": 0,
        },
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "total": len(results),
    }
    raw.update(extra)
    return raw


def write_blocked(out: Path, exc: BrowserUnavailable) -> None:
    raw = build_raw("", [], 0, status=BLOCKED_STATUS, reason=UNAVAILABLE_REASON, ok=False)
    raw["detail"] = exc.detail
    raw["tried"] = exc.tried
    (out / RAW_NAME).write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")


# ───────────────────────── 実行 ─────────────────────────


class _TestTimeout(Exception):
    pass


def _run_case(case: Case, browser: Any, egress: Egress, device: str, timeout_sec: float, p: Any):
    options: dict[str, Any] = (
        dict(p.devices["iPhone 13"]) if device == "mobile" else {"viewport": {"width": 1280, "height": 720}}
    )
    options.setdefault("locale", "ja-JP")
    context = browser.new_context(**options)
    use_alarm = hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer")
    try:
        context.route("**/*", egress.handler(case.label))
        page = context.new_page()
        page.set_default_timeout(timeout_sec * 1000)
        if use_alarm:

            def _on_alarm(signum: int, frame: Any) -> None:
                raise _TestTimeout(f"テストが {timeout_sec:g} 秒を超えました")

            signal.signal(signal.SIGALRM, _on_alarm)
            signal.setitimer(signal.ITIMER_REAL, timeout_sec)
        case.fn(page)
    finally:
        if use_alarm:
            signal.setitimer(signal.ITIMER_REAL, 0)
        try:
            context.close()
        except Exception:  # noqa: BLE001
            pass


def _failed_step(exc: BaseException) -> str:
    step = getattr(exc, "failed_step", "")
    if step:
        return str(step)
    api = sys.modules.get("web.services.pw_spec_api")
    return str(getattr(api, "LAST_STEP", "") or "")


def run(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    progress = out / PROGRESS_NAME
    progress.write_text("", encoding="utf-8")
    egress_log = Path(args.egress_log) if args.egress_log else out / EGRESS_LOG_NAME
    spec_path = Path(args.spec)

    try:
        cases = load_cases(spec_path)
    except Exception as exc:  # noqa: BLE001
        raw = build_raw(spec_path.name, [], 0, status="ERROR", reason=f"spec load failed: {exc}", ok=False)
        (out / RAW_NAME).write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        traceback.print_exc()
        return EXIT_ERROR
    if args.grep:
        pattern = re.compile(args.grep)
        cases = [c for c in cases if pattern.search(c.label)]
    if not cases:
        raw = build_raw(spec_path.name, [], 0, status="ERROR", reason="no tests", ok=False)
        (out / RAW_NAME).write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        return EXIT_ERROR

    _append(progress, {"event": "begin", "total": len(cases)})
    egress = Egress(load_policy(args.policy), egress_log)
    results: list[dict[str, Any]] = []
    started = time.time()

    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = launch_browser(p, headless=not args.headed)
            try:
                for case in cases:
                    t0 = time.time()
                    status, error, step = "passed", "", ""
                    if case.skip:
                        status = "skipped"
                    else:
                        try:
                            _run_case(case, browser, egress, args.device, args.per_test_timeout, p)
                        except BaseException as exc:  # noqa: BLE001 - テスト失敗として記録
                            if isinstance(exc, KeyboardInterrupt):
                                raise
                            status, error, step = "failed", str(exc)[:400], _failed_step(exc)
                    rec = {
                        "title": case.label,
                        "status": status,
                        "duration": int((time.time() - t0) * 1000),
                        "error": error,
                        "failed_step": step,
                    }
                    results.append(rec)
                    _append(progress, {"event": "test", **rec})
            finally:
                try:
                    browser.close()
                except Exception:  # noqa: BLE001
                    pass
    except BrowserUnavailable as exc:
        write_blocked(out, exc)
        print(f"{BLOCKED_STATUS}: {exc}", file=sys.stderr)
        return EXIT_BLOCKED

    failed = sum(1 for r in results if r["status"] == "failed")
    raw = build_raw(
        spec_path.name,
        results,
        int((time.time() - started) * 1000),
        status="FAILED" if failed else "PASSED",
        ok=failed == 0,
    )
    (out / RAW_NAME).write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return EXIT_FAILED if failed else EXIT_OK


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="web.services.pw_runner")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--policy", default=None, help="JSON 文字列または @ファイル（既定は環境変数）")
    ap.add_argument("--egress-log", default=None)
    ap.add_argument("--device", choices=("pc", "mobile"), default="pc")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--grep", default=None)
    ap.add_argument("--per-test-timeout", type=float, default=DEFAULT_TIMEOUT_SEC)
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
