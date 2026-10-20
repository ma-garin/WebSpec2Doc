from __future__ import annotations

import html as html_mod
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Any, Final

# subprocess の下限タイムアウト（自動スケール時の最低保証値）
_SUBPROCESS_MIN_SEC = 600
# 自動スケール時に per_test × 件数 に足す安全マージン（起動・後片付け時間）
_SUBPROCESS_MARGIN_SEC = 120
# 自動スケールの上限（環境変数 WEBSPEC2DOC_PW_MAX_EXEC_SEC で上書き可）。
# 188件×120秒/件（ユーザー実測ケース）+ マージンの22680秒を包含する必要があるため7時間に設定。
_SUBPROCESS_MAX_SEC_DEFAULT = 25200  # 7時間


def _max_exec_sec() -> int:
    try:
        return int(os.environ.get("WEBSPEC2DOC_PW_MAX_EXEC_SEC", str(_SUBPROCESS_MAX_SEC_DEFAULT)))
    except ValueError:
        return _SUBPROCESS_MAX_SEC_DEFAULT


def _count_tests_in_spec(spec_path: Path) -> int:
    """spec 内のテスト件数を粗く数える（case 登録の数）。タイムアウトの自動スケール専用。"""
    try:
        text = spec_path.read_text(encoding="utf-8")
    except OSError:
        return 0
    return len(re.findall(r"^\s*@case\s*\(", text, flags=re.M))


def _resolve_timeout_sec(
    spec_path: Path, per_test_timeout_sec: int, timeout_sec: int | None
) -> int:
    """全体タイムアウトを決定する。

    明示指定（timeout_sec）があればそれを使う。無指定（None）の場合、
    spec 内のテスト件数 × per_test_timeout_sec + マージンを自動算出する
    （188件×120秒のような大規模実行が固定600秒で必ずkillされる不具合の修正）。
    下限は _SUBPROCESS_MIN_SEC、上限は環境変数で調整可能な安全弁。
    """
    if timeout_sec is not None:
        return timeout_sec
    test_count = _count_tests_in_spec(spec_path)
    if test_count <= 0:
        return _SUBPROCESS_MIN_SEC
    estimated = test_count * per_test_timeout_sec + _SUBPROCESS_MARGIN_SEC
    return max(_SUBPROCESS_MIN_SEC, min(estimated, _max_exec_sec()))


def run_playwright(
    spec_path: Path,
    output_dir: Path,
    per_test_timeout_sec: int = 30,
    timeout_sec: int | None = None,
    add_log: Callable[[str], None] | None = None,
    device: str = "pc",
    workers: int = 1,
    egress_policy: Any = None,
    browser: str = "auto",
    headed: bool = False,
    on_proc: Callable[[Any], None] | None = None,
    grep: str = "",
) -> dict[str, Any]:
    """
    Python spec（``*_spec.py``）を Python Playwright ランナーで実行し、結果を返す。

    実行は子プロセス ``python -m web.services.pw_runner``。顧客環境の Google Chrome /
    Microsoft Edge を使い、外部コマンドの導入・実行時ダウンロードは一切行わない。
    ブラウザが無ければ成功扱いにせず ``unavailable=True / blocked=True`` で返す。

    Args:
        spec_path: ``*_spec.py`` のパス（``.spec.ts`` は実行不可＝エクスポート専用）
        output_dir: レポート出力先ディレクトリ
        per_test_timeout_sec: 1テストあたりの制限時間
        timeout_sec: 子プロセス全体の最大待機時間。None なら件数から自動算出する。
        device: "pc"（既定）または "mobile"。ホワイトリスト外は "pc"。
        workers: 並列実行数（送信方針の予算計算にのみ使う。ランナーは直列で実行する）。
        egress_policy: K1 送信ゲートウェイの方針。省略時は既定方針。
        browser: "auto"（既定）/ "chrome" / "msedge"。
        headed: True でブラウザ画面を表示して実行する。
        on_proc: 起動した子プロセス（Popen）を受け取るフック（AutoRun の中止用）。
        grep: タイトルが一致するテストだけを実行する（正規表現）。
    """
    if device not in ("pc", "mobile"):
        device = "pc"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_report_path = output_dir / "playwright_report.json"
    fallback_html_path = output_dir / "playwright_report.html"
    progress_path = output_dir / "playwright_progress.ndjson"
    raw_json_path = output_dir / "playwright_raw.json"

    def _log(msg: str) -> None:
        if add_log:
            add_log(msg)

    if spec_path.suffix != ".py":
        return _error_result(
            f"{spec_path.name} は実行できません。TypeScript はエクスポート専用です。"
            "Python の spec（*_spec.py）を生成して実行してください。",
            json_report_path,
            fallback_html_path,
        )

    from web.services.egress_gateway import (
        EGRESS_LOG_NAME,
        POLICY_ENV,
        EgressPolicy,
        read_egress_report,
    )

    policy = egress_policy if egress_policy is not None else EgressPolicy(workers=workers)
    egress_log_path = output_dir / EGRESS_LOG_NAME
    if egress_log_path.exists():
        egress_log_path.unlink()
    if raw_json_path.exists():
        raw_json_path.unlink()

    resolved_timeout_sec = _resolve_timeout_sec(spec_path, per_test_timeout_sec, timeout_sec)

    cmd = [
        sys.executable,
        "-m",
        "web.services.pw_runner",
        "--spec",
        str(spec_path),
        "--out",
        str(output_dir),
        "--egress-log",
        str(egress_log_path),
        "--device",
        device,
        "--per-test-timeout",
        str(per_test_timeout_sec),
    ]
    if headed:
        cmd.append("--headed")
    if grep:
        cmd.extend(["--grep", grep])

    expected_total = _count_tests_in_spec(spec_path)
    _log(
        f"Playwright 実行中: {spec_path.name}"
        f"（{expected_total}件・1テストあたり{per_test_timeout_sec}秒・全体上限{resolved_timeout_sec}秒）"
    )

    try:
        env = os.environ.copy()
        env[POLICY_ENV] = policy.to_json()
        channel = normalize_browser(browser)
        if channel in _CHANNELS:
            env[_BROWSER_ENV] = channel
        proc = _spawn_and_wait(cmd, resolved_timeout_sec, env, on_proc)
    except subprocess.TimeoutExpired as exc:
        return _interrupted_result(
            resolved_timeout_sec,
            expected_total,
            progress_path,
            json_report_path,
            fallback_html_path,
            exc.stdout if isinstance(exc.stdout, str) else "",
            exc.stderr if isinstance(exc.stderr, str) else "",
        )
    except Exception as exc:
        return _error_result(str(exc), json_report_path, fallback_html_path)

    raw_json = _read_raw_json(raw_json_path, proc.stdout)
    result = _parse_results(raw_json, proc.stdout, proc.stderr, proc.returncode)
    result["egress"] = read_egress_report(egress_log_path).to_dict()
    json_report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    fallback_html_path.write_text(_build_html_report(result), encoding="utf-8")
    return result



def _spawn_and_wait(
    cmd: list[str],
    timeout_sec: int,
    env: dict[str, str],
    on_proc: Callable[[Any], None] | None,
) -> subprocess.CompletedProcess:
    """subprocess.run 相当の実行。on_proc がある場合のみ Popen で起動して登録する。

    subprocess.run はプロセスハンドルを外へ出さないため、AutoRun の中止から
    子プロセスを終了させられない。中止可能にする呼び出し元だけがこの Popen 経路を通る。
    """
    if on_proc is None:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, env=env)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    on_proc(proc)
    try:
        stdout, stderr = proc.communicate(timeout=timeout_sec)
    except subprocess.TimeoutExpired as err:
        proc.kill()
        stdout, stderr = proc.communicate()
        raise subprocess.TimeoutExpired(cmd, timeout_sec, output=stdout, stderr=stderr) from err
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout=stdout, stderr=stderr)


def _read_raw_json(raw_json_path: Path, stdout: str) -> dict[str, Any]:
    """JSON reporter のファイル出力を優先して読む。無ければ stdout をフォールバック解析する
    （旧バージョン互換・reporter がファイル書き込みに失敗した場合の保険）。
    """
    if raw_json_path.is_file():
        try:
            return json.loads(raw_json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return _parse_stdout_json(stdout)


def _parse_stdout_json(stdout: str) -> dict[str, Any]:
    """stdout から JSON オブジェクトを抽出する（プリアンブルがある場合も対応）。"""
    if not stdout:
        return {}
    # JSON は { から始まる。前後に余分な出力があっても検索して取り出す
    start = stdout.find("{")
    if start < 0:
        return {}
    try:
        return json.loads(stdout[start:])
    except (json.JSONDecodeError, ValueError):
        return {}


def _python_playwright_version() -> str:
    """この Python 環境の playwright パッケージのバージョン（診断表示用）。"""
    try:
        return _pkg_version("playwright")
    except PackageNotFoundError:
        return ""


#: 製品内実行で使えるブラウザ（顧客環境の Google Chrome / Microsoft Edge のみ）。
#: firefox / webkit は非対応（バンドルも導入もしない）。
SUPPORTED_BROWSERS: Final = ("auto", "chrome", "msedge")
_CHANNELS: Final = ("chrome", "msedge")
_BROWSER_ENV: Final = "WEBSPEC2DOC_BROWSER"
_BROWSER_ALIASES: Final = {
    "msedge": "msedge",
    "edge": "msedge",
    "chrome": "chrome",
    "chromium": "auto",
    "auto": "auto",
}

#: ブラウザが無いときの案内（導入コマンドは案内しない。Chrome / Edge の導入を促す）
BROWSER_UNAVAILABLE_GUIDE: Final = (
    "browser unavailable: Google Chrome または Microsoft Edge をインストールして、もう一度実行してください。"
)


def normalize_browser(raw: str) -> str:
    """利用者の指定を "auto" / "chrome" / "msedge" へ正規化する。判別できなければ空文字。

    黙って別ブラウザへ読み替えない。判別できないことは呼び出し側へ返す。
    """
    text = (raw or "").strip().lower()
    if not text:
        return ""
    for key, value in _BROWSER_ALIASES.items():
        if key in text:
            return value
    return ""


def ensure_browser_available(browser: str) -> tuple[bool, str]:
    """指定ブラウザが使えるかを「検出のみ」で確かめる。導入はしない。"""
    if browser not in SUPPORTED_BROWSERS:
        return False, f"対応していないブラウザです: {browser}（Chrome か Edge を指定してください）"
    from src.browser_detect import BrowserUnavailable, detect_browser

    try:
        detect_browser(prefer=None if browser == "auto" else browser)
    except BrowserUnavailable:
        return False, BROWSER_UNAVAILABLE_GUIDE
    return True, ""



_STEP_TITLE_RE = re.compile(r"^S\d+$")


def _scan_failed_step(steps: Any) -> str:
    """`S<n>` という題名の失敗ステップを、外側から順に探す。"""
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        title = str(step.get("title") or "")
        if step.get("error") and _STEP_TITLE_RE.match(title):
            return title
        nested = _scan_failed_step(step.get("steps") or [])
        if nested:
            return nested
    return ""


def _failed_step_title(results: Any) -> str:
    """JSON レポータの結果から、最初に失敗したステップ境界（`S<n>`）を取り出す。"""
    for result in results or []:
        if not isinstance(result, dict):
            continue
        found = _scan_failed_step(result.get("steps") or [])
        if found:
            return found
    return ""


def _parse_results(
    raw: dict[str, Any], stdout: str, stderr: str, returncode: int
) -> dict[str, Any]:
    suites: list[dict[str, Any]] = raw.get("suites") or []
    stats = raw.get("stats") or {}

    # stderr の先頭 500 文字をエラー診断用に保存
    stderr_snippet = (stderr or "")[:500]

    # ブラウザ未検出（ランナーが BLOCKED を書いた）。成功扱いにせず理由を伝搬する。
    if str(raw.get("status", "")).upper() == "BLOCKED":
        reason = str(raw.get("reason") or "browser unavailable")
        return {
            "ok": False,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "total": 0,
            "duration_ms": 0,
            "tests": [],
            "status": "BLOCKED",
            "blocked": True,
            "unavailable": True,
            "reason": reason,
            "error": f"{reason}: {BROWSER_UNAVAILABLE_GUIDE}",
            "tried": raw.get("tried") or [],
            "stdout": stdout[:4000] if stdout else "",
            "stderr": stderr[:2000] if stderr else "",
            "stderr_snippet": stderr_snippet,
        }

    # evidence-only: suites も stats も無い（＝そもそも結果を解析できなかった）場合、
    # returncode==0 であっても「成功」を偽装してはいけない。0/0/0 を無言で成功扱いに
    # していた過去の実装は、AutoRun で188件承認・実行したのに結果が全て0件で表示され、
    # かつどこにもエラーが出ない、という致命的な UX 破綻の直接原因だった。
    if not suites and not stats:
        error = f"実行結果を解析できませんでした（終了コード {returncode}）"
        if stderr_snippet:
            error += f": {stderr_snippet}"
        return {
            "ok": False,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "total": 0,
            "duration_ms": 0,
            "tests": [],
            "error": error,
            "stdout": stdout[:4000] if stdout else "",
            "stderr": stderr[:2000] if stderr else "",
            "stderr_snippet": stderr_snippet,
        }

    tests: list[dict[str, Any]] = []
    for suite in suites:
        for spec in suite.get("specs") or []:
            for run in spec.get("tests") or []:
                status = _map_status(run.get("status", ""), run.get("results") or [])
                tests.append(
                    {
                        "title": spec.get("title", ""),
                        "status": status,
                        "duration_ms": sum(
                            (r.get("duration") or 0) for r in (run.get("results") or [])
                        ),
                        "error": _first_error(run.get("results") or []),
                        "failed_step": _failed_step_title(run.get("results") or []),
                    }
                )

    passed = sum(1 for t in tests if t["status"] == "passed")
    failed = sum(1 for t in tests if t["status"] == "failed")
    skipped = sum(1 for t in tests if t["status"] == "skipped")
    total = len(tests) or int(stats.get("expected", 0)) + int(stats.get("unexpected", 0)) + int(
        stats.get("skipped", 0)
    )

    failed_total = failed or int(stats.get("unexpected", 0))
    return {
        "ok": returncode == 0 and failed_total == 0,
        "passed": passed or int(stats.get("expected", 0)),
        "failed": failed_total,
        "skipped": skipped or int(stats.get("skipped", 0)),
        "total": total,
        "duration_ms": int(stats.get("duration", 0)),
        "tests": tests,
        "stdout": stdout[:4000] if stdout else "",
        "stderr": stderr[:2000] if stderr else "",
        "stderr_snippet": stderr_snippet,
    }


def _map_status(raw_status: str, results: list[dict[str, Any]]) -> str:
    if raw_status in ("passed", "expected"):
        return "passed"
    if raw_status in ("failed", "unexpected"):
        return "failed"
    if raw_status == "flaky":
        # リトライで合格したケース — 合格扱い
        return "passed"
    if raw_status in ("skipped", "pending"):
        return "skipped"
    for r in results:
        if r.get("status") in ("passed", "expected"):
            return "passed"
        if r.get("status") in ("failed", "unexpected"):
            return "failed"
    return raw_status or "unknown"


def _first_error(results: list[dict[str, Any]]) -> str:
    for r in results:
        for err in r.get("errors") or []:
            msg = err.get("message") or err.get("value") or ""
            if msg:
                return str(msg)[:400]
    return ""


def _read_progress_ndjson(progress_path: Path) -> tuple[int | None, list[dict[str, Any]]]:
    """途中終了時に回収する進捗 NDJSON を読む。(expected_total, tests) を返す。

    ファイルが無い・空・壊れている場合は (None, []) — 呼び出し側は
    「部分結果ゼロ」として扱う（捏造しない）。
    """
    if not progress_path.is_file():
        return None, []
    expected_total: int | None = None
    tests: list[dict[str, Any]] = []
    try:
        for line in progress_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("event") == "begin":
                expected_total = int(obj.get("total") or 0)
            elif obj.get("event") == "test":
                tests.append(
                    {
                        "title": str(obj.get("title", "")),
                        "status": _map_status(str(obj.get("status", "")), []),
                        "duration_ms": int(obj.get("duration") or 0),
                        "error": str(obj.get("error", "")),
                        "failed_step": str(obj.get("failed_step", "")),
                    }
                )
    except OSError:
        return None, []
    return expected_total, tests


def _interrupted_result(
    timeout_sec: int,
    expected_total: int,
    progress_path: Path,
    json_path: Path,
    html_path: Path,
    partial_stdout: str,
    partial_stderr: str,
) -> dict[str, Any]:
    """全体タイムアウトで中断された実行の結果を組み立てる。

    JSON reporter は完走時にしか出力しないため、途中経過は進捗 NDJSON
    （onTestEnd で逐次追記）から回収する。進捗ファイルが無ければ
    実行済み0件として正直に報告する（捏造しない）。
    """
    ndjson_total, tests = _read_progress_ndjson(progress_path)
    total_expected = ndjson_total if ndjson_total else expected_total
    passed = sum(1 for t in tests if t["status"] == "passed")
    failed = sum(1 for t in tests if t["status"] == "failed")
    skipped = sum(1 for t in tests if t["status"] == "skipped")
    ran = len(tests)

    if ran:
        error = (
            f"テスト実行が制限時間 {timeout_sec}秒 に達したため中断しました。"
            f"{total_expected or '?'}件中 {ran}件まで実行済みです"
            f"（成功{passed}／失敗{failed}／スキップ{skipped}）。"
            "1テストあたりの制限時間を短くするか、対象テスト数を減らすと完走しやすくなります。"
        )
    else:
        error = (
            f"テスト実行が制限時間 {timeout_sec}秒 に達したため中断しました。"
            "実行済みのテストはありませんでした（起動処理に時間がかかっている可能性があります）。"
        )

    result: dict[str, Any] = {
        "ok": False,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "total": ran,
        "duration_ms": 0,
        "tests": tests,
        "error": error,
        "interrupted": True,
        "expected_total": total_expected,
        "stdout": partial_stdout[:4000] if partial_stdout else "",
        "stderr": partial_stderr[:2000] if partial_stderr else "",
    }
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(_build_html_report(result), encoding="utf-8")
    return result


def _unavailable_result(reason: str, json_path: Path, html_path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "total": 0,
        "duration_ms": 0,
        "tests": [],
        "error": reason,
        "unavailable": True,
    }
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(_build_html_report(result), encoding="utf-8")
    return result


def _error_result(error: str, json_path: Path, html_path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "total": 0,
        "duration_ms": 0,
        "tests": [],
        "error": error,
    }
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(_build_html_report(result), encoding="utf-8")
    return result


def _format_duration_ms(duration_ms: Any) -> str:
    """ミリ秒を「分秒」表記（例: 2分5秒／45秒）に整形する。evidence-only:
    値が無い・不正な場合は「不明」と明示する（0秒等の捏造をしない）。"""
    try:
        total_sec = int(duration_ms) // 1000
    except (TypeError, ValueError):
        return "不明"
    if total_sec < 0:
        return "不明"
    minutes, seconds = divmod(total_sec, 60)
    return f"{minutes}分{seconds}秒" if minutes else f"{seconds}秒"


def _build_html_report(result: dict[str, Any]) -> str:
    """日本語の実行サマリレポート（ライト/ダーク両対応・非エンジニア向け）を組み立てる。

    Playwright ネイティブレポート（英語・ダークモード固定）は
    「詳細（開発者向け）」として別途参照できるよう web/routes/auto_run.py 側で
    playwright_native_html キーに残す。ここでは非エンジニアにも読める
    日本語サマリを既定のレポートとする（R3-03/04/05）。自己完結（外部
    script/link を読み込まない）で CSP を変更せずに単体表示できる。
    """
    interrupted = bool(result.get("interrupted"))
    unavailable = bool(result.get("unavailable"))
    ok = bool(result.get("ok")) and not interrupted and not unavailable
    if unavailable:
        status_text, status_cls = "実行不可", "warn"
    elif interrupted:
        status_text, status_cls = "中断", "warn"
    elif ok:
        status_text, status_cls = "成功", "ok"
    else:
        status_text, status_cls = "失敗", "fail"

    error_section = ""
    if result.get("error"):
        error_section = (
            f'<div class="err"><strong>{"注記" if (ok) else "エラー"}:</strong> '
            f"{html_mod.escape(str(result['error']))}</div>"
        )

    status_labels = {
        "passed": "✅ 成功",
        "failed": "❌ 失敗",
        "skipped": "⏭ スキップ",
        "unknown": "❔ 不明",
    }
    rows = "".join(
        "<tr class='{cls}'><td>{title}</td><td>{status}</td>"
        "<td>{dur}</td><td>{err}</td></tr>".format(
            cls=(
                "pass"
                if t["status"] == "passed"
                else ("skip" if t["status"] == "skipped" else "fail")
            ),
            title=html_mod.escape(str(t.get("title", ""))),
            status=html_mod.escape(
                status_labels.get(str(t.get("status", "")), str(t.get("status", "")))
            ),
            dur=_format_duration_ms(t.get("duration_ms")),
            err=(
                "<details><summary>エラー詳細</summary><pre>"
                f"{html_mod.escape(str(t.get('error') or ''))}</pre></details>"
                if t.get("error")
                else ""
            ),
        )
        for t in result.get("tests", [])
    )

    total_duration = _format_duration_ms(result.get("duration_ms"))

    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><title>テスト実行レポート</title>
<style>
:root {{
  --bg:#ffffff; --fg:#111827; --border:#e5e7eb; --th-bg:#f1f5f9; --pre-bg:#f9fafb;
  --ok:#16a34a; --fail:#dc2626; --warn:#d97706; --skip:#9ca3af; --err-bg:#fef2f2; --err-border:#fecaca;
  --muted:#6b7280;
}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:28px;color:var(--fg);background:var(--bg)}}
.intro{{color:var(--muted);font-size:14px;margin:6px 0 18px}}
.badge{{display:inline-block;padding:4px 14px;border-radius:20px;font-weight:700;color:#fff;
  background:var(--{status_cls if status_cls != 'warn' else 'warn'});font-size:18px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px;margin:18px 0}}
.card{{border:1px solid var(--border);border-radius:8px;padding:12px;text-align:center}}
.num{{font-size:28px;font-weight:800}}
table{{border-collapse:collapse;width:100%;margin-top:14px}}
td,th{{border:1px solid var(--border);padding:8px;font-size:13px;vertical-align:top}}
th{{background:var(--th-bg)}}
tr.pass td:nth-child(2){{color:var(--ok);font-weight:600}}
tr.fail td:nth-child(2){{color:var(--fail);font-weight:600}}
tr.skip td:nth-child(2){{color:var(--skip)}}
.err{{background:var(--err-bg);border:1px solid var(--err-border);border-radius:6px;padding:12px;margin:14px 0;color:var(--fail);font-size:13px}}
pre{{background:var(--pre-bg);border:1px solid var(--border);border-radius:6px;padding:12px;font-size:11px;white-space:pre-wrap;overflow-x:auto}}
details summary{{cursor:pointer;color:var(--fail);font-size:12px}}
@media print {{ body{{margin:8mm}} .card{{break-inside:avoid}} }}
</style></head>
<body>
<h1>テスト実行レポート</h1>
<p class="intro">このレポートは自動テストの実行結果です。❌の行から確認してください。</p>
<span class="badge">{status_text}</span>
<div class="cards">
  <div class="card"><div class="num" style="color:var(--ok)">{result.get('passed',0)}</div><div>成功</div></div>
  <div class="card"><div class="num" style="color:var(--fail)">{result.get('failed',0)}</div><div>失敗</div></div>
  <div class="card"><div class="num" style="color:var(--skip)">{result.get('skipped',0)}</div><div>スキップ</div></div>
  <div class="card"><div class="num">{result.get('total',0)}</div><div>合計</div></div>
  <div class="card"><div class="num">{total_duration}</div><div>実行時間</div></div>
</div>
{error_section}
<table><thead><tr><th>テスト</th><th>結果</th><th>時間</th><th>エラー</th></tr></thead>
<tbody>{rows}</tbody></table>
</body></html>"""
