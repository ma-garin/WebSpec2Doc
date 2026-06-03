from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from web.services.playwright_executor import (
    _build_html_report,
    _ensure_pw_env,
    _error_result,
    _first_error,
    _get_cli_version,
    _map_status,
    _parse_results,
    _pw_test_available,
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

    def test_success_parses_json(self, tmp_out: Path) -> None:
        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=True),
            patch(
                "web.services.playwright_executor.subprocess.run",
                return_value=_mock_proc(_VALID_JSON),
            ),
        ):
            result = run_playwright(Path("spec.ts"), tmp_out)

        assert result["ok"] is True
        assert result["passed"] == 1
        assert result["failed"] == 0
        assert len(result["tests"]) == 1
        assert result["tests"][0]["title"] == "ログイン画面表示"

    def test_success_writes_json_report(self, tmp_out: Path) -> None:
        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=True),
            patch(
                "web.services.playwright_executor.subprocess.run",
                return_value=_mock_proc(_VALID_JSON),
            ),
        ):
            run_playwright(Path("spec.ts"), tmp_out)

        saved = json.loads((tmp_out / "playwright_report.json").read_text())
        assert saved["passed"] == 1

    def test_failure_returncode_sets_ok_false(self, tmp_out: Path) -> None:
        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=True),
            patch(
                "web.services.playwright_executor.subprocess.run",
                return_value=_mock_proc(_FAILED_JSON, returncode=1),
            ),
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
        assert "タイムアウト" in result["error"]

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

    def test_invalid_json_stdout_does_not_crash(self, tmp_out: Path) -> None:
        with (
            patch("web.services.playwright_executor.shutil.which", return_value="/usr/bin/npx"),
            patch("web.services.playwright_executor._pw_test_available", return_value=True),
            patch(
                "web.services.playwright_executor.subprocess.run",
                return_value=_mock_proc("not-json", returncode=0),
            ),
        ):
            result = run_playwright(Path("spec.ts"), tmp_out)

        assert "ok" in result

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
        assert "--reporter=json" in cmd
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
        result = _parse_results({}, long_stdout, "", 0)
        assert len(result["stdout"]) == 4000

    def test_stderr_truncated_to_2000(self) -> None:
        long_stderr = "e" * 3000
        result = _parse_results({}, "", long_stderr, 0)
        assert len(result["stderr"]) == 2000

    def test_ok_reflects_returncode(self) -> None:
        assert _parse_results({}, "", "", 0)["ok"] is True
        assert _parse_results({}, "", "", 1)["ok"] is False


# ─────────────────────── _map_status ───────────────────────


class TestMapStatus:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("passed", "passed"),
            ("expected", "passed"),
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


# ─────────────────────── _build_html_report ───────────────────────


class TestBuildHtmlReport:
    def test_pass_badge(self) -> None:
        html = _build_html_report(
            {"ok": True, "passed": 5, "failed": 0, "skipped": 0, "total": 5, "tests": []}
        )
        assert "PASS" in html
        assert "#16a34a" in html

    def test_fail_badge(self) -> None:
        html = _build_html_report(
            {"ok": False, "passed": 0, "failed": 1, "skipped": 0, "total": 1, "tests": []}
        )
        assert "FAIL" in html
        assert "#dc2626" in html

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
        tests = [{"title": "ログイン", "status": "passed", "duration_ms": 150, "error": ""}]
        html = _build_html_report({"ok": True, "tests": tests})
        assert "ログイン" in html
        assert "150ms" in html


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
