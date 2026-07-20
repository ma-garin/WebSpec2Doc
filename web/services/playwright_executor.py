from __future__ import annotations

import html as html_mod
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
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
    device: str = "pc",
    workers: int = 1,
    egress_policy: Any = None,
) -> dict[str, Any]:
    """
    ローカル @playwright/test CLI でスペックを実行し、結果を返す。

    Args:
        spec_path: .spec.ts ファイルのパス
        output_dir: レポート出力先ディレクトリ
        per_test_timeout_sec: 1テストあたりの制限時間（Playwright config の timeout）
        timeout_sec: subprocess 全体の最大待機時間。None なら
            spec 内のテスト件数から自動算出する（既定の挙動）。
        device: "pc"（既定）または "mobile"（iPhone 13相当のビューポート/UA）。
            ホワイトリスト外の値は "pc" として扱う。
        workers: 並列実行数。既定は1（対象サイトへ同時多数アクセスしないための配慮）。
            対象へ一切アクセスしない自己検証（mutation_verifier）等、外部への
            配慮が不要な用途でのみ増やすこと。
        egress_policy: K1 送信ゲートウェイの方針（`EgressPolicy`）。
            省略時は既定方針を使う。生成テストは必ずゲートウェイを経由するため、
            ここで SSRF 遮断・予算上限・全件記録が強制される。
    """
    if device not in ("pc", "mobile"):
        device = "pc"
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

    # @playwright/test パッケージを確認・インストール（playwright CLI の有無とは独立）。
    # _pw_test_available() は単なる存在確認ではなく、Python側 playwright との
    # バージョン一致・ブラウザ実在まで確認する（そうしないと、異なるバージョンで
    # 既にインストール済み・ブラウザ未導入のケースを見逃し、実行時に
    # browserType.launch: Executable doesn't exist で全滅する）。
    if not _pw_test_available():
        _log("実行環境をセットアップしています…")
        ok, msg = _ensure_pw_env(_PW_ENV_DIR)
        _log(msg)
        if not ok:
            return _unavailable_result(msg, json_report_path, fallback_html_path)

    # ローカル CLI を優先（global CLI との version mismatch を回避）
    # resolve() はシンボリックリンクを辿って cli.js を返すため使わない
    local_cli = _PW_ENV_DIR / "node_modules" / ".bin" / "playwright"
    cli_cmd = str(local_cli) if local_cli.is_file() else "npx"

    # K1 送信ゲートウェイのフィクスチャを spec の隣へ生成する。
    # 生成 spec は `./_autorun_egress` から test を import するため、
    # これが無いと実行できない＝ゲートウェイの迂回が構造的に不可能。
    from web.services.egress_gateway import (
        EGRESS_LOG_NAME,
        EgressPolicy,
        write_egress_fixture,
    )

    policy = egress_policy if egress_policy is not None else EgressPolicy(workers=workers)
    egress_log_path = output_dir / EGRESS_LOG_NAME
    if egress_log_path.exists():
        egress_log_path.unlink()
    write_egress_fixture(spec_path.parent, egress_log_path)

    raw_json_path = output_dir / "playwright_raw.json"
    # JS コンフィグを spec ファイルの隣に生成（レポーター含め全設定を記述）
    config_path = _write_pw_config(
        spec_path=spec_path,
        html_output_dir=pw_html_dir,
        per_test_timeout_ms=per_test_timeout_sec * 1000,
        json_output_path=raw_json_path,
        progress_path=progress_path,
        device=device,
        workers=workers,
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
        # K1: 送信方針をフィクスチャへ渡す（SSRF遮断・予算・全件記録）
        from web.services.egress_gateway import POLICY_ENV

        env[POLICY_ENV] = policy.to_json()
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
    # K1: 実際に何が送信され、何が遮断されたかの記録。
    # 「送信0」を主張する用途（自己検証）では、これが唯一の証拠になる。
    from web.services.egress_gateway import read_egress_report

    result["egress"] = read_egress_report(egress_log_path).to_dict()
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
    device: str = "pc",
    workers: int = 1,
) -> Path:
    """JS 形式の playwright config を生成する（TypeScript import 不要）。

    device="mobile" 時のみ use ブロックに iPhone 13 相当のビューポート/UA を
    追記する（R3-02: PC/モバイル選択）。ホワイトリスト外の値は "pc" として扱う。
    """
    if device not in ("pc", "mobile"):
        device = "pc"
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

    mobile_use = (
        (
            "    viewport: { width: 390, height: 844 },\n"
            "    isMobile: true,\n"
            "    hasTouch: true,\n"
            "    deviceScaleFactor: 3,\n"
            "    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',\n"
        )
        if device == "mobile"
        else ""
    )

    config_js = (
        "module.exports = {\n"
        f"  testDir: {json.dumps(spec_dir_abs)},\n"
        f"  testMatch: {json.dumps(spec_path.name)},\n"
        f"  timeout: {per_test_timeout_ms},\n"
        f"  workers: {int(workers) if workers and workers > 0 else 1},\n"
        f"  outputDir: {json.dumps(artifacts_dir_abs)},\n"
        "  use: {\n"
        "    screenshot: 'on',\n"
        "    trace: 'retain-on-failure',\n"
        f"    actionTimeout: {action_timeout_ms},\n"
        f"    navigationTimeout: {nav_timeout_ms},\n"
        f"{mobile_use}"
        "  },\n"
        "  reporter: [\n" + "\n".join(reporters) + "\n"
        "  ],\n"
        "};\n"
    )
    config_path.write_text(config_js, encoding="utf-8")
    return config_path


def _pw_test_available() -> bool:
    """ローカルまたは共有 env に @playwright/test があり、実行可能な状態かを確認する。

    共有 env（_PW_ENV_DIR）については、単に存在するかだけでなく Python 側
    playwright とのバージョン一致・ブラウザ実在まで確認する。どちらか欠けて
    いれば False を返し、呼び出し側で _ensure_pw_env()（再構築・自動導入）
    を実行させる（バージョン不一致のまま「セットアップ済み」と誤判定すると、
    実行時に browserType.launch: Executable doesn't exist で全滅する）。
    """
    local = Path("node_modules/@playwright/test")
    if local.is_dir():
        return True
    shared = _PW_ENV_DIR / "node_modules/@playwright/test"
    if shared.is_dir():
        target_ver = _python_playwright_version()
        installed_ver = _installed_pw_test_version(_PW_ENV_DIR)
        if target_ver and installed_ver and installed_ver != target_ver:
            return False
        if not _browsers_present(_configured_browsers_path(), target_ver):
            return False
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
    """npx playwright の version 文字列を返す（例: '1.59.1'）。

    diagnostics 表示専用。npm パッケージのバージョン決定には使わない
    （_python_playwright_version 参照 — npx解決の最新版に追従すると
    Python 側 playwright パッケージの導入済み Chromium と食い違う）。
    """
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


def _python_playwright_version() -> str:
    """この Python 環境にインストールされている playwright パッケージのバージョンを返す。

    AutoRun が使う npm @playwright/test は、このバージョンに必ずピン止めする。
    `npx playwright --version` で決めていた旧実装は、npx が解決する最新版
    （Python 側より新しいことが多い）を拾ってしまい、Python 側の playwright が
    .runtime/ms-playwright に導入した Chromium ビルドと一致しない
    バージョンの @playwright/test がテストを実行しようとして
    'browserType.launch: Executable doesn't exist' で全滅する不具合の原因だった。
    """
    try:
        return _pkg_version("playwright")
    except PackageNotFoundError:
        return ""


def _installed_pw_test_version(env_dir: Path) -> str:
    """env_dir に既にインストールされている @playwright/test のバージョンを返す。"""
    pkg_json = env_dir / "node_modules" / "@playwright" / "test" / "package.json"
    if not pkg_json.is_file():
        return ""
    try:
        data = json.loads(pkg_json.read_text(encoding="utf-8"))
        return str(data.get("version", ""))
    except (OSError, json.JSONDecodeError):
        return ""


def _configured_browsers_path() -> Path:
    """PLAYWRIGHT_BROWSERS_PATH を解決する（未設定ならリポジトリ既定へ固定）。"""
    if str(Path("src").resolve()) not in sys.path:
        sys.path.insert(0, str(Path("src").resolve()))
    from crawler.playwright_runtime import configure_playwright_browsers_path

    return configure_playwright_browsers_path()


def _required_browser_globs(pw_test_version: str) -> tuple[str, ...]:
    """@playwright/test の版が実行時に要求するブラウザディレクトリの glob を返す。

    1.49 以降は headless 実行の既定が chromium_headless_shell-<build> の別バイナリに
    変わったため、chromium-* だけでは 'Executable doesn't exist' で全滅する
    （R3-08: chromium-1117 のみ導入済みで chromium_headless_shell-1217 が無い環境で再発）。
    """
    try:
        major, minor = (int(x) for x in pw_test_version.split(".")[:2])
    except (ValueError, AttributeError):
        return ("chromium-*", "chromium_headless_shell-*")  # 不明時は両方要求（安全側）
    if (major, minor) >= (1, 49):
        return ("chromium-*", "chromium_headless_shell-*")
    return ("chromium-*",)


def _browsers_present(browsers_path: Path, pw_test_version: str) -> bool:
    """必要ブラウザが全て導入済みか（版対応・AND判定）。実行ファイル実在まで確認する。

    ディレクトリだけ残って中身が空のケース（インストール強制終了・ボリューム
    破損等）も「欠落」として扱う。version 不一致のまま OR 判定していた旧実装は、
    chromium-* だけ残っていて chromium_headless_shell-* が無い環境を
    「導入済み」と誤判定し、自動修復をスキップしてテスト全滅を招いていた。
    """
    if not browsers_path.is_dir():
        return False
    for pattern in _required_browser_globs(pw_test_version):
        dirs = list(browsers_path.glob(pattern))
        if not dirs:
            return False
        # ディレクトリだけ残って中身が空のケース（強制終了等）も欠落として扱う
        if not any(p.is_file() for d in dirs for p in d.rglob("*")):
            return False
    return True


def _ensure_browsers_installed(pw_test_version: str) -> tuple[bool, str]:
    """chromium ブラウザ本体の実在を確認し、無ければ自動導入する。

    npm @playwright/test を Python 版と同一バージョンにピン止めしても、
    .runtime/ms-playwright にブラウザが一度も導入されていない環境
    （新規チェックアウト・コンテナ再作成直後等）では、実行時に
    'browserType.launch: Executable doesn't exist' で全滅する。
    """
    browsers_path = _configured_browsers_path()
    if _browsers_present(browsers_path, pw_test_version):
        return True, ""
    if not shutil.which("npx"):
        return False, "npx が見つからず Playwright ブラウザを自動導入できません。"
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_path)
    try:
        proc = subprocess.run(
            ["npx", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(_PW_ENV_DIR),
            env=env,
        )
        if proc.returncode != 0:
            return False, f"Playwright ブラウザの自動導入に失敗しました: {proc.stderr[:300]}"
        # 自動導入後も再検証する（導入コマンドが chromium_headless_shell を
        # 含んでいない版・部分的に失敗した場合を見逃さないため）。
        if not _browsers_present(browsers_path, pw_test_version):
            missing = [
                pattern
                for pattern in _required_browser_globs(pw_test_version)
                if not any(browsers_path.glob(pattern))
            ]
            missing_desc = ", ".join(missing) if missing else "実行ファイル"
            return False, f"自動導入後もブラウザが不足しています: {missing_desc}"
        return True, "Playwright ブラウザ（chromium）を自動導入しました。"
    except subprocess.TimeoutExpired:
        return False, "Playwright ブラウザの自動導入がタイムアウトしました。"
    except Exception as exc:
        return False, f"Playwright ブラウザの自動導入エラー: {exc}"


def _ensure_pw_env(env_dir: Path) -> tuple[bool, str]:
    """@playwright/test を env_dir にインストールする（Python側 playwright と同バージョン）。

    バージョン不一致（既存インストール済みの @playwright/test が Python 側と
    異なる場合。過去は npx 解決の最新版でインストールしていたため必ず発生していた）
    を検出した場合は node_modules を破棄して再構築する。
    """
    env_dir.mkdir(parents=True, exist_ok=True)
    pkg_json = env_dir / "package.json"

    target_ver = _python_playwright_version()
    if not target_ver:
        return False, (
            "Python側 playwright のバージョンを特定できないため実行を中止しました"
            "（latest の暗黙インストールはブラウザ不一致全滅の原因になるため行いません）。"
            "venv を有効化し `pip show playwright` で確認してください。"
        )
    installed_ver = _installed_pw_test_version(env_dir)
    version_mismatch = bool(installed_ver) and installed_ver != target_ver

    if version_mismatch:
        # 既存envがPython側と異なるバージョンでインストールされている
        # （旧実装のnpx最新版インストール等）→ ブラウザ実行不能を防ぐため再構築する
        shutil.rmtree(env_dir / "node_modules", ignore_errors=True)

    already_installed = (env_dir / "node_modules/@playwright/test").is_dir()
    if already_installed and not version_mismatch:
        ok, msg = _ensure_browsers_installed(target_ver)
        if not ok:
            return False, msg
        return True, "@playwright/test は既にセットアップ済みです。"

    if not shutil.which("npm"):
        return False, "npm が見つかりません。Node.js をインストールしてください。"

    dep_spec = target_ver
    pkg_json.write_text(
        json.dumps(
            {
                "name": "autorun-env",
                "private": True,
                "dependencies": {"@playwright/test": dep_spec},
            }
        ),
        encoding="utf-8",
    )

    pkg = f"@playwright/test@{target_ver}"

    try:
        proc = subprocess.run(
            ["npm", "install", pkg, "--prefix", str(env_dir)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode != 0:
            return False, f"npm install 失敗: {proc.stderr[:300]}"
    except subprocess.TimeoutExpired:
        return False, "npm install タイムアウト"
    except Exception as exc:
        return False, f"npm install エラー: {exc}"

    ok, msg = _ensure_browsers_installed(target_ver)
    if not ok:
        return False, msg
    return True, f"@playwright/test {target_ver or ''} のインストールが完了しました。"


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
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg:#0f172a; --fg:#e5e7eb; --border:#334155; --th-bg:#1e293b; --pre-bg:#111827;
    --err-bg:#3f1d1d; --err-border:#7f1d1d; --muted:#9ca3af;
  }}
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
