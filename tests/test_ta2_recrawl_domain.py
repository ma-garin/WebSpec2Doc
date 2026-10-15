"""再クロールが「同じサイトのディレクトリ」に書き戻ることの回帰テスト。

不具合: 呼び出し側が `demomart` を渡しても、クローラ CLI が URL のホストから
出力先を作り直すため `output/127.0.0.1:8766/` に書かれ、drift の基準が永久に
できなかった（docs/plans/ta2/unified-verify.md B-1 / B-2）。

契約: `--domain-name` があれば出力先ディレクトリ名はそれに従う。無ければ従来
どおり URL のホストから決める（既存の挙動を変えない）。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod  # noqa: E402
import main as main_mod  # noqa: E402
import web.routes.crawl as crawl_mod  # noqa: E402
import web.routes.ta2 as ta2_mod  # noqa: E402
import web.services.job_queue as jq  # noqa: E402

DOMAIN = "demomart"
URL = "http://127.0.0.1:8766/"


class _Popen:
    def __init__(self, cmd, stdout=None, stderr=None, text=None, bufsize=None) -> None:
        self.cmd = cmd
        self.stdout = iter(["クロール完了\n"])
        self.returncode = None

    def wait(self, timeout=None) -> int:
        self.returncode = 0
        return 0

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9


class TestOutDir:
    """src/main.py の出力先解決。"""

    def test_falls_back_to_host_when_flag_absent(self, tmp_path: Path) -> None:
        args = argparse.Namespace(output=tmp_path)
        assert main_mod._out_dir(args, URL) == tmp_path / "127.0.0.1:8766"

    def test_uses_domain_name_when_given(self, tmp_path: Path) -> None:
        args = argparse.Namespace(output=tmp_path, domain_name=DOMAIN)
        assert main_mod._out_dir(args, URL) == tmp_path / DOMAIN

    @pytest.mark.parametrize("bad", ["", "   ", "..", "../etc", "a/b", "a\\b"])
    def test_rejects_unsafe_directory_names(self, tmp_path: Path, bad: str) -> None:
        args = argparse.Namespace(output=tmp_path, domain_name=bad)
        assert main_mod._out_dir(args, URL) == tmp_path / "127.0.0.1:8766"

    def test_cli_accepts_the_flag(self) -> None:
        root = Path(__file__).resolve().parent.parent
        res = subprocess.run(
            [sys.executable, "src/main.py", "--help"],
            capture_output=True,
            text=True,
            cwd=root,
            timeout=120,
        )
        assert "--domain-name" in res.stdout


class TestJobQueue:
    """web/services/job_queue.py がサブプロセスへ渡す引数。"""

    def _run(self, monkeypatch, tmp_path: Path, **kwargs) -> list[str]:
        calls: list[list[str]] = []

        def fake_popen(cmd, *a, **kw):
            calls.append(cmd)
            return _Popen(cmd)

        monkeypatch.setattr(jq.subprocess, "Popen", fake_popen)
        job = jq.CrawlJob(
            job_id="j1", domain=DOMAIN, site_url=URL, status="queued", started_at="now"
        )
        jq._run_job(job, 2, 30, ["json"], False, "", tmp_path, None, **kwargs)
        return calls[0]

    def test_passes_domain_name_to_the_crawler(self, monkeypatch, tmp_path: Path) -> None:
        cmd = self._run(monkeypatch, tmp_path, domain_name=DOMAIN)
        assert "--domain-name" in cmd
        assert cmd[cmd.index("--domain-name") + 1] == DOMAIN

    def test_omits_the_flag_when_empty(self, monkeypatch, tmp_path: Path) -> None:
        assert "--domain-name" not in self._run(monkeypatch, tmp_path)

    def test_start_crawl_job_defaults_to_the_site_directory_label(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        captured: dict[str, object] = {}

        class _Thread:
            def __init__(self, target=None, args=(), daemon=None, name=None) -> None:
                captured["args"] = args

            def start(self) -> None:
                return None

        monkeypatch.setattr(jq.threading, "Thread", _Thread)
        jq.start_crawl_job(DOMAIN, URL, output_dir=tmp_path)
        assert captured["args"][-1] == DOMAIN


class TestRecrawlRoute:
    """POST /api/ta2/recrawl が見ている画面のディレクトリを渡す。"""

    @pytest.fixture(autouse=True)
    def _clear_job_registry(self):
        """ジョブ台帳はモジュール共有なので、テストごとに空にする。

        残っていると「このサイトは再クロール中です」の 409 ガードが
        前のテストのジョブを見て発火し、無関係な失敗になる。
        """
        from web.services import job_queue

        job_queue._JOBS.clear()
        yield
        job_queue._JOBS.clear()

    def test_recrawl_passes_the_domain_through(self, monkeypatch, tmp_path: Path) -> None:
        calls: list[dict] = []

        def fake_start(domain, url, **kwargs):
            calls.append({"domain": domain, "url": url, **kwargs})
            return "job-1"

        monkeypatch.setattr(ta2_mod, "scoped_output_dir", lambda _base: tmp_path)
        monkeypatch.setattr(
            ta2_mod, "_report", lambda domain: {"meta": {"target_url": URL}, "screens": []}
        )
        monkeypatch.setattr("web.services.job_queue.start_crawl_job", fake_start)

        res = appmod.app.test_client().post("/api/ta2/recrawl", json={"domain": DOMAIN})
        assert res.status_code == 200
        assert calls[0]["domain"] == DOMAIN
        assert calls[0]["domain_name"] == DOMAIN


class TestHomeIngestRoute:
    """POST /run（ホームの取り込み）は domain_name を受け取って転送する。"""

    def _post(self, monkeypatch, tmp_path: Path, data: dict) -> list[str]:
        calls: list[list[str]] = []

        def fake_popen(cmd, *a, **kw):
            calls.append(cmd)
            return _Popen(cmd)

        monkeypatch.setattr(crawl_mod, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(crawl_mod.subprocess, "Popen", fake_popen)
        appmod.app.test_client().post("/run", data=data).get_data()
        return calls[0]

    def test_forwards_domain_name(self, monkeypatch, tmp_path: Path) -> None:
        cmd = self._post(
            monkeypatch, tmp_path, {"urls": URL, "format": "json", "domain_name": DOMAIN}
        )
        assert cmd[cmd.index("--domain-name") + 1] == DOMAIN

    def test_unchanged_without_the_field(self, monkeypatch, tmp_path: Path) -> None:
        assert "--domain-name" not in self._post(
            monkeypatch, tmp_path, {"urls": URL, "format": "json"}
        )
