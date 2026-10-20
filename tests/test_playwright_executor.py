from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from web.services.playwright_executor import (
    _build_html_report,
    _count_tests_in_spec,
    _error_result,
    _first_error,
    _map_status,
    _parse_results,
    _parse_stdout_json,
    _python_playwright_version,
    _read_progress_ndjson,
    _resolve_timeout_sec,
    _unavailable_result,
    ensure_browser_available,
    normalize_browser,
    run_playwright,
)

# ─────────────────────── フィクスチャ ───────────────────────


@pytest.fixture()
def tmp_out(tmp_path: Path) -> Path:
    return tmp_path / "out"


def _mock_proc(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    p = MagicMock()
    p.stdout = stdout
    p.stderr = stderr
    p.returncode = returncode
    return p


_VALID_JSON = json.dumps(
    {
        "suites": [
            {
                "specs": [
                    {
                        "title": "ログイン画面表示",
                        "tests": [
                            {
                                "status": "passed",
                                "results": [{"duration": 120, "errors": []}],
                            }
                        ],
                    }
                ],
            }
        ],
        "stats": {"expected": 1, "unexpected": 0, "skipped": 0, "total": 1, "duration": 120},
    }
)

_FAILED_JSON = json.dumps(
    {
        "suites": [
            {
                "specs": [
                    {
                        "title": "ログイン失敗ケース",
                        "tests": [
                            {
                                "status": "failed",
                                "results": [
                                    {"duration": 80, "errors": [{"message": "期待値と異なります"}]}
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
        "stats": {"expected": 0, "unexpected": 1, "skipped": 0, "total": 1, "duration": 80},
    }
)


def _out_dir(cmd: list[str]) -> Path:
    return Path(cmd[cmd.index("--out") + 1])


def _write_raw_json_via_runner(monkeypatch: pytest.MonkeyPatch, content: str) -> list[list[str]]:
    """子プロセス（pw_runner）の代わりに、--out が指す playwright_raw.json を書くフェイク。
    実行されたコマンドを返す（検証用）。
    """
    seen: list[list[str]] = []

    def fake_run(cmd: list[str], **_: object) -> MagicMock:
        seen.append(list(cmd))
        (_out_dir(cmd) / "playwright_raw.json").write_text(content, encoding="utf-8")
        return _mock_proc(content)

    monkeypatch.setattr("web.services.playwright_executor.subprocess.run", fake_run)
    return seen


@pytest.fixture()
def spec_py(tmp_path: Path) -> Path:
    p = tmp_path / "autorun_spec.py"
    p.write_text(
        "@case('a')\ndef a(page):\n    pass\n\n@case('b')\ndef b(page):\n    pass\n",
        encoding="utf-8",
    )
    return p


# ─────────────────────── run_playwright ───────────────────────


class TestRunPlaywright:
    def test_typescript_spec_is_rejected_not_executed(self, tmp_out: Path) -> None:
        """TS はエクスポート専用。実行を試みず、理由つきで失敗させる。"""
        with patch("web.services.playwright_executor.subprocess.run") as run:
            result = run_playwright(Path("my.spec.ts"), tmp_out)

        run.assert_not_called()
        assert result["ok"] is False
        assert "エクスポート専用" in result["error"]
        assert (tmp_out / "playwright_report.json").exists()

    def test_blocked_when_no_browser_is_not_success(
        self, tmp_out: Path, spec_py: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Chrome / Edge が無い（ランナーが BLOCKED を書く）ときは成功扱いにせず伝搬する。"""
        blocked = json.dumps({"status": "BLOCKED", "reason": "browser unavailable", "tried": ["chrome"]})
        _write_raw_json_via_runner(monkeypatch, blocked)
        result = run_playwright(spec_py, tmp_out)

        assert result["ok"] is False
        assert result["blocked"] is True
        assert result["unavailable"] is True
        assert result["status"] == "BLOCKED"
        assert "Chrome" in result["error"]
        assert "npx" not in result["error"] and "install" not in result["error"].lower()

    def test_success_parses_json(
        self, tmp_out: Path, spec_py: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_raw_json_via_runner(monkeypatch, _VALID_JSON)
        result = run_playwright(spec_py, tmp_out)

        assert result["ok"] is True
        assert result["passed"] == 1
        assert result["failed"] == 0
        assert len(result["tests"]) == 1
        assert result["tests"][0]["title"] == "ログイン画面表示"

    def test_cmd_runs_python_runner_without_node_tools(
        self, tmp_out: Path, spec_py: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _write_raw_json_via_runner(monkeypatch, _VALID_JSON)
        run_playwright(spec_py, tmp_out)

        cmd = seen[0]
        assert cmd[1:3] == ["-m", "web.services.pw_runner"]
        assert cmd[cmd.index("--spec") + 1] == str(spec_py)
        assert "--egress-log" in cmd
        joined = " ".join(cmd)
        assert "npx" not in joined and "node" not in joined and "--config" not in cmd

    def test_headless_by_default(
        self, tmp_out: Path, spec_py: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """既定はヘッドレス。--headed を勝手に付けない（サーバ運用で画面が開かない）。"""
        seen = _write_raw_json_via_runner(monkeypatch, _VALID_JSON)
        run_playwright(spec_py, tmp_out)

        assert seen and "--headed" not in seen[0]

    def test_headed_option_adds_flag(
        self, tmp_out: Path, spec_py: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """headed=True のときだけブラウザ画面を出す（実行中の様子を人が見る用途）。"""
        seen = _write_raw_json_via_runner(monkeypatch, _VALID_JSON)
        run_playwright(spec_py, tmp_out, headed=True)

        assert seen and "--headed" in seen[0]

    def test_grep_is_passed_to_runner(
        self, tmp_out: Path, spec_py: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _write_raw_json_via_runner(monkeypatch, _VALID_JSON)
        run_playwright(spec_py, tmp_out, grep="ログイン")

        assert seen[0][seen[0].index("--grep") + 1] == "ログイン"

    @pytest.mark.parametrize(
        ("browser", "expected"), [("chrome", "chrome"), ("msedge", "msedge"), ("Edge", "msedge")]
    )
    def test_browser_selection_goes_via_env(
        self, tmp_out: Path, spec_py: Path, browser: str, expected: str
    ) -> None:
        captured_env: dict[str, str] = {}

        def fake_run(cmd: list[str], env: dict[str, str], **_: object) -> MagicMock:
            captured_env.update(env)
            return _mock_proc(_VALID_JSON)

        with patch("web.services.playwright_executor.subprocess.run", side_effect=fake_run):
            run_playwright(spec_py, tmp_out, browser=browser)

        assert captured_env["WEBSPEC2DOC_BROWSER"] == expected

    def test_success_writes_json_report(
        self, tmp_out: Path, spec_py: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_raw_json_via_runner(monkeypatch, _VALID_JSON)
        run_playwright(spec_py, tmp_out)

        saved = json.loads((tmp_out / "playwright_report.json").read_text())
        assert saved["passed"] == 1

    def test_success_writes_html_report_too(
        self, tmp_out: Path, spec_py: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """成功時にも日本語サマリ HTML が書かれる（従来は成功時に書かれていなかった）。"""
        _write_raw_json_via_runner(monkeypatch, _VALID_JSON)
        run_playwright(spec_py, tmp_out)

        html = (tmp_out / "playwright_report.html").read_text(encoding="utf-8")
        assert "ログイン画面表示" in html

    def test_stdout_fallback_when_raw_file_missing(self, tmp_out: Path, spec_py: Path) -> None:
        """raw json ファイルが書かれなかった場合、stdout パースにフォールバックする。"""
        with patch(
            "web.services.playwright_executor.subprocess.run",
            return_value=_mock_proc(_VALID_JSON),
        ):
            result = run_playwright(spec_py, tmp_out)

        assert result["passed"] == 1

    def test_failure_returncode_sets_ok_false(
        self, tmp_out: Path, spec_py: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_raw_json_via_runner(monkeypatch, _FAILED_JSON)
        result = run_playwright(spec_py, tmp_out)

        assert result["ok"] is False
        assert result["failed"] == 1

    def test_timeout_returns_error(self, tmp_out: Path, spec_py: Path) -> None:
        with patch(
            "web.services.playwright_executor.subprocess.run",
            side_effect=subprocess.TimeoutExpired("python", 300),
        ):
            result = run_playwright(spec_py, tmp_out)

        assert result["ok"] is False
        assert "中断" in result["error"]
        assert result["interrupted"] is True

    def test_timeout_with_progress_ndjson_recovers_partial_results(
        self, tmp_out: Path, spec_py: Path
    ) -> None:
        """全体タイムアウトで kill されても、進捗 NDJSON から実行済み分を回収する。"""

        def fake_run(cmd: list[str], **_: object) -> MagicMock:
            out = _out_dir(cmd)
            out.mkdir(parents=True, exist_ok=True)
            (out / "playwright_progress.ndjson").write_text(
                json.dumps({"event": "begin", "total": 2})
                + "\n"
                + json.dumps({"event": "test", "title": "a", "status": "passed", "duration": 50})
                + "\n",
                encoding="utf-8",
            )
            raise subprocess.TimeoutExpired(cmd, 600)

        with patch("web.services.playwright_executor.subprocess.run", side_effect=fake_run):
            result = run_playwright(spec_py, tmp_out)

        assert result["interrupted"] is True
        assert result["total"] == 1
        assert result["passed"] == 1
        assert result["expected_total"] == 2
        assert "2件中 1件" in result["error"]

    def test_timeout_without_progress_ndjson_reports_zero_honestly(
        self, tmp_out: Path, spec_py: Path
    ) -> None:
        """進捗ファイルが無い場合、部分結果0件を捏造せず正直にエラーだけ出す。"""
        with patch(
            "web.services.playwright_executor.subprocess.run",
            side_effect=subprocess.TimeoutExpired("python", 600),
        ):
            result = run_playwright(spec_py, tmp_out)

        assert result["total"] == 0
        assert result["ok"] is False
        assert result["error"]

    def test_generic_exception_returns_error(self, tmp_out: Path, spec_py: Path) -> None:
        with patch(
            "web.services.playwright_executor.subprocess.run",
            side_effect=OSError("broken pipe"),
        ):
            result = run_playwright(spec_py, tmp_out)

        assert result["ok"] is False
        assert "broken pipe" in result["error"]

    def test_invalid_json_stdout_is_reported_as_error_not_success(
        self, tmp_out: Path, spec_py: Path
    ) -> None:
        """パース不能な出力は ok=False・error 必須（無言で 0/0/0 成功にしない）。"""
        with patch(
            "web.services.playwright_executor.subprocess.run",
            return_value=_mock_proc("not-json", returncode=0),
        ):
            result = run_playwright(spec_py, tmp_out)

        assert result["ok"] is False
        assert result["error"]
        assert result["total"] == 0

    def test_explicit_timeout_sec_overrides_autoscale(self, tmp_out: Path, spec_py: Path) -> None:
        """timeout_sec を明示指定した場合、自動スケールより優先される。"""
        captured: dict[str, object] = {}

        def fake_run(cmd: list[str], timeout: int, **_: object) -> MagicMock:
            captured["timeout"] = timeout
            return _mock_proc(_VALID_JSON)

        with patch("web.services.playwright_executor.subprocess.run", side_effect=fake_run):
            run_playwright(spec_py, tmp_out, timeout_sec=42)

        assert captured["timeout"] == 42


class TestBrowserHelpers:
    def test_normalize_browser(self) -> None:
        assert normalize_browser("Google Chrome") == "chrome"
        assert normalize_browser("Microsoft Edge") == "msedge"
        assert normalize_browser("auto") == "auto"
        assert normalize_browser("") == ""

    def test_firefox_and_webkit_are_not_supported(self) -> None:
        assert normalize_browser("firefox") == ""
        assert normalize_browser("webkit") == ""
        ok, message = ensure_browser_available("firefox")
        assert ok is False and "Chrome" in message

    def test_missing_browser_guides_to_install_chrome_or_edge(self) -> None:
        from src.browser_detect import BrowserUnavailable

        with patch("src.browser_detect.detect_browser", side_effect=BrowserUnavailable("none")):
            ok, message = ensure_browser_available("auto")

        assert ok is False
        assert "Chrome" in message and "Edge" in message
        assert "npx" not in message and "playwright install" not in message


# ─────────────────────── _resolve_timeout_sec（自動スケール） ───────────────────────


class TestResolveTimeoutSec:
    def test_explicit_value_wins(self, tmp_path: Path) -> None:
        spec = tmp_path / "s_spec.py"
        spec.write_text("@case('a')\ndef a(page):\n    pass\n" * 100, encoding="utf-8")
        assert _resolve_timeout_sec(spec, 120, 999) == 999

    def test_scales_with_test_count(self, tmp_path: Path) -> None:
        """188件×120秒/件のような大規模実行が固定600秒で必ずkillされる不具合の修正。"""
        spec = tmp_path / "s_spec.py"
        spec.write_text("@case('a')\ndef a(page):\n    pass\n" * 188, encoding="utf-8")
        resolved = _resolve_timeout_sec(spec, 120, None)
        assert resolved >= 188 * 120

    def test_below_min_uses_minimum_600(self, tmp_path: Path) -> None:
        spec = tmp_path / "s_spec.py"
        spec.write_text("@case('a')\ndef a(page):\n    pass\n", encoding="utf-8")
        assert _resolve_timeout_sec(spec, 30, None) >= 600

    def test_respects_env_max(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WEBSPEC2DOC_PW_MAX_EXEC_SEC", "1000")
        spec = tmp_path / "s_spec.py"
        spec.write_text("@case('a')\ndef a(page):\n    pass\n" * 1000, encoding="utf-8")
        assert _resolve_timeout_sec(spec, 120, None) == 1000

    def test_no_tests_falls_back_to_min(self, tmp_path: Path) -> None:
        spec = tmp_path / "s_spec.py"
        spec.write_text("# empty\n", encoding="utf-8")
        assert _resolve_timeout_sec(spec, 30, None) == 600

    def test_missing_spec_file_falls_back_to_min(self, tmp_path: Path) -> None:
        assert _resolve_timeout_sec(tmp_path / "missing_spec.py", 30, None) == 600


class TestCountTestsInSpec:
    def test_counts_test_calls(self, tmp_path: Path) -> None:
        spec = tmp_path / "s_spec.py"
        spec.write_text(
            "@case('a')\ndef a(page):\n    pass\n@case('b')\ndef b(page):\n    pass\n# @case('c') はコメント\n",
            encoding="utf-8",
        )
        # 行頭の @case( だけを数える（コメント内は数えない・粗い見積り）
        assert _count_tests_in_spec(spec) == 2

    def test_missing_file_returns_zero(self, tmp_path: Path) -> None:
        assert _count_tests_in_spec(tmp_path / "missing_spec.py") == 0


# ─────────────────────── _parse_results ───────────────────────


class TestParseResults:
    def test_full_suite_structure(self) -> None:
        raw = json.loads(_VALID_JSON)
        result = _parse_results(raw, "", "", 0)

        assert result["passed"] == 1
        assert result["failed"] == 0
        assert result["total"] == 1
        assert result["tests"][0]["title"] == "ログイン画面表示"
        assert result["tests"][0]["status"] == "passed"
        assert result["tests"][0]["duration_ms"] == 120

    def test_failed_suite(self) -> None:
        raw = json.loads(_FAILED_JSON)
        result = _parse_results(raw, "", "", 1)

        assert result["failed"] == 1
        assert result["tests"][0]["error"] == "期待値と異なります"

    def test_empty_raw_falls_back_to_stats(self) -> None:
        raw = {
            "suites": [],
            "stats": {"expected": 3, "unexpected": 1, "skipped": 0, "total": 4, "duration": 500},
        }
        result = _parse_results(raw, "", "", 0)

        assert result["passed"] == 3
        assert result["failed"] == 1
        assert result["total"] == 4

    def test_stdout_truncated_to_4000(self) -> None:
        long_stdout = "x" * 5000
        raw = json.loads(_VALID_JSON)
        result = _parse_results(raw, long_stdout, "", 0)
        assert len(result["stdout"]) == 4000

    def test_stderr_truncated_to_2000(self) -> None:
        long_stderr = "e" * 3000
        raw = json.loads(_VALID_JSON)
        result = _parse_results(raw, "", long_stderr, 0)
        assert len(result["stderr"]) == 2000

    def test_parse_failure_is_never_success(self) -> None:
        """suites/stats が両方とも空（パース失敗）の場合、returncode に関わらず
        ok=False かつ error 必須（無言で成功扱いにしない・evidence-only）。

        旧実装は `_parse_results({}, "", "", 0)["ok"] is True` を仕様として固定していたが、
        これは「AutoRunで188件実行したのに結果が0/0/0でエラーも出ない」致命的なバグの直接原因だった。
        """
        result0 = _parse_results({}, "", "", 0)
        assert result0["ok"] is False
        assert result0["error"]
        assert result0["total"] == 0

        result1 = _parse_results({}, "", "", 1)
        assert result1["ok"] is False
        assert result1["error"]

    def test_parse_failure_includes_stderr_snippet(self) -> None:
        result = _parse_results({}, "", "Error: something broke", 1)
        assert "Error: something broke" in result["error"]


# ─────────────────────── _map_status ───────────────────────


class TestMapStatus:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("passed", "passed"),
            ("expected", "passed"),
            ("flaky", "passed"),  # リトライで合格 → passed扱い
            ("failed", "failed"),
            ("unexpected", "failed"),
            ("skipped", "skipped"),
            ("pending", "skipped"),
            ("", "unknown"),
        ],
    )
    def test_direct_status_mapping(self, raw: str, expected: str) -> None:
        assert _map_status(raw, []) == expected

    def test_falls_back_to_results_list(self) -> None:
        assert _map_status("", [{"status": "passed"}]) == "passed"
        assert _map_status("", [{"status": "failed"}]) == "failed"


# ─────────────────────── _first_error ───────────────────────


class TestFirstError:
    def test_returns_first_error_message(self) -> None:
        results = [{"errors": [{"message": "AssertionError: expected foo"}]}]
        assert _first_error(results) == "AssertionError: expected foo"

    def test_returns_value_if_no_message(self) -> None:
        results = [{"errors": [{"value": "Timeout 30000ms exceeded"}]}]
        assert _first_error(results) == "Timeout 30000ms exceeded"

    def test_empty_errors_returns_empty_string(self) -> None:
        assert _first_error([]) == ""
        assert _first_error([{"errors": []}]) == ""

    def test_long_error_truncated_to_400(self) -> None:
        results = [{"errors": [{"message": "x" * 500}]}]
        assert len(_first_error(results)) == 400


# ─────────────────────── _read_progress_ndjson ───────────────────────


class TestReadProgressNdjson:
    def test_missing_file_returns_none_and_empty(self, tmp_path: Path) -> None:
        total, tests = _read_progress_ndjson(tmp_path / "missing.ndjson")
        assert total is None
        assert tests == []

    def test_parses_begin_and_test_events(self, tmp_path: Path) -> None:
        path = tmp_path / "progress.ndjson"
        path.write_text(
            json.dumps({"event": "begin", "total": 3})
            + "\n"
            + json.dumps({"event": "test", "title": "a", "status": "passed", "duration": 10})
            + "\n"
            + json.dumps(
                {"event": "test", "title": "b", "status": "failed", "duration": 20, "error": "x"}
            )
            + "\n",
            encoding="utf-8",
        )
        total, tests = _read_progress_ndjson(path)
        assert total == 3
        assert len(tests) == 2
        assert tests[0]["status"] == "passed"
        assert tests[1]["status"] == "failed"
        assert tests[1]["error"] == "x"

    def test_corrupt_line_is_skipped_not_fatal(self, tmp_path: Path) -> None:
        path = tmp_path / "progress.ndjson"
        path.write_text(
            json.dumps({"event": "begin", "total": 1})
            + "\nnot-json-at-all\n"
            + json.dumps({"event": "test", "title": "a", "status": "passed", "duration": 5})
            + "\n",
            encoding="utf-8",
        )
        total, tests = _read_progress_ndjson(path)
        assert total == 1
        assert len(tests) == 1

    def test_empty_file_returns_none_total(self, tmp_path: Path) -> None:
        path = tmp_path / "progress.ndjson"
        path.write_text("", encoding="utf-8")
        total, tests = _read_progress_ndjson(path)
        assert total is None
        assert tests == []


# ─────────────────────── _build_html_report ───────────────────────


class TestBuildHtmlReport:
    def test_pass_badge(self) -> None:
        html = _build_html_report(
            {"ok": True, "passed": 5, "failed": 0, "skipped": 0, "total": 5, "tests": []}
        )
        assert "成功" in html

    def test_fail_badge(self) -> None:
        html = _build_html_report(
            {"ok": False, "passed": 0, "failed": 1, "skipped": 0, "total": 1, "tests": []}
        )
        assert "失敗" in html

    def test_interrupted_badge(self) -> None:
        html = _build_html_report(
            {
                "ok": False,
                "interrupted": True,
                "passed": 1,
                "failed": 0,
                "skipped": 0,
                "total": 1,
                "tests": [],
                "error": "中断しました",
            }
        )
        assert "中断" in html

    def test_error_section_rendered(self) -> None:
        html = _build_html_report({"ok": False, "error": "npx が見つかりません", "tests": []})
        assert "npx が見つかりません" in html

    def test_xss_escaped_in_title(self) -> None:
        tests = [
            {
                "title": "<script>alert(1)</script>",
                "status": "passed",
                "duration_ms": 0,
                "error": "",
            }
        ]
        html = _build_html_report({"ok": True, "tests": tests})
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_test_rows_rendered(self) -> None:
        tests = [{"title": "ログイン", "status": "passed", "duration_ms": 125_000, "error": ""}]
        html = _build_html_report({"ok": True, "tests": tests})
        assert "ログイン" in html
        assert "2分5秒" in html

    def test_no_dark_mode(self) -> None:
        """ダークモードは製品から削除済み（ライト固定）。OS 設定にも追従しないこと。"""
        html = _build_html_report({"ok": True, "tests": []})
        assert "prefers-color-scheme" not in html
        assert "data-theme" not in html

    def test_html_is_japanese(self) -> None:
        """ユーザー報告: 実行レポートが全て英語で読みにくい。"""
        html = _build_html_report(
            {"ok": True, "passed": 1, "failed": 0, "skipped": 0, "total": 1, "tests": []}
        )
        assert 'lang="ja"' in html
        assert "PASS" not in html.split("<body>")[0].split("<style>")[0]  # title に PASS が無い

    def test_build_html_report_is_japanese_light(self) -> None:
        """R3-03/04/05: 実行レポートは自己完結の日本語ライト基調レポート
        （外部scriptを読み込まない・ライト固定）。"""
        html = _build_html_report(
            {"ok": True, "passed": 1, "failed": 0, "skipped": 0, "total": 1, "tests": []}
        )
        assert 'lang="ja"' in html
        assert "成功" in html
        assert "<script src=" not in html

    def test_status_badges_use_emoji(self) -> None:
        tests = [
            {"title": "t1", "status": "passed", "duration_ms": 100, "error": ""},
            {"title": "t2", "status": "failed", "duration_ms": 100, "error": "boom"},
            {"title": "t3", "status": "skipped", "duration_ms": 0, "error": ""},
        ]
        html = _build_html_report({"ok": False, "tests": tests})
        assert "✅" in html
        assert "❌" in html
        assert "⏭" in html

    def test_error_detail_collapsed_and_escaped(self) -> None:
        tests = [
            {
                "title": "t1",
                "status": "failed",
                "duration_ms": 0,
                "error": "<script>alert(1)</script>",
            }
        ]
        html = _build_html_report({"ok": False, "tests": tests})
        assert "<details>" in html
        assert "エラー詳細" in html
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_intro_sentence_present(self) -> None:
        html = _build_html_report({"ok": True, "tests": []})
        assert "❌の行から確認してください" in html

    def test_total_duration_shown_as_minutes_seconds(self) -> None:
        html = _build_html_report({"ok": True, "tests": [], "duration_ms": 65_000})
        assert "1分5秒" in html


# ─────────────────────── _python_playwright_version ───────────────────────


class TestPythonPlaywrightVersion:
    def test_returns_installed_version(self) -> None:
        # requirements.txt の固定版と実環境が一致する
        assert _python_playwright_version() == "1.61.0"

    def test_returns_empty_when_package_missing(self) -> None:
        from importlib.metadata import PackageNotFoundError

        with patch(
            "web.services.playwright_executor._pkg_version",
            side_effect=PackageNotFoundError,
        ):
            assert _python_playwright_version() == ""


# ─────────────────────── _unavailable_result / _error_result ───────────────────────


class TestResultHelpers:
    def test_unavailable_result_structure(self, tmp_path: Path) -> None:
        result = _unavailable_result("理由", tmp_path / "r.json", tmp_path / "r.html")
        assert result["unavailable"] is True
        assert result["ok"] is False
        assert result["error"] == "理由"
        assert (tmp_path / "r.json").exists()
        assert (tmp_path / "r.html").exists()

    def test_error_result_structure(self, tmp_path: Path) -> None:
        result = _error_result("タイムアウト", tmp_path / "r.json", tmp_path / "r.html")
        assert result["ok"] is False
        assert result["error"] == "タイムアウト"
        assert "unavailable" not in result


# ─────────────────────── _parse_stdout_json ───────────────────────


class TestParseStdoutJson:
    def test_pure_json(self) -> None:
        data = {"suites": [], "stats": {}}
        assert _parse_stdout_json(json.dumps(data)) == data

    def test_json_with_preamble(self) -> None:
        preamble = "Warning: some npm message\n"
        data = {"suites": [], "stats": {"expected": 2}}
        result = _parse_stdout_json(preamble + json.dumps(data))
        assert result["stats"]["expected"] == 2

    def test_empty_string_returns_empty(self) -> None:
        assert _parse_stdout_json("") == {}

    def test_no_json_returns_empty(self) -> None:
        assert _parse_stdout_json("no json here") == {}

    def test_invalid_json_after_brace_returns_empty(self) -> None:
        assert _parse_stdout_json("{broken json") == {}


class TestPerTestTimeoutParam:
    def test_per_test_timeout_passed_to_runner(
        self, tmp_out: Path, spec_py: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """per_test_timeout_sec がランナーの --per-test-timeout として渡る。"""
        seen = _write_raw_json_via_runner(monkeypatch, _VALID_JSON)
        run_playwright(spec_py, tmp_out, per_test_timeout_sec=45)

        assert seen[0][seen[0].index("--per-test-timeout") + 1] == "45"

    def test_default_per_test_timeout_is_30s(
        self, tmp_out: Path, spec_py: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _write_raw_json_via_runner(monkeypatch, _VALID_JSON)
        run_playwright(spec_py, tmp_out)

        assert seen[0][seen[0].index("--per-test-timeout") + 1] == "30"


# ─────────────────────── _spawn_and_wait ───────────────────────


class TestSpawnAndWait:
    def test_without_on_proc_uses_subprocess_run(self) -> None:
        from web.services.playwright_executor import _spawn_and_wait

        with patch(
            "web.services.playwright_executor.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        ) as mock_run:
            _spawn_and_wait(["true"], 5, {}, None)
        mock_run.assert_called_once()

    def test_on_proc_receives_popen_and_result_matches(self) -> None:
        import os
        import sys

        from web.services.playwright_executor import _spawn_and_wait

        seen: list = []
        cp = _spawn_and_wait(
            [sys.executable, "-c", "print('hi')"], 30, os.environ.copy(), seen.append
        )
        assert cp.returncode == 0
        assert "hi" in cp.stdout
        assert seen and seen[0].pid > 0
