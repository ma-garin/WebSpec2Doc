from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.env_store as env_store_mod
import web.routes.history as history_mod
import web.routes.report as report_mod
import web.summary as summary_mod
import web.validation as validation_mod


def _client():
    return appmod.app.test_client()


# ---------- web/security.py ----------


class TestHostMatches:
    def test_matching_host_returns_true(self) -> None:
        from web.security import _host_matches

        assert _host_matches("https://example.com/path", "example.com") is True

    def test_different_host_returns_false(self) -> None:
        from web.security import _host_matches

        assert _host_matches("https://evil.com/x", "example.com") is False

    def test_invalid_url_returns_false(self) -> None:
        from web.security import _host_matches

        assert _host_matches("not-a-url", "example.com") is False

    def test_empty_string_returns_false(self) -> None:
        from web.security import _host_matches

        assert _host_matches("", "example.com") is False


class TestCsrfGuard:
    def test_get_request_passes(self) -> None:
        from web.security import csrf_guard

        with appmod.app.test_request_context("/", method="GET"):
            assert csrf_guard() is None

    def test_post_with_matching_origin_passes(self) -> None:
        from web.security import csrf_guard

        with appmod.app.test_request_context(
            "/", method="POST", headers={"Origin": "http://localhost"}
        ):
            assert csrf_guard() is None

    def test_post_with_null_origin_returns_403(self) -> None:
        from web.security import csrf_guard

        with appmod.app.test_request_context("/", method="POST", headers={"Origin": "null"}):
            resp = csrf_guard()
            assert resp is not None
            assert resp.status_code == 403

    def test_post_with_mismatched_origin_returns_403(self) -> None:
        from web.security import csrf_guard

        with appmod.app.test_request_context(
            "/", method="POST", headers={"Origin": "https://evil.com"}
        ):
            resp = csrf_guard()
            assert resp is not None
            assert resp.status_code == 403

    def test_post_with_matching_referer_passes(self) -> None:
        from web.security import csrf_guard

        with appmod.app.test_request_context(
            "/", method="POST", headers={"Referer": "http://localhost/page"}
        ):
            assert csrf_guard() is None

    def test_post_with_mismatched_referer_returns_403(self) -> None:
        from web.security import csrf_guard

        with appmod.app.test_request_context(
            "/", method="POST", headers={"Referer": "https://evil.com/x"}
        ):
            resp = csrf_guard()
            assert resp is not None
            assert resp.status_code == 403

    def test_post_without_origin_or_referer_passes(self) -> None:
        from web.security import csrf_guard

        with appmod.app.test_request_context("/", method="POST"):
            assert csrf_guard() is None


class TestLocalhostGuard:
    def test_loopback_hosts_pass(self) -> None:
        from web.security import localhost_guard

        for host in ("localhost", "localhost:8765", "127.0.0.1", "[::1]:8765"):
            with appmod.app.test_request_context("/", headers={"Host": host}):
                assert localhost_guard() is None

    def test_non_local_hosts_return_403(self) -> None:
        for host in ("example.com", "localhost.evil.test", "192.168.1.10", "127.0.0.2"):
            response = _client().get("/", headers={"Host": host})
            assert response.status_code == 403


# ---------- web/env_store.py ----------


class TestReadEnv:
    def test_reads_key_value(self, tmp_path: Path, monkeypatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=bar\n", encoding="utf-8")
        monkeypatch.setattr(env_store_mod, "ENV_FILE", env_file)
        result = env_store_mod._read_env()
        assert result["FOO"] == "bar"

    def test_skips_comments(self, tmp_path: Path, monkeypatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\nFOO=bar\n", encoding="utf-8")
        monkeypatch.setattr(env_store_mod, "ENV_FILE", env_file)
        result = env_store_mod._read_env()
        assert "# comment" not in result
        assert result["FOO"] == "bar"

    def test_skips_lines_without_equals(self, tmp_path: Path, monkeypatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("NOEQ\nFOO=bar\n", encoding="utf-8")
        monkeypatch.setattr(env_store_mod, "ENV_FILE", env_file)
        result = env_store_mod._read_env()
        assert "NOEQ" not in result

    def test_returns_empty_when_no_file(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(env_store_mod, "ENV_FILE", tmp_path / "nonexistent.env")
        assert env_store_mod._read_env() == {}


class TestWriteEnv:
    def test_writes_new_key(self, tmp_path: Path, monkeypatch) -> None:
        env_file = tmp_path / ".env"
        monkeypatch.setattr(env_store_mod, "ENV_FILE", env_file)
        env_store_mod._write_env({"OPENAI_API_KEY": "sk-test"})
        assert "OPENAI_API_KEY=sk-test" in env_file.read_text(encoding="utf-8")

    def test_updates_existing_key(self, tmp_path: Path, monkeypatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("OPENAI_API_KEY=old\n", encoding="utf-8")
        monkeypatch.setattr(env_store_mod, "ENV_FILE", env_file)
        env_store_mod._write_env({"OPENAI_API_KEY": "new"})
        text = env_file.read_text(encoding="utf-8")
        assert "new" in text
        assert "old" not in text

    def test_rejects_invalid_key_name(self, tmp_path: Path, monkeypatch) -> None:
        env_file = tmp_path / ".env"
        monkeypatch.setattr(env_store_mod, "ENV_FILE", env_file)
        env_store_mod._write_env({"INVALID KEY!": "value"})
        assert not env_file.exists()

    def test_skips_empty_updates(self, tmp_path: Path, monkeypatch) -> None:
        env_file = tmp_path / ".env"
        monkeypatch.setattr(env_store_mod, "ENV_FILE", env_file)
        env_store_mod._write_env({})
        assert not env_file.exists()


class TestMaskKey:
    def test_empty_key_returns_empty(self) -> None:
        assert env_store_mod._mask_key("") == ""

    def test_short_key_returns_stars(self) -> None:
        result = env_store_mod._mask_key("sk-abc")
        assert result == "****"

    def test_long_key_masked_partial(self) -> None:
        result = env_store_mod._mask_key("sk-abcdefghijklmnop")
        assert result.startswith("sk-ab")
        assert result.endswith("mnop")
        assert "…" in result


# ---------- web/validation.py ----------


class TestCleanInt:
    def test_valid_int_within_range(self) -> None:
        assert validation_mod._clean_int("5", 3, 1, 10) == 5

    def test_invalid_string_returns_default(self) -> None:
        assert validation_mod._clean_int("bad", 3, 1, 10) == 3

    def test_clamps_to_min(self) -> None:
        assert validation_mod._clean_int("0", 3, 1, 10) == 1

    def test_clamps_to_max(self) -> None:
        assert validation_mod._clean_int("99", 3, 1, 10) == 10


class TestSafeAuthPath:
    def test_empty_returns_empty(self) -> None:
        assert validation_mod._safe_auth_path("") == ""

    def test_file_within_project_allowed(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        auth = tmp_path / "auth.json"
        auth.write_text("{}", encoding="utf-8")
        result = validation_mod._safe_auth_path(str(auth))
        assert result == str(auth)

    def test_file_outside_project_rejected(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        outside = Path("/tmp/evil_auth.json")
        result = validation_mod._safe_auth_path(str(outside))
        assert result == ""


class TestSafeOutputPath:
    def test_empty_returns_none(self) -> None:
        assert validation_mod._safe_output_path("") is None

    def test_path_outside_output_dir_rejected(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(validation_mod, "OUTPUT_DIR", tmp_path / "output")
        result = validation_mod._safe_output_path("/etc/passwd")
        assert result is None

    def test_path_inside_output_dir_allowed(self, tmp_path: Path, monkeypatch) -> None:
        out = tmp_path / "output"
        out.mkdir()
        monkeypatch.setattr(validation_mod, "OUTPUT_DIR", out)
        f = out / "report.html"
        f.write_text("x", encoding="utf-8")
        result = validation_mod._safe_output_path(str(f))
        assert result == f

    def test_nonexistent_file_returns_none(self, tmp_path: Path, monkeypatch) -> None:
        out = tmp_path / "output"
        out.mkdir()
        monkeypatch.setattr(validation_mod, "OUTPUT_DIR", out)
        result = validation_mod._safe_output_path(str(out / "missing.html"))
        assert result is None


class TestSanitize:
    def test_strips_whitespace(self) -> None:
        assert validation_mod._sanitize("  hello  ") == "hello"

    def test_removes_newlines(self) -> None:
        assert "\n" not in validation_mod._sanitize("line1\nline2")

    def test_removes_carriage_returns(self) -> None:
        assert "\r" not in validation_mod._sanitize("line1\r\nline2")


# ---------- web/summary.py ----------


class TestCountScreens:
    def test_counts_matching_rows(self, tmp_path: Path) -> None:
        md = tmp_path / "screens.md"
        md.write_text("| 1 | title | url |\n| 2 | title2 | url2 |\n", encoding="utf-8")
        result = summary_mod._count_screens(md)
        assert result == 2

    def test_returns_zero_when_no_file(self, tmp_path: Path) -> None:
        assert summary_mod._count_screens(tmp_path / "nonexistent.md") == 0


class TestSummaryForDomain:
    def test_reads_report_json(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(summary_mod, "OUTPUT_DIR", tmp_path)
        d = tmp_path / "example.com"
        d.mkdir()
        report = {
            "screens": [
                {"forms": [{"fields": ["a", "b"]}], "buttons": ["btn1"]},
            ]
        }
        (d / "report.json").write_text(json.dumps(report), encoding="utf-8")
        result = summary_mod._summary_for_domain("example.com")
        assert result["screens"] == 1
        assert result["forms"] == 1
        assert result["buttons"] == 1

    def test_falls_back_to_snapshot(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(summary_mod, "OUTPUT_DIR", tmp_path)
        d = tmp_path / "example.com"
        snaps = d / "snapshots"
        snaps.mkdir(parents=True)
        pages = [{"url": "https://example.com/", "forms": [], "buttons": []}]
        (snaps / "20240101-120000.json").write_text(json.dumps(pages), encoding="utf-8")
        result = summary_mod._summary_for_domain("example.com")
        assert result["screens"] == 1

    def test_bad_report_json_falls_back(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(summary_mod, "OUTPUT_DIR", tmp_path)
        d = tmp_path / "example.com"
        d.mkdir()
        (d / "report.json").write_text("not json", encoding="utf-8")
        result = summary_mod._summary_for_domain("example.com")
        assert result["screens"] == 0

    def test_bad_snapshot_returns_zero(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(summary_mod, "OUTPUT_DIR", tmp_path)
        d = tmp_path / "example.com"
        snaps = d / "snapshots"
        snaps.mkdir(parents=True)
        (snaps / "20240101-120000.json").write_text("bad", encoding="utf-8")
        result = summary_mod._summary_for_domain("example.com")
        assert result["screens"] == 0


class TestFmtSnapTs:
    def test_parses_valid_stem(self) -> None:
        result = summary_mod._fmt_snap_ts("20240115-143000")
        assert result == "2024-01-15 14:30"

    def test_returns_stem_on_invalid(self) -> None:
        result = summary_mod._fmt_snap_ts("invalid")
        assert result == "invalid"


# ---------- web/process.py ----------


class TestTerminateProc:
    def test_terminates_running_proc(self) -> None:
        from web.process import _terminate_proc

        proc = MagicMock(spec=subprocess.Popen)
        proc.poll.return_value = None
        _terminate_proc(proc)
        proc.terminate.assert_called_once()

    def test_kills_on_timeout(self) -> None:
        from web.process import _terminate_proc

        proc = MagicMock(spec=subprocess.Popen)
        proc.poll.return_value = None
        proc.wait.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=5)
        _terminate_proc(proc)
        proc.kill.assert_called_once()

    def test_skips_already_done_proc(self) -> None:
        from web.process import _terminate_proc

        proc = MagicMock(spec=subprocess.Popen)
        proc.poll.return_value = 0
        _terminate_proc(proc)
        proc.terminate.assert_not_called()


# ---------- src/generator/mermaid_generator.py ----------


class TestFilterNavEdges:
    def test_small_graph_not_filtered(self) -> None:
        import networkx as nx

        from generator.mermaid_generator import _filter_nav_edges

        g = nx.DiGraph()
        g.add_nodes_from(["A", "B", "C"])
        edges = [("A", "B", {}), ("C", "B", {})]
        result = _filter_nav_edges(edges, g)
        assert len(result) == 2

    def test_nav_target_limited_to_one_edge(self) -> None:
        import networkx as nx

        from generator.mermaid_generator import _filter_nav_edges

        g = nx.DiGraph()
        nodes = ["P001", "P002", "P003", "P004", "P005"]
        g.add_nodes_from(nodes)
        # Make P005 a nav target: pointed to by most nodes
        g.add_edges_from([("P001", "P005"), ("P002", "P005"), ("P003", "P005"), ("P004", "P005")])
        edges = [
            ("P001", "P005", {}),
            ("P002", "P005", {}),
            ("P003", "P005", {}),
            ("P004", "P005", {}),
        ]
        result = _filter_nav_edges(edges, g)
        nav_edges = [e for e in result if e[1] == "P005"]
        assert len(nav_edges) == 1

    def test_non_nav_edges_preserved(self) -> None:
        import networkx as nx

        from generator.mermaid_generator import _filter_nav_edges

        g = nx.DiGraph()
        g.add_nodes_from(["P001", "P002", "P003", "P004", "P005"])
        g.add_edge("P001", "P002")
        edges = [("P001", "P002", {})]
        result = _filter_nav_edges(edges, g)
        assert ("P001", "P002", {}) in result


class TestUrlPath:
    def test_path_only(self) -> None:
        from generator.mermaid_generator import _url_path

        assert _url_path("https://example.com/about") == "/about"

    def test_path_with_query(self) -> None:
        from generator.mermaid_generator import _url_path

        result = _url_path("https://example.com/search?q=test")
        assert "q=test" in result

    def test_root_path(self) -> None:
        from generator.mermaid_generator import _url_path

        assert _url_path("https://example.com/") == "/"


# ---------- web/routes/settings.py (Flask test client) ----------


class TestSettingsRoute:
    def test_get_settings_returns_key_info(self, tmp_path: Path, monkeypatch) -> None:
        import web.env_store as _es

        env_file = tmp_path / ".env"
        env_file.write_text("OPENAI_API_KEY=test-placeholder-key\n", encoding="utf-8")
        monkeypatch.setattr(_es, "ENV_FILE", env_file)
        data = _client().get("/api/settings").get_json()
        assert data["openai_key_set"] is True

    def test_get_settings_no_key(self, tmp_path: Path, monkeypatch) -> None:
        env_file = tmp_path / ".env"
        monkeypatch.setattr(env_store_mod, "ENV_FILE", env_file)
        data = _client().get("/api/settings").get_json()
        assert data["openai_key_set"] is False

    def test_post_settings_saves_key(self, tmp_path: Path, monkeypatch) -> None:
        env_file = tmp_path / ".env"
        monkeypatch.setattr(env_store_mod, "ENV_FILE", env_file)
        res = _client().post("/api/settings", data={"api_key": "test-placeholder-key-for-ci"})
        assert res.status_code == 200
        assert res.get_json()["ok"] is True

    def test_post_settings_saves_model(self, tmp_path: Path, monkeypatch) -> None:
        env_file = tmp_path / ".env"
        monkeypatch.setattr(env_store_mod, "ENV_FILE", env_file)
        res = _client().post("/api/settings", data={"model": "gpt-4o"})
        assert res.status_code == 200

    def test_post_settings_saves_org_and_project(self, tmp_path: Path, monkeypatch) -> None:
        env_file = tmp_path / ".env"
        monkeypatch.setattr(env_store_mod, "ENV_FILE", env_file)
        res = _client().post("/api/settings", data={"org_id": "org-123", "project_id": "proj-abc"})
        assert res.status_code == 200


# ---------- web/routes/history.py (Flask test client) ----------


class TestApiHistory:
    def test_returns_items_list(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(history_mod, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(summary_mod, "OUTPUT_DIR", tmp_path)
        d = tmp_path / "example.com"
        d.mkdir()
        data = _client().get("/api/history").get_json()
        assert "items" in data
        assert any(i["domain"] == "example.com" for i in data["items"])

    def test_empty_output_dir(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(history_mod, "OUTPUT_DIR", tmp_path / "nonexistent")
        data = _client().get("/api/history").get_json()
        assert data["items"] == []

    def test_counts_snapshots(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(history_mod, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(summary_mod, "OUTPUT_DIR", tmp_path)
        d = tmp_path / "example.com"
        snaps = d / "snapshots"
        snaps.mkdir(parents=True)
        (snaps / "20240101-120000.json").write_text("[]", encoding="utf-8")
        data = _client().get("/api/history").get_json()
        item = next(i for i in data["items"] if i["domain"] == "example.com")
        assert item["snapshot_count"] == 1


class TestApiSnapshots:
    def test_returns_snapshot_list(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(history_mod, "OUTPUT_DIR", tmp_path)
        d = tmp_path / "example.com"
        snaps = d / "snapshots"
        snaps.mkdir(parents=True)
        pages = [{"url": "https://example.com/", "forms": [], "buttons": []}]
        (snaps / "20240101-120000.json").write_text(json.dumps(pages), encoding="utf-8")
        data = _client().get("/api/snapshots?domain=example.com").get_json()
        assert len(data["snapshots"]) == 1

    def test_invalid_domain_returns_404(self) -> None:
        res = _client().get("/api/snapshots?domain=!!bad!!")
        assert res.status_code == 404

    def test_skips_unreadable_snapshot(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(history_mod, "OUTPUT_DIR", tmp_path)
        d = tmp_path / "example.com"
        snaps = d / "snapshots"
        snaps.mkdir(parents=True)
        (snaps / "20240101-120000.json").write_text("bad json", encoding="utf-8")
        data = _client().get("/api/snapshots?domain=example.com").get_json()
        assert data["snapshots"] == []


# ---------- web/routes/report.py (Flask test client) ----------


class TestApiResult:
    def test_invalid_domain_returns_404(self) -> None:
        res = _client().get("/api/result?domain=!!bad!!")
        assert res.status_code == 404

    def test_missing_domain_dir_returns_404(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(report_mod, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(summary_mod, "OUTPUT_DIR", tmp_path)
        res = _client().get("/api/result?domain=nonexistent.com")
        assert res.status_code == 404

    def test_existing_domain_returns_files(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(report_mod, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(summary_mod, "OUTPUT_DIR", tmp_path)
        d = tmp_path / "example.com"
        d.mkdir()
        (d / "report.html").write_text("<html></html>", encoding="utf-8")
        data = _client().get("/api/result?domain=example.com").get_json()
        assert "files" in data
        assert "summary" in data


class TestDownloadZip:
    def test_invalid_domain_returns_404(self) -> None:
        res = _client().get("/download-zip?domain=!!bad!!")
        assert res.status_code == 404

    def test_missing_domain_dir_returns_404(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(report_mod, "OUTPUT_DIR", tmp_path)
        res = _client().get("/download-zip?domain=nonexistent.com")
        assert res.status_code == 404

    def test_valid_domain_returns_zip(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(report_mod, "OUTPUT_DIR", tmp_path)
        d = tmp_path / "example.com"
        d.mkdir()
        (d / "report.html").write_text("<html></html>", encoding="utf-8")
        res = _client().get("/download-zip?domain=example.com")
        assert res.status_code == 200
        assert res.content_type == "application/zip"
