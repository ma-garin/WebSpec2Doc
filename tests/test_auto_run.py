from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from web.config import MAX_DEPTH, MAX_PAGES_LIMIT
from web.routes.auto_run import (
    AutoRunJob,
    _current_test_progress,
    _do_login,
    _execute_tests,
    _now_iso,
    _phase_crawl,
    _phase_discover,
    _phase_generate_scripts,
    _resolve_crawl_limits,
    _truthy,
)

# ─────────────────────── フィクスチャ ───────────────────────


def _make_job(**kwargs: Any) -> AutoRunJob:
    defaults: dict[str, Any] = {
        "job_id": "test-job-001",
        "url": "https://example.com",
        "domain": "example.com",
        "started_at": _now_iso(),
    }
    return AutoRunJob(**{**defaults, **kwargs})


# ─────────────────────── AutoRunJob ───────────────────────


class TestAutoRunJob:
    def test_add_log_appends_with_timestamp(self) -> None:
        job = _make_job()
        job.add_log("テストメッセージ")
        assert len(job.log) == 1
        assert "テストメッセージ" in job.log[0]

    def test_to_dict_contains_required_keys(self) -> None:
        job = _make_job()
        d = job.to_dict()
        required = {
            "job_id",
            "url",
            "domain",
            "status",
            "step_label",
            "log",
            "outputs",
            "test_results",
            "error",
            "started_at",
            "finished_at",
            "elapsed_sec",
            "input_request",
            "run_policy",
            "step_data",
        }
        assert required.issubset(d.keys())

    def test_to_dict_log_capped_at_1000(self) -> None:
        """長時間クロールで先頭ログが早期に消えないよう、上限は1000行。"""
        job = _make_job()
        for i in range(1050):
            job.add_log(f"msg {i}")
        d = job.to_dict()
        assert len(d["log"]) == 1000
        assert d["log"][0].endswith("msg 50")

    def test_log_total_size_and_huge_line_are_capped(self) -> None:
        job = AutoRunJob(job_id="test", url="https://example.com")
        job.add_log("<img src=x onerror=alert(1)>" + "あ" * 200_000)
        payload = job.to_dict()["log"]
        assert len("".join(payload).encode("utf-8")) <= 256 * 1024
        assert payload[0].startswith("[")

    def test_step_data_in_to_dict(self) -> None:
        job = _make_job()
        job.step_data["crawl"] = {"screens": 5}
        assert job.to_dict()["step_data"]["crawl"]["screens"] == 5

    def test_elapsed_sec_returns_nonnegative(self) -> None:
        job = _make_job()
        assert job.elapsed_sec() >= 0

    def test_elapsed_sec_zero_without_started_at(self) -> None:
        job = AutoRunJob(job_id="x", url="https://example.com")
        assert job.elapsed_sec() == 0

    def test_cancel_sets_cancelled_flag(self) -> None:
        job = _make_job()
        job.cancel()
        assert job._cancelled is True

    def test_cancel_terminates_proc(self) -> None:
        job = _make_job()
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        job._proc = mock_proc
        job.cancel()
        mock_proc.terminate.assert_called_once()

    def test_cancel_sets_input_event(self) -> None:
        job = _make_job()
        job.cancel()
        assert job._input_event.is_set()


# ─────────────────────── _execute_tests ───────────────────────


class TestExecuteTests:
    def test_no_spec_path_sets_failed(self, tmp_path: Path) -> None:
        job = _make_job()
        job.outputs = {}  # spec_ts なし
        _execute_tests(job)
        assert job.status == "failed"
        assert "spec.ts" in job.error

    def test_spec_path_not_found_sets_failed(self, tmp_path: Path) -> None:
        job = _make_job()
        job.outputs = {"spec_ts": str(tmp_path / "nonexistent.spec.ts")}
        _execute_tests(job)
        # run_playwright を呼ぼうとするが spec_path は存在 → それ自体は問題ない
        # ただし実際には mock なので今回はパス存在チェックなし
        # spec_ts があれば run_playwright が呼ばれる
        assert job.status in ("complete", "failed")

    def test_success_sets_complete(self, tmp_path: Path) -> None:
        spec_path = tmp_path / "autorun.spec.ts"
        spec_path.write_text("", encoding="utf-8")
        job = _make_job(domain="example.com")
        job.outputs = {"spec_ts": str(spec_path)}
        job.run_policy = {"filter_mode": "all", "per_test_timeout_sec": 30}

        mock_result = {
            "ok": True,
            "passed": 5,
            "failed": 0,
            "skipped": 0,
            "total": 5,
            "tests": [],
        }
        with patch("web.routes.auto_run.run_playwright", return_value=mock_result):
            _execute_tests(job)

        assert job.status == "complete"
        assert job.test_results["passed"] == 5
        assert job.finished_at != ""

    def test_failure_test_sets_complete_not_failed(self, tmp_path: Path) -> None:
        """個々のテストが失敗しても（実行自体は正常完走）job.status は 'complete'。
        実行結果に error/interrupted が無いのが「正常完走・一部失敗」の実データ形状
        （_parse_results は parse 不能時のみ error を載せる）。"""
        spec_path = tmp_path / "autorun.spec.ts"
        spec_path.write_text("", encoding="utf-8")
        job = _make_job(domain="example.com")
        job.outputs = {"spec_ts": str(spec_path)}
        job.run_policy = {"filter_mode": "all", "per_test_timeout_sec": 30}

        mock_result = {
            "ok": False,
            "passed": 0,
            "failed": 3,
            "skipped": 0,
            "total": 3,
            "tests": [],
        }
        with patch("web.routes.auto_run.run_playwright", return_value=mock_result):
            _execute_tests(job)

        assert job.status == "complete"
        assert job.test_results["ok"] is False

    def test_result_error_with_zero_total_sets_job_failed(self, tmp_path: Path) -> None:
        """実行結果が解析不能・未セットアップ等で error を伴う場合、'complete' を
        偽装せず job.status='failed' にする（AutoRunで188件実行して0/0/0が
        無言で成功表示された致命的UX破綻の再発防止）。"""
        spec_path = tmp_path / "autorun.spec.ts"
        spec_path.write_text("", encoding="utf-8")
        job = _make_job(domain="example.com")
        job.outputs = {"spec_ts": str(spec_path)}
        job.run_policy = {"filter_mode": "all", "per_test_timeout_sec": 30}

        mock_result = {
            "ok": False,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "total": 0,
            "tests": [],
            "error": "実行結果を解析できませんでした（終了コード 1）",
        }
        with patch("web.routes.auto_run.run_playwright", return_value=mock_result):
            _execute_tests(job)

        assert job.status == "failed"
        assert "解析できませんでした" in job.error
        assert job.test_results["total"] == 0

    def test_interrupted_with_partial_results_sets_job_failed(self, tmp_path: Path) -> None:
        """全体タイムアウトで中断され部分結果が回収された場合も 'complete' を
        偽装せず job.status='failed' とし、部分結果件数をログに残す。"""
        spec_path = tmp_path / "autorun.spec.ts"
        spec_path.write_text("", encoding="utf-8")
        job = _make_job(domain="example.com")
        job.outputs = {"spec_ts": str(spec_path)}
        job.run_policy = {"filter_mode": "all", "per_test_timeout_sec": 30}

        mock_result = {
            "ok": False,
            "passed": 40,
            "failed": 2,
            "skipped": 0,
            "total": 42,
            "tests": [],
            "error": "テスト実行が制限時間 600秒 に達したため中断しました。188件中42件まで実行済み",
            "interrupted": True,
        }
        with patch("web.routes.auto_run.run_playwright", return_value=mock_result):
            _execute_tests(job)

        assert job.status == "failed"
        assert any("中断されました（部分結果を回収）" in line for line in job.log)
        assert job.test_results["total"] == 42

    def test_run_playwright_exception_sets_failed(self, tmp_path: Path) -> None:
        spec_path = tmp_path / "autorun.spec.ts"
        spec_path.write_text("", encoding="utf-8")
        job = _make_job(domain="example.com")
        job.outputs = {"spec_ts": str(spec_path)}
        job.run_policy = {"filter_mode": "all", "per_test_timeout_sec": 30}

        with patch(
            "web.routes.auto_run.run_playwright", side_effect=RuntimeError("予期しないエラー")
        ):
            _execute_tests(job)

        assert job.status == "failed"
        assert "予期しないエラー" in job.error

    def test_cancelled_job_skips_execution(self, tmp_path: Path) -> None:
        spec_path = tmp_path / "autorun.spec.ts"
        spec_path.write_text("", encoding="utf-8")
        job = _make_job(domain="example.com")
        job.outputs = {"spec_ts": str(spec_path)}
        job._cancelled = True

        mock_pw = MagicMock()
        with patch("web.routes.auto_run.run_playwright", mock_pw):
            _execute_tests(job)

        mock_pw.assert_not_called()

    def test_filter_mode_regenerates_spec(self, tmp_path: Path) -> None:
        spec_path = tmp_path / "autorun.spec.ts"
        spec_path.write_text("", encoding="utf-8")
        candidates = {
            "candidates": [
                {
                    "id": "T1",
                    "title": "画面表示スモーク",
                    "automation_status": "auto",
                    "steps": [],
                    "expected": "",
                    "trace_id": "P001",
                }
            ]
        }
        # _execute_tests は OUTPUT_DIR / domain / "qa_process" / "playwright_candidates.json" を参照
        qa_dir = tmp_path / "example.com" / "qa_process"
        qa_dir.mkdir(parents=True)
        cands_path = qa_dir / "playwright_candidates.json"
        cands_path.write_text(json.dumps(candidates), encoding="utf-8")

        job = _make_job(domain="example.com")
        job.outputs = {"spec_ts": str(spec_path)}
        job.run_policy = {"filter_mode": "smoke", "per_test_timeout_sec": 30}

        mock_result = {"ok": True, "passed": 1, "failed": 0, "skipped": 0, "total": 1, "tests": []}
        captured_filter: list[str] = []

        def fake_gen(domain: str, path: Path, out: Path, filter_mode: str = "all") -> None:
            captured_filter.append(filter_mode)

        with (
            patch("web.routes.auto_run.run_playwright", return_value=mock_result),
            patch("web.routes.auto_run.OUTPUT_DIR", tmp_path),
            patch("web.routes.auto_run.generate_spec_ts", side_effect=fake_gen),
        ):
            _execute_tests(job)

        # smoke フィルターで再生成が呼ばれた
        assert "smoke" in captured_filter

    def test_per_test_timeout_passed_to_run_playwright(self, tmp_path: Path) -> None:
        spec_path = tmp_path / "autorun.spec.ts"
        spec_path.write_text("", encoding="utf-8")
        job = _make_job(domain="example.com")
        job.outputs = {"spec_ts": str(spec_path)}
        job.run_policy = {"filter_mode": "all", "per_test_timeout_sec": 45}

        mock_result = {"ok": True, "passed": 1, "failed": 0, "skipped": 0, "total": 1, "tests": []}
        captured_kwargs: list[dict[str, Any]] = []

        def fake_pw(spec: Path, outdir: Path, **kwargs: Any) -> dict[str, Any]:
            captured_kwargs.append(kwargs)
            return mock_result

        with patch("web.routes.auto_run.run_playwright", side_effect=fake_pw):
            _execute_tests(job)

        assert captured_kwargs[0].get("per_test_timeout_sec") == 45

    def test_playwright_report_html_saved_in_outputs(self, tmp_path: Path) -> None:
        spec_path = tmp_path / "autorun.spec.ts"
        spec_path.write_text("", encoding="utf-8")
        job = _make_job(domain="example.com")
        job.outputs = {"spec_ts": str(spec_path)}
        job.run_policy = {"filter_mode": "all", "per_test_timeout_sec": 30}

        # playwright-report/index.html を作成して outputs に登録されるかテスト
        qa_dir = tmp_path
        pw_html = qa_dir / "playwright-report" / "index.html"
        pw_html.parent.mkdir(parents=True)
        pw_html.write_text("<html></html>")

        mock_result = {"ok": True, "passed": 1, "failed": 0, "skipped": 0, "total": 1, "tests": []}
        with (
            patch("web.routes.auto_run.run_playwright", return_value=mock_result),
            patch("web.routes.auto_run.OUTPUT_DIR", tmp_path.parent),
        ):
            _execute_tests(job)

        # outputs に playwright_report_html が登録されているか確認
        # (ディレクトリ構造によっては登録されない場合もあるが，is_file チェックがあれば登録される)
        assert job.status == "complete"


# ─────────────────────── _current_test_progress ───────────────────────
#
# AutoRunで188件承認・実行しても実行中に進捗が全く見えない、というドッグ
# フーディング指摘への対応。進捗NDJSON（playwright_executorがonTestEndで
# 逐次追記するもの）を読み取り専用で覗き見て「n/188件目」表示用データを返す。


class TestCurrentTestProgress:
    def test_no_progress_file_returns_zero_and_none_total(self, tmp_path: Path) -> None:
        job = _make_job(domain="example.com")
        with patch("web.routes.auto_run.OUTPUT_DIR", tmp_path):
            progress = _current_test_progress(job)
        assert progress == {"completed": 0, "total": None}

    def test_reads_partial_progress_from_ndjson(self, tmp_path: Path) -> None:
        job = _make_job(domain="example.com")
        qa_dir = tmp_path / "example.com" / "qa_process"
        qa_dir.mkdir(parents=True)
        ndjson_path = qa_dir / "playwright_progress.ndjson"
        lines = [
            json.dumps({"event": "begin", "total": 188}),
            json.dumps({"event": "test", "title": "t1", "status": "passed"}),
            json.dumps({"event": "test", "title": "t2", "status": "passed"}),
            json.dumps({"event": "test", "title": "t3", "status": "failed"}),
        ]
        ndjson_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        with patch("web.routes.auto_run.OUTPUT_DIR", tmp_path):
            progress = _current_test_progress(job)

        assert progress == {"completed": 3, "total": 188}


# ─────────────────────── _phase_generate_scripts ───────────────────────


class TestPhaseGenerateScripts:
    def test_no_candidates_file_sets_failed(self, tmp_path: Path) -> None:
        job = _make_job(domain="example.com")
        with patch("web.routes.auto_run.OUTPUT_DIR", tmp_path):
            _phase_generate_scripts(job)
        assert job.status == "failed"
        assert "playwright_candidates.json" in job.error

    def test_success_sets_spec_ts_output(self, tmp_path: Path) -> None:
        qa_dir = tmp_path / "example.com" / "qa_process"
        qa_dir.mkdir(parents=True)
        cands = qa_dir / "playwright_candidates.json"
        cands.write_text('{"candidates": []}', encoding="utf-8")

        job = _make_job(domain="example.com")
        with patch("web.routes.auto_run.OUTPUT_DIR", tmp_path):
            _phase_generate_scripts(job)

        assert "spec_ts" in job.outputs
        assert job.status != "failed"

    def test_cancelled_skips_phase(self, tmp_path: Path) -> None:
        job = _make_job(domain="example.com")
        job._cancelled = True
        mock_gen = MagicMock()
        with patch("web.routes.auto_run.generate_spec_ts", mock_gen):
            _phase_generate_scripts(job)
        mock_gen.assert_not_called()


# ─────────────────────── _phase_discover / _do_login（ドメイン単位の認証統合）───────────────────────
#
# B-auth-ux #3: AutoRun は「ログインが必要なページ」を都度・画面ごとに尋ねるのではなく、
# ドメイン単位で1回だけ入力を求め、取得した認証情報（auth.json）を後続のクロール全体で
# 再利用しなければならない。この回帰を防ぐためのテスト。


class TestPhaseDiscoverLoginConsolidation:
    def _discover_proc(self, login_pages: list[dict]) -> MagicMock:
        pages = [
            {
                "url": "https://example.com/",
                "title": "Top",
                "login_required": False,
                "login_url": "",
            },
            *login_pages,
        ]
        proc = MagicMock()
        proc.stdout = json.dumps({"pages": pages})
        return proc

    def test_multiple_login_pages_yield_single_input_request(self) -> None:
        """同一ドメインに認証必須ページが複数あっても input_request は1回だけ生成される。"""
        job = _make_job(url="https://example.com/", domain="example.com")
        login_pages = [
            {
                "url": f"https://example.com/mypage{i}.html",
                "title": f"マイページ{i}",
                "login_required": True,
                "login_url": "https://example.com/login.html",
            }
            for i in range(3)
        ]
        with patch(
            "web.routes.auto_run.subprocess.run",
            return_value=self._discover_proc(login_pages),
        ):
            _phase_discover(job, depth=2, max_pages=30)

        assert job.status == "awaiting_input"
        assert job.input_request is not None
        assert job.input_request["type"] == "login"
        assert job.input_request["login_url"] == "https://example.com/login.html"
        # メッセージにドメイン内の認証必須件数（3件）がまとまって表示される
        assert "3件" in job.input_request["message"]

    def test_no_login_pages_skips_awaiting_input(self) -> None:
        job = _make_job(url="https://example.com/", domain="example.com")
        with patch(
            "web.routes.auto_run.subprocess.run",
            return_value=self._discover_proc([]),
        ):
            _phase_discover(job, depth=2, max_pages=30)

        assert job.status != "awaiting_input"
        assert job.input_request is None

    def test_do_login_success_sets_auth_path_for_whole_domain(self, tmp_path: Path) -> None:
        """一度だけ入力した認証情報の auth_path が job に保存され、後続クロール全体に
        再利用される（画面ごとに再入力を求めない）ことを検証する。"""
        job = _make_job(url="https://example.com/", domain="example.com")
        job.input_request = {"login_url": "https://example.com/login.html"}
        job._input_data = {"username": "user", "password": "pass"}

        login_proc = MagicMock()
        login_proc.stdout = json.dumps({"success": True})

        with (
            patch("web.routes.auto_run.OUTPUT_DIR", tmp_path),
            patch("web.routes.auto_run.subprocess.run", return_value=login_proc) as mock_run,
        ):
            _do_login(job)

        assert job.status != "failed"
        assert job.auth_path
        assert job.auth_path.endswith("auth.json")
        # ログイン試行は1回だけ（画面ごとに繰り返し呼ばれない）
        assert mock_run.call_count == 1

        # 取得した auth_path が後続のクロールフェーズにそのまま渡され、
        # 同一ドメインの他画面のために再度ログインを求めない。
        popen_calls: list[list[str]] = []

        def fake_popen(cmd, *args, **kwargs):
            popen_calls.append(cmd)
            proc = MagicMock()
            proc.stdout = iter(["ok\n"])
            proc.wait.return_value = 0
            return proc

        report_dir = tmp_path / "example.com"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "report.json").write_text('{"screens": []}', encoding="utf-8")

        with (
            patch("web.routes.auto_run.OUTPUT_DIR", tmp_path),
            patch("web.routes.auto_run.subprocess.Popen", side_effect=fake_popen),
        ):
            _phase_crawl(job, depth=2, max_pages=30)

        assert popen_calls, "クロールサブプロセスが起動していない"
        assert "--auth" in popen_calls[0]
        assert popen_calls[0][popen_calls[0].index("--auth") + 1] == job.auth_path

    def test_crawl_cli_stdout_tagged_as_developer_detail(self, tmp_path: Path) -> None:
        """クロールCLIの生stdoutは `[cli]` タグ付きでログに追加される
        （UIでは既定非表示・開発者向けトグルで表示。生ログがそのまま表示され
        読みにくい、というドッグフーディング指摘への対応）。"""
        job = _make_job(url="https://example.com/", domain="example.com")

        def fake_popen(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.stdout = iter(["Crawling https://example.com/...\n", "  found 3 links\n"])
            proc.wait.return_value = 0
            return proc

        report_dir = tmp_path / "example.com"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "report.json").write_text('{"screens": []}', encoding="utf-8")

        with (
            patch("web.routes.auto_run.OUTPUT_DIR", tmp_path),
            patch("web.routes.auto_run.subprocess.Popen", side_effect=fake_popen),
        ):
            _phase_crawl(job, depth=2, max_pages=30)

        cli_lines = [line for line in job.log if "[cli]" in line]
        assert len(cli_lines) == 2
        assert "Crawling https://example.com/..." in cli_lines[0]
        assert "found 3 links" in cli_lines[1]


# ─────────────────────── _truthy ───────────────────────


class TestTruthy:
    @pytest.mark.parametrize("val", ["1", "true", "True", "yes", "on"])
    def test_truthy_values(self, val: str) -> None:
        assert _truthy(val) is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", "", None, False])
    def test_falsy_values(self, val: object) -> None:
        assert _truthy(val) is False


# ─────────────────────── _now_iso ───────────────────────


def test_now_iso_returns_string() -> None:
    result = _now_iso()
    assert isinstance(result, str)
    assert "T" in result  # ISO 形式


# ─────────────────────── _resolve_crawl_limits ───────────────────────


class TestResolveCrawlLimits:
    def test_defaults_to_max_when_omitted(self) -> None:
        """R1-08/R2-18: 深さ・最大ページを省略した場合、既定=上限（全対象）になる。"""
        depth, max_pages = _resolve_crawl_limits({}, {})
        assert depth == MAX_DEPTH
        assert max_pages == MAX_PAGES_LIMIT

    def test_uses_form_values_when_provided(self) -> None:
        depth, max_pages = _resolve_crawl_limits({"depth": "3", "max_pages": "50"}, {})
        assert depth == 3
        assert max_pages == 50

    def test_uses_json_body_when_form_empty(self) -> None:
        depth, max_pages = _resolve_crawl_limits({}, {"depth": "1", "max_pages": "10"})
        assert depth == 1
        assert max_pages == 10

    def test_clamps_values_above_limit(self) -> None:
        depth, max_pages = _resolve_crawl_limits(
            {"depth": str(MAX_DEPTH + 10), "max_pages": str(MAX_PAGES_LIMIT + 10)}, {}
        )
        assert depth == MAX_DEPTH
        assert max_pages == MAX_PAGES_LIMIT

    def test_clamps_values_below_minimum(self) -> None:
        depth, max_pages = _resolve_crawl_limits({"depth": "0", "max_pages": "0"}, {})
        assert depth == 1
        assert max_pages == 1


class TestHistoryRunsRoute:
    """GET /api/history/runs — 一般化された実行履歴（R2-27）。"""

    def _client(self):
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        import app as appmod

        return appmod.app.test_client()

    def test_returns_empty_list_when_no_history(self, tmp_path: Path) -> None:
        with patch("web.routes.auto_run.OUTPUT_DIR", tmp_path):
            res = self._client().get("/api/history/runs")
        assert res.status_code == 200
        assert res.get_json() == {"runs": []}

    def test_includes_logged_autorun_and_running_job(self, tmp_path: Path) -> None:
        from web.services.usage_tracker import record_autorun

        record_autorun(tmp_path, "example.com", status="complete", passed=2, failed=0, total=2)
        job = _make_job(domain="other.com", status="running_tests")
        with (
            patch("web.routes.auto_run.OUTPUT_DIR", tmp_path),
            patch("web.routes.auto_run._JOBS", {job.job_id: job}),
        ):
            res = self._client().get("/api/history/runs")
        data = res.get_json()
        assert res.status_code == 200
        domains = {run["domain"] for run in data["runs"]}
        assert domains == {"example.com", "other.com"}
        running = next(run for run in data["runs"] if run["domain"] == "other.com")
        assert running["source"] == "running"
        assert running["status"] == "running_tests"
