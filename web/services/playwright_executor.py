from __future__ import annotations

import html as html_mod
import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

# AutoRun が生成した .spec.ts を実行するための共有 node_modules の場所
_PW_ENV_DIR = Path("output/.playwright_env")

# Playwright HTML レポートのサブディレクトリ名
_PW_HTML_SUBDIR = "playwright-report"

# spec ファイルと並べて生成する一時 JS コンフィグ／進捗レポーター名
_PW_CONFIG_NAME = "_autorun_pw.config.js"
_PW_PROGRESS_REPORTER_NAME = "_autorun_pw.progress_reporter.js"

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
    """spec.ts 内のテスト件数を粗く数える（test( 呼び出しの数）。

    正確な AST 解析はしない（オーバーエンジニアリング）。件数はタイムアウトの
    自動スケールにのみ使うため、多少のズレがあっても安全側（下限600秒保証）に倒れる。
    """
    try:
        text = spec_path.read_text(encoding="utf-8")
    except OSError:
        return 0
    return len(re.findall(r"(?<![.\w])test\s*\(", text))


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
) -> dict[str, Any]:
    """
    ローカル @playwright/test CLI でスペックを実行し、結果を返す。

    Args:
        spec_path: .spec.ts ファイルのパス
        output_dir: レポート出力先ディレクトリ
        per_test_timeout_sec: 1テストあたりの制限時間（Playwright config の timeout）
        timeout_sec: subprocess 全体の最大待機時間。None なら
            spec 内のテスト件数から自動算出する（既定の挙動）。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    json_report_path = output_dir / "playwright_report.json"
    fallback_html_path = output_dir / "playwright_report.html"
    pw_html_dir = output_dir / _PW_HTML_SUBDIR
    progress_path = output_dir / "playwright_progress.ndjson"

    def _log(msg: str) -> None:
        if add_log:
            add_log(msg)

    if not shutil.which("npx"):
        return _unavailable_result(
            "npx が見つかりません。Node.js をインストールしてください。",
            json_report_path,
            fallback_html_path,
        )

    # @playwright/test パッケージを確認・インストール（playwright CLI の有無とは独立）
    if not _pw_test_available():
        _log("@playwright/test をセットアップしています…")
        ok, msg = _ensure_pw_env(_PW_ENV_DIR)
        _log(msg)
        if not ok:
            return _unavailable_result(msg, json_report_path, fallback_html_path)

    # ローカル CLI を優先（global CLI との version mismatch を回避）
    # resolve() はシンボリックリンクを辿って cli.js を返すため使わない
    local_cli = _PW_ENV_DIR / "node_modules" / ".bin" / "playwright"
    cli_cmd = str(local_cli) if local_cli.is_file() else "npx"

    raw_json_path = output_dir / "playwright_raw.json"
    # JS コンフィグを spec ファイルの隣に生成（レポーター含め全設定を記述）
    config_path = _write_pw_config(
        spec_path=spec_path,
        html_output_dir=pw_html_dir,
        per_test_timeout_ms=per_test_timeout_sec * 1000,
        json_output_path=raw_json_path,
        progress_path=progress_path,
    )

    resolved_timeout_sec = _resolve_timeout_sec(spec_path, per_test_timeout_sec, timeout_sec)

    env_node_modules = str((_PW_ENV_DIR / "node_modules").resolve())
    # --reporter=json は config の reporter 配列を上書きするため使わない
    # config で json (ファイル) + html (ファイル) + 進捗(ndjson) の全設定済み
    if cli_cmd == "npx":
        cmd = ["npx", "playwright", "test", "--config", str(config_path.resolve())]
    else:
        cmd = [cli_cmd, "test", "--config", str(config_path.resolve())]

    expected_total = _count_tests_in_spec(spec_path)
    _log(
        f"Playwright 実行中: {spec_path.name}"
        f"（{expected_total}件・1テストあたり{per_test_timeout_sec}秒・全体上限{resolved_timeout_sec}秒）"
    )

    try:
        env = os.environ.copy()
        existing = env.get("NODE_PATH", "")
        env["NODE_PATH"] = f"{env_node_modules}:{existing}" if existing else env_node_modules
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=resolved_timeout_sec,
            env=env,
        )
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
    json_report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    fallback_html_path.write_text(_build_html_report(result), encoding="utf-8")
    return result


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


def _write_progress_reporter(reporter_path: Path) -> None:
    """途中終了しても実行済みテストが追記されていく NDJSON 進捗レポーターを生成する。

    onTestEnd で1行/テスト追記するため、subprocess が SIGKILL されても
    直前までの実行済みテストの結果はファイルに残る（部分結果の回収を可能にする）。
    """
    reporter_js = """
const fs = require('fs');

class ProgressReporter {
  constructor(options) {
    this._path = (options && options.progressPath) || 'playwright_progress.ndjson';
    fs.writeFileSync(this._path, '');
  }
  _append(obj) {
    fs.appendFileSync(this._path, JSON.stringify(obj) + '\\n');
  }
  onBegin(config, suite) {
    let total = 0;
    try { total = suite.allTests().length; } catch (e) { total = 0; }
    this._append({ event: 'begin', total });
  }
  onTestEnd(test, result) {
    let message = '';
    if (result.errors && result.errors.length) {
      message = String(result.errors[0].message || result.errors[0].value || '').slice(0, 400);
    }
    this._append({
      event: 'test',
      title: test.title,
      status: result.status,
      duration: result.duration || 0,
      error: message,
    });
  }
}

module.exports = ProgressReporter;
"""
    reporter_path.write_text(reporter_js, encoding="utf-8")


def _write_pw_config(
    spec_path: Path,
    html_output_dir: Path,
    per_test_timeout_ms: int = 30_000,
    json_output_path: Path | None = None,
    progress_path: Path | None = None,
) -> Path:
    """JS 形式の playwright config を生成する（TypeScript import 不要）。"""
    config_path = spec_path.parent / _PW_CONFIG_NAME
    reporter_path = spec_path.parent / _PW_PROGRESS_REPORTER_NAME
    spec_dir_abs = str(spec_path.parent.resolve())
    html_dir_abs = str(html_output_dir.resolve())
    # テスト成果物（スクショ・トレース）の保存先
    artifacts_dir_abs = str((html_output_dir.parent / "test-results").resolve())
    # アクションタイムアウト: per-test timeout の半分（最大 15s）
    action_timeout_ms = min(per_test_timeout_ms // 2, 15_000)
    # ナビゲーションタイムアウト: per-test timeout（最大 30s）
    nav_timeout_ms = min(per_test_timeout_ms, 30_000)

    reporters = [
        "    ['html', " + json.dumps({"outputFolder": html_dir_abs, "open": "never"}) + "],"
    ]
    if json_output_path is not None:
        reporters.insert(
            0,
            "    ['json', " + json.dumps({"outputFile": str(json_output_path.resolve())}) + "],",
        )
    else:
        reporters.insert(0, "    ['json'],")
    if progress_path is not None:
        _write_progress_reporter(reporter_path)
        reporters.append(
            "    ["
            + json.dumps(str(reporter_path.resolve()))
            + ", "
            + json.dumps({"progressPath": str(progress_path.resolve())})
            + "],"
        )

    config_js = (
        "module.exports = {\n"
        f"  testDir: {json.dumps(spec_dir_abs)},\n"
        f"  testMatch: {json.dumps(spec_path.name)},\n"
        f"  timeout: {per_test_timeout_ms},\n"
        "  workers: 1,\n"
        f"  outputDir: {json.dumps(artifacts_dir_abs)},\n"
        "  use: {\n"
        "    screenshot: 'on',\n"
        "    trace: 'retain-on-failure',\n"
        f"    actionTimeout: {action_timeout_ms},\n"
        f"    navigationTimeout: {nav_timeout_ms},\n"
        "  },\n"
        "  reporter: [\n" + "\n".join(reporters) + "\n"
        "  ],\n"
        "};\n"
    )
    config_path.write_text(config_js, encoding="utf-8")
    return config_path


def _pw_test_available() -> bool:
    """ローカルまたは共有 env に @playwright/test があるか確認。"""
    local = Path("node_modules/@playwright/test")
    shared = _PW_ENV_DIR / "node_modules/@playwright/test"
    if local.is_dir() or shared.is_dir():
        return True
    try:
        result = subprocess.run(
            ["node", "-e", "require.resolve('@playwright/test')"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _get_cli_version() -> str:
    """npx playwright の version 文字列を返す（例: '1.59.1'）。"""
    try:
        proc = subprocess.run(
            ["npx", "playwright", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # "Version 1.59.1" → "1.59.1"
        parts = proc.stdout.strip().split()
        if len(parts) >= 2:
            return parts[-1]
    except Exception:
        pass
    return ""


def _ensure_pw_env(env_dir: Path) -> tuple[bool, str]:
    """@playwright/test を env_dir にインストールする（CLI と同バージョン）。"""
    env_dir.mkdir(parents=True, exist_ok=True)
    pkg_json = env_dir / "package.json"
    if not pkg_json.exists():
        pkg_json.write_text('{"name":"autorun-env","private":true}', encoding="utf-8")

    pw_test_dir = env_dir / "node_modules/@playwright/test"
    if pw_test_dir.is_dir():
        return True, "@playwright/test は既にセットアップ済みです。"

    if not shutil.which("npm"):
        return False, "npm が見つかりません。Node.js をインストールしてください。"

    # CLI と同バージョンをインストールして version mismatch を防ぐ
    cli_ver = _get_cli_version()
    pkg = f"@playwright/test@{cli_ver}" if cli_ver else "@playwright/test"

    try:
        proc = subprocess.run(
            ["npm", "install", pkg, "--prefix", str(env_dir)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode == 0:
            return True, f"@playwright/test {cli_ver or ''} のインストールが完了しました。"
        return False, f"npm install 失敗: {proc.stderr[:300]}"
    except subprocess.TimeoutExpired:
        return False, "npm install タイムアウト"
    except Exception as exc:
        return False, f"npm install エラー: {exc}"


def _parse_results(
    raw: dict[str, Any], stdout: str, stderr: str, returncode: int
) -> dict[str, Any]:
    suites: list[dict[str, Any]] = raw.get("suites") or []
    stats = raw.get("stats") or {}

    # stderr の先頭 500 文字をエラー診断用に保存
    stderr_snippet = (stderr or "")[:500]

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


def _build_html_report(result: dict[str, Any]) -> str:
    """日本語の実行サマリレポート（ライト/ダーク両対応）を組み立てる。

    Playwright ネイティブレポート（英語・ダークモード固定）は
    「詳細（開発者向け）」として別途参照できるよう web/routes/report.py 側で
    playwright_native_html キーに残す。ここでは非エンジニアにも読める
    日本語サマリを既定のレポートとする。
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

    status_labels = {"passed": "成功", "failed": "失敗", "skipped": "スキップ", "unknown": "不明"}
    rows = "".join(
        "<tr class='{cls}'><td>{title}</td><td>{status}</td>"
        "<td>{dur}ms</td><td>{err}</td></tr>".format(
            cls=(
                "pass"
                if t["status"] == "passed"
                else ("skip" if t["status"] == "skipped" else "fail")
            ),
            title=html_mod.escape(str(t.get("title", ""))),
            status=html_mod.escape(
                status_labels.get(str(t.get("status", "")), str(t.get("status", "")))
            ),
            dur=t.get("duration_ms", 0),
            err=html_mod.escape(str(t.get("error") or "")[:120]),
        )
        for t in result.get("tests", [])
    )

    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><title>テスト実行レポート</title>
<style>
:root {{
  --bg:#ffffff; --fg:#111827; --border:#e5e7eb; --th-bg:#f1f5f9; --pre-bg:#f9fafb;
  --ok:#16a34a; --fail:#dc2626; --warn:#d97706; --skip:#9ca3af; --err-bg:#fef2f2; --err-border:#fecaca;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg:#0f172a; --fg:#e5e7eb; --border:#334155; --th-bg:#1e293b; --pre-bg:#111827;
    --err-bg:#3f1d1d; --err-border:#7f1d1d;
  }}
}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:28px;color:var(--fg);background:var(--bg)}}
.badge{{display:inline-block;padding:4px 14px;border-radius:20px;font-weight:700;color:#fff;
  background:var(--{status_cls if status_cls != 'warn' else 'warn'});font-size:18px}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:18px 0}}
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
</style></head>
<body>
<h1>テスト実行レポート</h1>
<span class="badge">{status_text}</span>
<div class="cards">
  <div class="card"><div class="num" style="color:var(--ok)">{result.get('passed',0)}</div><div>成功</div></div>
  <div class="card"><div class="num" style="color:var(--fail)">{result.get('failed',0)}</div><div>失敗</div></div>
  <div class="card"><div class="num" style="color:var(--skip)">{result.get('skipped',0)}</div><div>スキップ</div></div>
  <div class="card"><div class="num">{result.get('total',0)}</div><div>合計</div></div>
</div>
{error_section}
<table><thead><tr><th>テスト</th><th>結果</th><th>時間</th><th>エラー</th></tr></thead>
<tbody>{rows}</tbody></table>
</body></html>"""
