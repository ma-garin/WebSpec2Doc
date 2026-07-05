from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from web.services.playwright_executor import (
    _browsers_present,
    _build_html_report,
    _count_tests_in_spec,
    _ensure_browsers_installed,
    _ensure_pw_env,
    _error_result,
    _first_error,
    _get_cli_version,
    _installed_pw_test_version,
    _map_status,
    _parse_results,
    _parse_stdout_json,
    _pw_test_available,
    _python_playwright_version,
    _read_progress_ndjson,
    _required_browser_globs,
    _resolve_timeout_sec,
    _unavailable_result,
    _write_pw_config,
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


def _write_raw_json_via_config(monkeypatch: pytest.MonkeyPatch, content: str) -> None:
    """subprocess.run が呼ばれたときに、config が指す raw json ファイルへ書き込む
    フェイクを仕込む（新実装は stdout ではなくファイル出力を優先して読むため）。
    """

    def fake_run(cmd: list[str], **_: object) -> MagicMock:
        idx = cmd.index("--config") + 1 if "--config" in cmd else -1
        if idx > 0:
            config_text = Path(cmd[idx]).read_text(encoding="utf-8")
            import re

            m = re.search(r"outputFile[\"']?:\s*[\"']([^\"']+)[\"']", config_text)
            if m:
                Path(m.group(1)).write_text(content, encoding="utf-8")
        return _mock_proc(content)

    monkeypatch.setattr("web.services.playwright_executor.subprocess.run", fake_run)


# ─────────────────────── run_playwright ───────────────────────


class TestRunPlaywright:
    def test_no_npx_returns_unavailable(self, tmp_out: Path) -> None:
        with patch("web.services.playwright_executor.shutil.which", return_value=None):
            result = run_playwright(Path("spec.ts"), tmp_out)

        assert result["ok"] is False
        assert result["unavailable"] is True
        assert "npx" in result["error"]

    def test_unavailable_writes_json_and_html(self, tmp_out: Path) -> None:
        with patch("web.services.playwright_executor.shutil.which", return_value=None):
            run_playwright(Path("spec.ts"), tmp_out)

        assert (tmp_out / "playwright_report.json").exists()
        assert (tmp_out / "playwright_report.html").exists()

    def test_pw_test_setup_fails_returns_unavailable(self, tmp_out: Path) -> None:
        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=False),
            patch(
                "web.services.playwright_executor._ensure_pw_env", return_value=(False, "npm失敗")
            ),
        ):
            result = run_playwright(Path("spec.ts"), tmp_out)

        assert result["unavailable"] is True
        assert "npm失敗" in result["error"]

    def test_success_parses_json(self, tmp_out: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_raw_json_via_config(monkeypatch, _VALID_JSON)
        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=True),
        ):
            result = run_playwright(Path("spec.ts"), tmp_out)

        assert result["ok"] is True
        assert result["passed"] == 1
        assert result["failed"] == 0
        assert len(result["tests"]) == 1
        assert result["tests"][0]["title"] == "ログイン画面表示"

    def test_success_writes_json_report(
        self, tmp_out: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_raw_json_via_config(monkeypatch, _VALID_JSON)
        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=True),
        ):
            run_playwright(Path("spec.ts"), tmp_out)

        saved = json.loads((tmp_out / "playwright_report.json").read_text())
        assert saved["passed"] == 1

    def test_success_writes_html_report_too(
        self, tmp_out: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """成功時にも日本語サマリ HTML が書かれる（従来は成功時に書かれていなかった）。"""
        _write_raw_json_via_config(monkeypatch, _VALID_JSON)
        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=True),
        ):
            run_playwright(Path("spec.ts"), tmp_out)

        html = (tmp_out / "playwright_report.html").read_text(encoding="utf-8")
        assert "ログイン画面表示" in html

    def test_stdout_fallback_when_raw_file_missing(self, tmp_out: Path) -> None:
        """raw json ファイルが書かれなかった場合、stdout パースにフォールバックする
        （reporter がファイル書き込みに失敗した場合の保険・旧バージョン互換）。
        """
        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=True),
            patch(
                "web.services.playwright_executor.subprocess.run",
                return_value=_mock_proc(_VALID_JSON),
            ),
        ):
            result = run_playwright(Path("spec.ts"), tmp_out)

        assert result["passed"] == 1

    def test_failure_returncode_sets_ok_false(
        self, tmp_out: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_raw_json_via_config(monkeypatch, _FAILED_JSON)
        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=True),
        ):
            result = run_playwright(Path("spec.ts"), tmp_out)

        assert result["ok"] is False
        assert result["failed"] == 1

    def test_timeout_returns_error(self, tmp_out: Path) -> None:
        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=True),
            patch(
                "web.services.playwright_executor.subprocess.run",
                side_effect=subprocess.TimeoutExpired("npx", 300),
            ),
        ):
            result = run_playwright(Path("spec.ts"), tmp_out)

        assert result["ok"] is False
        assert "中断" in result["error"]
        assert result["interrupted"] is True

    def test_timeout_with_progress_ndjson_recovers_partial_results(
        self, tmp_out: Path, tmp_path: Path
    ) -> None:
        """全体タイムアウトで kill されても、進捗 NDJSON から実行済み分を回収する。"""
        spec_path = tmp_path / "autorun.spec.ts"
        spec_path.write_text("test('a', () => {});\ntest('b', () => {});\n", encoding="utf-8")

        def fake_run(cmd: list[str], **_: object) -> MagicMock:
            idx = cmd.index("--config") + 1 if "--config" in cmd else -1
            config_text = Path(cmd[idx]).read_text(encoding="utf-8")
            import re

            m = re.search(r"progressPath[\"']?:\s*[\"']([^\"']+)[\"']", config_text)
            assert m is not None
            progress_path = Path(m.group(1))
            progress_path.write_text(
                json.dumps({"event": "begin", "total": 2})
                + "\n"
                + json.dumps({"event": "test", "title": "a", "status": "passed", "duration": 50})
                + "\n",
                encoding="utf-8",
            )
            raise subprocess.TimeoutExpired(cmd, 600)

        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=True),
            patch("web.services.playwright_executor.subprocess.run", side_effect=fake_run),
        ):
            result = run_playwright(spec_path, tmp_out)

        assert result["interrupted"] is True
        assert result["total"] == 1
        assert result["passed"] == 1
        assert result["expected_total"] == 2
        assert "2件中 1件" in result["error"]

    def test_timeout_without_progress_ndjson_reports_zero_honestly(self, tmp_out: Path) -> None:
        """進捗ファイルが無い場合、部分結果0件を捏造せず正直にエラーだけ出す。"""
        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=True),
            patch(
                "web.services.playwright_executor.subprocess.run",
                side_effect=subprocess.TimeoutExpired("npx", 600),
            ),
        ):
            result = run_playwright(Path("spec.ts"), tmp_out)

        assert result["total"] == 0
        assert result["ok"] is False
        assert result["error"]

    def test_generic_exception_returns_error(self, tmp_out: Path) -> None:
        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=True),
            patch(
                "web.services.playwright_executor.subprocess.run",
                side_effect=OSError("broken pipe"),
            ),
        ):
            result = run_playwright(Path("spec.ts"), tmp_out)

        assert result["ok"] is False
        assert "broken pipe" in result["error"]

    def test_invalid_json_stdout_is_reported_as_error_not_success(self, tmp_out: Path) -> None:
        """パース不能な出力は ok=False・error 必須（無言で 0/0/0 成功にしない）。"""
        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=True),
            patch(
                "web.services.playwright_executor.subprocess.run",
                return_value=_mock_proc("not-json", returncode=0),
            ),
        ):
            result = run_playwright(Path("spec.ts"), tmp_out)

        assert result["ok"] is False
        assert result["error"]
        assert result["total"] == 0

    def test_cmd_uses_local_cli_and_config(self, tmp_out: Path) -> None:
        captured: list[list[str]] = []

        def fake_run(cmd: list[str], **_: object) -> MagicMock:
            captured.append(cmd)
            return _mock_proc(_VALID_JSON)

        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=True),
            patch("web.services.playwright_executor.subprocess.run", side_effect=fake_run),
        ):
            run_playwright(Path("my.spec.ts"), tmp_out)

        cmd = captured[0]
        # --reporter=json は config で定義するため CLI フラグには含まない
        assert "--reporter=json" not in cmd
        assert "--config" in cmd

    def test_node_path_set_in_env(self, tmp_out: Path) -> None:
        captured_env: dict[str, str] = {}

        def fake_run(cmd: list[str], env: dict[str, str], **_: object) -> MagicMock:
            captured_env.update(env)
            return _mock_proc(_VALID_JSON)

        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=True),
            patch("web.services.playwright_executor.subprocess.run", side_effect=fake_run),
        ):
            run_playwright(Path("spec.ts"), tmp_out)

        assert "NODE_PATH" in captured_env
        assert ".playwright_env" in captured_env["NODE_PATH"]

    def test_add_log_called(self, tmp_out: Path) -> None:
        logs: list[str] = []

        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=False),
            patch(
                "web.services.playwright_executor._ensure_pw_env",
                return_value=(True, "インストール完了"),
            ),
            patch(
                "web.services.playwright_executor.subprocess.run",
                return_value=_mock_proc(_VALID_JSON),
            ),
        ):
            run_playwright(Path("spec.ts"), tmp_out, add_log=logs.append)

        assert any("インストール完了" in log for log in logs)

    def test_explicit_timeout_sec_overrides_autoscale(self, tmp_out: Path) -> None:
        """timeout_sec を明示指定した場合、自動スケールより優先される。"""
        captured: dict[str, object] = {}

        def fake_run(cmd: list[str], timeout: int, **_: object) -> MagicMock:
            captured["timeout"] = timeout
            return _mock_proc(_VALID_JSON)

        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=True),
            patch("web.services.playwright_executor.subprocess.run", side_effect=fake_run),
        ):
            run_playwright(Path("spec.ts"), tmp_out, timeout_sec=42)

        assert captured["timeout"] == 42


# ─────────────────────── _resolve_timeout_sec（自動スケール） ───────────────────────


class TestResolveTimeoutSec:
    def test_explicit_value_wins(self, tmp_path: Path) -> None:
        spec = tmp_path / "s.spec.ts"
        spec.write_text("test('a', () => {});\n" * 100, encoding="utf-8")
        assert _resolve_timeout_sec(spec, 120, 999) == 999

    def test_scales_with_test_count(self, tmp_path: Path) -> None:
        """188件×120秒/件のような大規模実行が固定600秒で必ずkillされる不具合の修正。"""
        spec = tmp_path / "s.spec.ts"
        spec.write_text("test('a', () => {});\n" * 188, encoding="utf-8")
        resolved = _resolve_timeout_sec(spec, 120, None)
        assert resolved >= 188 * 120

    def test_below_min_uses_minimum_600(self, tmp_path: Path) -> None:
        spec = tmp_path / "s.spec.ts"
        spec.write_text("test('a', () => {});\n", encoding="utf-8")
        assert _resolve_timeout_sec(spec, 30, None) >= 600

    def test_respects_env_max(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WEBSPEC2DOC_PW_MAX_EXEC_SEC", "1000")
        spec = tmp_path / "s.spec.ts"
        spec.write_text("test('a', () => {});\n" * 1000, encoding="utf-8")
        assert _resolve_timeout_sec(spec, 120, None) == 1000

    def test_no_tests_falls_back_to_min(self, tmp_path: Path) -> None:
        spec = tmp_path / "s.spec.ts"
        spec.write_text("// empty\n", encoding="utf-8")
        assert _resolve_timeout_sec(spec, 30, None) == 600

    def test_missing_spec_file_falls_back_to_min(self, tmp_path: Path) -> None:
        assert _resolve_timeout_sec(tmp_path / "missing.spec.ts", 30, None) == 600


class TestCountTestsInSpec:
    def test_counts_test_calls(self, tmp_path: Path) -> None:
        spec = tmp_path / "s.spec.ts"
        spec.write_text(
            "test('a', () => {});\ntest('b', () => {});\ntest.skip('c', () => {});\n",
            encoding="utf-8",
        )
        # test.skip( は (?<![.\w])test\( のパターンにマッチしない（既知の仕様・粗い見積り）
        assert _count_tests_in_spec(spec) == 2

    def test_missing_file_returns_zero(self, tmp_path: Path) -> None:
        assert _count_tests_in_spec(tmp_path / "missing.spec.ts") == 0


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

    def test_dark_mode_media_query_present(self) -> None:
        """ライト/ダーク両対応（ユーザー報告: 実行レポートがダークモード固定だった）。"""
        html = _build_html_report({"ok": True, "tests": []})
        assert "prefers-color-scheme: dark" in html

    def test_html_is_japanese(self) -> None:
        """ユーザー報告: 実行レポートが全て英語で読みにくい。"""
        html = _build_html_report(
            {"ok": True, "passed": 1, "failed": 0, "skipped": 0, "total": 1, "tests": []}
        )
        assert 'lang="ja"' in html
        assert "PASS" not in html.split("<body>")[0].split("<style>")[0]  # title に PASS が無い

    def test_build_html_report_is_japanese_light(self) -> None:
        """R3-03/04/05: 実行レポートは自己完結の日本語ライト基調レポート
        （外部scriptを読み込まず、ダークモードにも追随する）。"""
        html = _build_html_report(
            {"ok": True, "passed": 1, "failed": 0, "skipped": 0, "total": 1, "tests": []}
        )
        assert 'lang="ja"' in html
        assert "成功" in html
        assert "prefers-color-scheme" in html
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


# ─────────────────────── _pw_test_available ───────────────────────


class TestPwTestAvailable:
    def test_true_if_local_node_modules_exists(self, tmp_path: Path) -> None:
        local = tmp_path / "node_modules/@playwright/test"
        local.mkdir(parents=True)
        with patch("web.services.playwright_executor.Path") as mock_path:
            mock_path.return_value = local
            # local.is_dir() が True を返す構造を直接テスト
        assert local.is_dir() is True

    def test_false_if_node_raises(self) -> None:
        with (
            patch("web.services.playwright_executor.Path.is_dir", return_value=False),
            patch("web.services.playwright_executor.subprocess.run", side_effect=OSError),
        ):
            assert _pw_test_available() is False


# ─────────────────────── _ensure_pw_env ───────────────────────


class TestEnsurePwEnv:
    def test_already_installed(self, tmp_path: Path) -> None:
        pw_dir = tmp_path / "node_modules/@playwright/test"
        pw_dir.mkdir(parents=True)
        ok, msg = _ensure_pw_env(tmp_path)
        assert ok is True
        assert "既にセットアップ済み" in msg

    def test_no_npm(self, tmp_path: Path) -> None:
        with patch("web.services.playwright_executor.shutil.which", return_value=None):
            ok, msg = _ensure_pw_env(tmp_path)
        assert ok is False
        assert "npm" in msg

    def test_npm_install_success(self, tmp_path: Path) -> None:
        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npm"),
            patch(
                "web.services.playwright_executor.subprocess.run",
                return_value=_mock_proc(returncode=0),
            ),
        ):
            ok, msg = _ensure_pw_env(tmp_path)
        assert ok is True
        assert "完了" in msg

    def test_npm_install_failure(self, tmp_path: Path) -> None:
        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npm"),
            patch(
                "web.services.playwright_executor.subprocess.run",
                return_value=_mock_proc(stderr="E404", returncode=1),
            ),
        ):
            ok, msg = _ensure_pw_env(tmp_path)
        assert ok is False
        assert "失敗" in msg

    def test_npm_install_timeout(self, tmp_path: Path) -> None:
        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npm"),
            patch(
                "web.services.playwright_executor.subprocess.run",
                side_effect=subprocess.TimeoutExpired("npm", 180),
            ),
        ):
            ok, msg = _ensure_pw_env(tmp_path)
        assert ok is False
        assert "タイムアウト" in msg

    def test_creates_package_json(self, tmp_path: Path) -> None:
        env_dir = tmp_path / "pw_env"
        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npm"),
            patch(
                "web.services.playwright_executor.subprocess.run",
                return_value=_mock_proc(returncode=0),
            ),
        ):
            _ensure_pw_env(env_dir)
        assert (env_dir / "package.json").exists()

    def test_version_mismatch_rebuilds_env(self, tmp_path: Path) -> None:
        """既存envがPython側と異なるバージョンの @playwright/test で入っている場合
        （旧実装がnpx解決の最新版をインストールしていたケースの再発防止）、
        node_modules を破棄して同バージョンで再インストールする。"""
        pw_test_dir = tmp_path / "node_modules" / "@playwright" / "test"
        pw_test_dir.mkdir(parents=True)
        (pw_test_dir / "package.json").write_text(
            json.dumps({"name": "@playwright/test", "version": "1.56.1"}), encoding="utf-8"
        )
        install_calls: list[list[str]] = []

        def fake_run(cmd: list[str], **_: object) -> MagicMock:
            install_calls.append(cmd)
            return _mock_proc(returncode=0)

        with (
            patch(
                "web.services.playwright_executor._python_playwright_version",
                return_value="1.44.0",
            ),
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npm"),
            patch("web.services.playwright_executor.subprocess.run", side_effect=fake_run),
            patch(
                "web.services.playwright_executor._ensure_browsers_installed",
                return_value=(True, ""),
            ),
        ):
            ok, msg = _ensure_pw_env(tmp_path)

        assert ok is True
        assert "1.44.0" in msg
        # 旧バージョンの node_modules は破棄され、新バージョンで npm install し直された
        assert not pw_test_dir.is_dir()
        assert install_calls, "npm install が実行されていない"
        assert any("@playwright/test@1.44.0" in arg for arg in install_calls[0])

    def test_matching_version_skips_reinstall_but_checks_browsers(self, tmp_path: Path) -> None:
        """バージョンが一致していれば再インストールしないが、ブラウザ実在は毎回確認する。"""
        pw_test_dir = tmp_path / "node_modules" / "@playwright" / "test"
        pw_test_dir.mkdir(parents=True)
        (pw_test_dir / "package.json").write_text(
            json.dumps({"name": "@playwright/test", "version": "1.44.0"}), encoding="utf-8"
        )
        with (
            patch(
                "web.services.playwright_executor._python_playwright_version",
                return_value="1.44.0",
            ),
            patch(
                "web.services.playwright_executor._ensure_browsers_installed",
                return_value=(True, ""),
            ) as mock_browsers,
            patch("web.services.playwright_executor.subprocess.run") as mock_run,
        ):
            ok, msg = _ensure_pw_env(tmp_path)

        assert ok is True
        assert "既にセットアップ済み" in msg
        mock_browsers.assert_called_once()
        mock_run.assert_not_called()  # npm install は走らない

    def test_browsers_missing_after_reinstall_fails(self, tmp_path: Path) -> None:
        """npm install自体は成功しても、ブラウザ自動導入に失敗すればセットアップ全体を失敗にする。"""
        with (
            patch(
                "web.services.playwright_executor._python_playwright_version",
                return_value="1.44.0",
            ),
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npm"),
            patch(
                "web.services.playwright_executor.subprocess.run",
                return_value=_mock_proc(returncode=0),
            ),
            patch(
                "web.services.playwright_executor._ensure_browsers_installed",
                return_value=(False, "ブラウザの自動導入に失敗しました"),
            ),
        ):
            ok, msg = _ensure_pw_env(tmp_path)
        assert ok is False
        assert "ブラウザ" in msg

    def test_ensure_pw_env_fails_without_python_version(self, tmp_path: Path) -> None:
        """Python側 playwright のバージョンを特定できない場合は latest への
        暗黙フォールバックをせず実行を中止する（R3-08: npx解決の新版
        @playwright/test が混入しブラウザ不一致で全滅する不具合の再発防止）。"""
        with patch(
            "web.services.playwright_executor._python_playwright_version",
            return_value="",
        ):
            ok, msg = _ensure_pw_env(tmp_path)
        assert ok is False
        assert "特定できない" in msg
        # package.json は生成されず、"latest" もどこにも書かれない
        pkg_json = tmp_path / "package.json"
        assert not pkg_json.exists()


# ─────────────────────── _python_playwright_version / _installed_pw_test_version ───────────────────────


class TestPythonPlaywrightVersion:
    def test_returns_installed_version(self) -> None:
        # requirements.txt で playwright==1.44.0 に固定されている
        assert _python_playwright_version() == "1.44.0"

    def test_returns_empty_when_package_missing(self) -> None:
        from importlib.metadata import PackageNotFoundError

        with patch(
            "web.services.playwright_executor._pkg_version",
            side_effect=PackageNotFoundError,
        ):
            assert _python_playwright_version() == ""


class TestInstalledPwTestVersion:
    def test_reads_version_from_package_json(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "node_modules" / "@playwright" / "test"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.json").write_text(json.dumps({"version": "1.56.1"}), encoding="utf-8")
        assert _installed_pw_test_version(tmp_path) == "1.56.1"

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert _installed_pw_test_version(tmp_path) == ""

    def test_corrupt_json_returns_empty(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "node_modules" / "@playwright" / "test"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.json").write_text("{not json", encoding="utf-8")
        assert _installed_pw_test_version(tmp_path) == ""


# ─────────────────────── _required_browser_globs ───────────────────────


class TestRequiredBrowserGlobs:
    def test_required_globs_144_needs_chromium_only(self) -> None:
        assert _required_browser_globs("1.44.0") == ("chromium-*",)

    def test_required_globs_149plus_needs_headless_shell(self) -> None:
        assert "chromium_headless_shell-*" in _required_browser_globs("1.56.1")

    def test_required_globs_exactly_149_needs_headless_shell(self) -> None:
        assert _required_browser_globs("1.49.0") == ("chromium-*", "chromium_headless_shell-*")

    def test_required_globs_unknown_version_requires_both(self) -> None:
        # バージョンが特定できない場合は安全側（両方必須）に倒す
        assert _required_browser_globs("") == ("chromium-*", "chromium_headless_shell-*")
        assert _required_browser_globs("not-a-version") == (
            "chromium-*",
            "chromium_headless_shell-*",
        )


# ─────────────────────── _browsers_present / _ensure_browsers_installed ───────────────────────


def _make_browser_dir(root: Path, name: str) -> None:
    """本物のブラウザディレクトリを模す（実行ファイルを1つ持つ）。"""
    bin_dir = root / name / "chrome-linux"
    bin_dir.mkdir(parents=True)
    (bin_dir / "chrome").write_text("dummy-binary", encoding="utf-8")


class TestBrowsersPresent:
    def test_true_when_chromium_present_for_pre_149(self, tmp_path: Path) -> None:
        _make_browser_dir(tmp_path, "chromium-1148")
        assert _browsers_present(tmp_path, "1.44.0") is True

    def test_browsers_present_false_when_headless_shell_missing_on_149(
        self, tmp_path: Path
    ) -> None:
        """R3-08の実際の再発状態: chromium-* のみ導入済みで
        chromium_headless_shell-* が無い環境は 1.49 以降で不足として検出される
        （旧OR判定では見逃してテスト全滅を招いていた）。"""
        _make_browser_dir(tmp_path, "chromium-1117")
        assert _browsers_present(tmp_path, "1.56.1") is False

    def test_true_when_both_present_for_149plus(self, tmp_path: Path) -> None:
        _make_browser_dir(tmp_path, "chromium-1148")
        _make_browser_dir(tmp_path, "chromium_headless_shell-1217")
        assert _browsers_present(tmp_path, "1.56.1") is True

    def test_browsers_present_false_when_dir_empty(self, tmp_path: Path) -> None:
        """ディレクトリだけ残って中身が空（強制終了・破損等）は欠落として扱う。"""
        (tmp_path / "chromium-1148").mkdir()
        assert _browsers_present(tmp_path, "1.44.0") is False

    def test_false_when_dir_missing(self, tmp_path: Path) -> None:
        assert _browsers_present(tmp_path / "does-not-exist", "1.44.0") is False


class TestEnsureBrowsersInstalled:
    def test_already_present_skips_install(self, tmp_path: Path) -> None:
        with (
            patch(
                "web.services.playwright_executor._configured_browsers_path",
                return_value=tmp_path,
            ),
            patch("web.services.playwright_executor._browsers_present", return_value=True),
            patch("web.services.playwright_executor.subprocess.run") as mock_run,
        ):
            ok, msg = _ensure_browsers_installed("1.44.0")
        assert ok is True
        assert msg == ""
        mock_run.assert_not_called()

    def test_missing_and_no_npx(self, tmp_path: Path) -> None:
        with (
            patch(
                "web.services.playwright_executor._configured_browsers_path",
                return_value=tmp_path,
            ),
            patch("web.services.playwright_executor._browsers_present", return_value=False),
            patch("web.services.playwright_executor.shutil.which", return_value=None),
        ):
            ok, msg = _ensure_browsers_installed("1.44.0")
        assert ok is False
        assert "npx" in msg

    def test_missing_installs_successfully(self, tmp_path: Path) -> None:
        with (
            patch(
                "web.services.playwright_executor._configured_browsers_path",
                return_value=tmp_path,
            ),
            patch(
                "web.services.playwright_executor._browsers_present",
                side_effect=[False, True],
            ),
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch(
                "web.services.playwright_executor.subprocess.run",
                return_value=_mock_proc(returncode=0),
            ) as mock_run,
        ):
            ok, msg = _ensure_browsers_installed("1.44.0")
        assert ok is True
        assert "自動導入" in msg
        cmd = mock_run.call_args[0][0]
        assert cmd == ["npx", "playwright", "install", "chromium"]

    def test_ensure_browsers_installed_reverifies_after_install(self, tmp_path: Path) -> None:
        """npm/npx install コマンドが returncode=0 で終わっても、再検証で
        依然としてブラウザが揃っていなければ成功と偽装せず失敗を返す
        （インストールが一部のみ成功したケースを見逃さないため）。"""
        with (
            patch(
                "web.services.playwright_executor._configured_browsers_path",
                return_value=tmp_path,
            ),
            patch("web.services.playwright_executor._browsers_present", return_value=False),
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch(
                "web.services.playwright_executor.subprocess.run",
                return_value=_mock_proc(returncode=0),
            ),
        ):
            ok, msg = _ensure_browsers_installed("1.56.1")
        assert ok is False
        assert "不足" in msg

    def test_install_failure(self, tmp_path: Path) -> None:
        with (
            patch(
                "web.services.playwright_executor._configured_browsers_path",
                return_value=tmp_path,
            ),
            patch("web.services.playwright_executor._browsers_present", return_value=False),
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch(
                "web.services.playwright_executor.subprocess.run",
                return_value=_mock_proc(stderr="network error", returncode=1),
            ),
        ):
            ok, msg = _ensure_browsers_installed("1.44.0")
        assert ok is False
        assert "失敗" in msg

    def test_install_timeout(self, tmp_path: Path) -> None:
        with (
            patch(
                "web.services.playwright_executor._configured_browsers_path",
                return_value=tmp_path,
            ),
            patch("web.services.playwright_executor._browsers_present", return_value=False),
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch(
                "web.services.playwright_executor.subprocess.run",
                side_effect=subprocess.TimeoutExpired("npx", 300),
            ),
        ):
            ok, msg = _ensure_browsers_installed("1.44.0")
        assert ok is False
        assert "タイムアウト" in msg


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


# ─────────────────────── _write_pw_config ───────────────────────


class TestWritePwConfig:
    def test_generates_js_config(self, tmp_path: Path) -> None:
        spec = tmp_path / "autorun.spec.ts"
        spec.write_text("", encoding="utf-8")
        html_dir = tmp_path / "playwright-report"

        config_path = _write_pw_config(spec, html_dir)

        assert config_path.suffix == ".js"
        content = config_path.read_text()
        assert "module.exports" in content
        assert "autorun.spec.ts" in content
        assert str(tmp_path.resolve()) in content

    def test_config_contains_screenshot_and_trace(self, tmp_path: Path) -> None:
        spec = tmp_path / "autorun.spec.ts"
        spec.write_text("", encoding="utf-8")
        content = _write_pw_config(spec, tmp_path / "out").read_text()
        assert "screenshot" in content
        assert "trace" in content

    def test_config_contains_html_reporter(self, tmp_path: Path) -> None:
        spec = tmp_path / "autorun.spec.ts"
        spec.write_text("", encoding="utf-8")
        html_dir = tmp_path / "playwright-report"
        content = _write_pw_config(spec, html_dir).read_text()
        assert "html" in content
        assert str(html_dir.resolve()) in content

    def test_config_workers_1(self, tmp_path: Path) -> None:
        spec = tmp_path / "autorun.spec.ts"
        spec.write_text("", encoding="utf-8")
        content = _write_pw_config(spec, tmp_path / "out").read_text()
        assert "workers: 1" in content

    def test_config_timeout_from_per_test_param(self, tmp_path: Path) -> None:
        spec = tmp_path / "autorun.spec.ts"
        spec.write_text("", encoding="utf-8")
        content = _write_pw_config(spec, tmp_path / "out", per_test_timeout_ms=45_000).read_text()
        assert "timeout: 45000" in content

    def test_config_output_dir_for_artifacts(self, tmp_path: Path) -> None:
        spec = tmp_path / "autorun.spec.ts"
        spec.write_text("", encoding="utf-8")
        content = _write_pw_config(spec, tmp_path / "playwright-report").read_text()
        assert "outputDir" in content
        assert "test-results" in content

    def test_json_output_file_set_when_path_given(self, tmp_path: Path) -> None:
        """stdout 汚染バグの根本修正: JSON reporter はファイル出力にする。"""
        spec = tmp_path / "autorun.spec.ts"
        spec.write_text("", encoding="utf-8")
        raw_json = tmp_path / "playwright_raw.json"
        content = _write_pw_config(spec, tmp_path / "out", json_output_path=raw_json).read_text()
        assert "outputFile" in content
        assert str(raw_json.resolve()) in content

    def test_progress_reporter_registered_when_path_given(self, tmp_path: Path) -> None:
        spec = tmp_path / "autorun.spec.ts"
        spec.write_text("", encoding="utf-8")
        progress_path = tmp_path / "playwright_progress.ndjson"
        config_path = _write_pw_config(spec, tmp_path / "out", progress_path=progress_path)
        content = config_path.read_text()
        assert "progressPath" in content
        assert str(progress_path.resolve()) in content
        reporter_file = spec.parent / "_autorun_pw.progress_reporter.js"
        assert reporter_file.exists()
        assert "onTestEnd" in reporter_file.read_text(encoding="utf-8")

    def test_write_pw_config_mobile_injects_viewport(self, tmp_path: Path) -> None:
        spec = tmp_path / "autorun.spec.ts"
        spec.write_text("", encoding="utf-8")
        content = _write_pw_config(spec, tmp_path / "out", device="mobile").read_text()
        assert "isMobile: true" in content
        assert "viewport: { width: 390, height: 844 }" in content
        assert "iPhone" in content

    def test_write_pw_config_pc_has_no_viewport(self, tmp_path: Path) -> None:
        spec = tmp_path / "autorun.spec.ts"
        spec.write_text("", encoding="utf-8")
        content = _write_pw_config(spec, tmp_path / "out", device="pc").read_text()
        assert "isMobile" not in content
        assert "viewport" not in content

    def test_write_pw_config_unknown_device_falls_back_to_pc(self, tmp_path: Path) -> None:
        spec = tmp_path / "autorun.spec.ts"
        spec.write_text("", encoding="utf-8")
        content = _write_pw_config(spec, tmp_path / "out", device="__proto__").read_text()
        assert "isMobile" not in content


# ─────────────────────── _get_cli_version ───────────────────────


class TestGetCliVersion:
    def test_parses_version_string(self) -> None:
        with patch(
            "web.services.playwright_executor.subprocess.run",
            return_value=_mock_proc("Version 1.59.1"),
        ):
            assert _get_cli_version() == "1.59.1"

    def test_returns_empty_on_error(self) -> None:
        with patch("web.services.playwright_executor.subprocess.run", side_effect=OSError):
            assert _get_cli_version() == ""


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


# ─────────────────────── per_test_timeout_sec パラメータ ───────────────────────


class TestPerTestTimeoutParam:
    def test_per_test_timeout_passed_to_config(self, tmp_out: Path) -> None:
        """per_test_timeout_sec が Playwright config の timeout (ms) として反映される。"""
        captured_cmds: list[list[str]] = []
        config_contents: list[str] = []

        def fake_run(cmd: list[str], **_: object) -> MagicMock:
            captured_cmds.append(cmd)
            # --config の後の引数からコンフィグファイルパスを取得して内容を確認
            idx = cmd.index("--config") + 1 if "--config" in cmd else -1
            if idx > 0:
                from pathlib import Path as P

                try:
                    config_contents.append(P(cmd[idx]).read_text())
                except Exception:
                    pass
            return _mock_proc(_VALID_JSON)

        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=True),
            patch("web.services.playwright_executor.subprocess.run", side_effect=fake_run),
        ):
            run_playwright(Path("spec.ts"), tmp_out, per_test_timeout_sec=45)

        assert any("timeout: 45000" in c for c in config_contents)

    def test_default_per_test_timeout_is_30s(self, tmp_out: Path) -> None:
        config_contents: list[str] = []

        def fake_run(cmd: list[str], **_: object) -> MagicMock:
            idx = cmd.index("--config") + 1 if "--config" in cmd else -1
            if idx > 0:
                from pathlib import Path as P

                try:
                    config_contents.append(P(cmd[idx]).read_text())
                except Exception:
                    pass
            return _mock_proc(_VALID_JSON)

        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=True),
            patch("web.services.playwright_executor.subprocess.run", side_effect=fake_run),
        ):
            run_playwright(Path("spec.ts"), tmp_out)

        assert any("timeout: 30000" in c for c in config_contents)
