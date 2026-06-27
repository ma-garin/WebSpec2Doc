"""サイト追加ウィザードの既定挙動テスト（Flask テストクライアント）"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.routes.crawl as crawl_mod
import web.routes.discover as discover_mod
import web.routes.login as login_mod
import web.routes.report as report_mod
import web.routes.site as site_mod
import web.summary as summary_mod


class _Proc:
    def __init__(self, stdout: str = "{}", returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode


class _Popen:
    def __init__(self, cmd, stdout=None, stderr=None, text=None, bufsize=None) -> None:
        self.cmd = cmd
        self.stdout = iter(["クロールを開始しました\n", "クロール完了\n"])
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


def _client():
    return appmod.app.test_client()


def _patch_output_dirs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(crawl_mod, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(report_mod, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(site_mod, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(summary_mod, "OUTPUT_DIR", tmp_path)


def _write_report_files(tmp_path: Path, domain: str = "example.com") -> Path:
    domain_dir = tmp_path / domain
    domain_dir.mkdir(parents=True, exist_ok=True)
    (domain_dir / "report.html").write_text("<html><body>report</body></html>", encoding="utf-8")
    (domain_dir / "report.json").write_text(
        json.dumps({"screens": [{"url": f"https://{domain}/", "forms": [], "buttons": []}]}),
        encoding="utf-8",
    )
    return domain_dir


def _discover_payload(*, login_required: bool = False) -> str:
    return json.dumps(
        {
            "pages": [
                {
                    "url": "https://example.com/",
                    "title": "Top",
                    "login_required": login_required,
                }
            ]
        }
    )


def _index_html() -> str:
    return appmod.app.test_client().get("/").get_data(as_text=True)


def test_discover_btn_is_in_url_row() -> None:
    html = _index_html()
    assert 'id="discover-btn"' in html
    # 画面分析ボタンがURL入力と同じ input-row 内にあること
    assert 'id="url-input"' in html.split('id="discover-btn"')[0].split('class="input-row"')[-1]


def test_single_mode_is_removed() -> None:
    assert 'value="single"' not in _index_html()


def test_manual_mode_is_removed() -> None:
    # クロールウィザードのmanualモードが除去されていることを確認する。
    # 観点管理フィルタの value="manual" は許容されるため、viewpoints セクション外を検査する。
    html = _index_html()
    wizard_section = html.split('id="view-viewpoints"')[0] if 'id="view-viewpoints"' in html else html
    assert 'value="manual"' not in wizard_section


def test_removed_qa_views_are_not_exposed() -> None:
    html = _index_html()
    assert 'data-view="qa-process"' not in html
    assert 'id="view-qa-process"' not in html
    assert 'data-view="qa-models"' not in html
    assert 'id="view-qa-models"' not in html
    assert 'data-view="qa-automation"' not in html
    assert 'id="view-qa-automation"' not in html
    assert "qa-process.js" not in html
    assert 'data-view="qa-quality"' in html
    assert 'id="view-qa-quality"' in html


def test_user_guide_view_is_present() -> None:
    html = _index_html()
    assert 'data-view="user-guide"' in html
    assert 'id="view-user-guide"' in html
    assert "WebSpec2Doc ユーザーガイド" in html


def test_execution_progress_details_are_present() -> None:
    html = _index_html()
    for element_id in ("exec-count", "exec-eta", "exec-skipped", "exec-saved"):
        assert f'id="{element_id}"' in html


def test_discover_to_crawl_flow(tmp_path: Path, monkeypatch) -> None:
    _patch_output_dirs(tmp_path, monkeypatch)
    _write_report_files(tmp_path)
    popen_calls = []

    monkeypatch.setattr(
        discover_mod.subprocess, "run", lambda *args, **kwargs: _Proc(_discover_payload())
    )

    def fake_popen(cmd, *args, **kwargs):
        proc = _Popen(cmd, *args, **kwargs)
        popen_calls.append(cmd)
        return proc

    monkeypatch.setattr(crawl_mod.subprocess, "Popen", fake_popen)

    discover_res = _client().post("/api/discover", data={"url": "https://example.com"})
    pages = discover_res.get_json()["pages"]
    assert discover_res.status_code == 200
    assert [page["url"] for page in pages] == ["https://example.com/"]

    run_res = _client().post(
        "/run",
        data={"urls": ",".join(page["url"] for page in pages), "format": "md,html"},
    )
    assert run_res.is_streamed
    stream = run_res.get_data(as_text=True)

    assert run_res.mimetype == "text/plain"
    assert "RUN_ID:" in stream
    assert "REPORT_PATH:" in stream
    assert "--format" in popen_calls[0]
    assert "md,html,json" in popen_calls[0]
    assert "--parallelism" in popen_calls[0]
    assert popen_calls[0][popen_calls[0].index("--parallelism") + 1] == "2"


def test_discover_no_login_to_result(tmp_path: Path, monkeypatch) -> None:
    _patch_output_dirs(tmp_path, monkeypatch)
    _write_report_files(tmp_path)

    monkeypatch.setattr(
        discover_mod.subprocess, "run", lambda *args, **kwargs: _Proc(_discover_payload())
    )
    monkeypatch.setattr(crawl_mod.subprocess, "Popen", _Popen)

    discover_data = _client().post("/api/discover", data={"url": "https://example.com"}).get_json()
    urls = [page["url"] for page in discover_data["pages"]]

    run_stream = _client().post("/run", data={"urls": ",".join(urls), "format": "md,html"})
    assert "REPORT_PATH:" in run_stream.get_data(as_text=True)

    result_res = _client().get("/api/result?domain=example.com")
    result = result_res.get_json()
    assert result_res.status_code == 200
    assert result["summary"]["screens"] == 1
    assert result["files"]["html"].endswith("report.html")
    assert result["files"]["json"].endswith("report.json")


def test_discover_with_login_to_crawl(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _patch_output_dirs(tmp_path, monkeypatch)
    _write_report_files(tmp_path)
    popen_calls = []

    def fake_run(cmd, *args, **kwargs):
        if "--discover" in cmd:
            return _Proc(_discover_payload(login_required=True))
        if "--login-simple" in cmd:
            return _Proc(
                json.dumps(
                    {
                        "success": True,
                        "needs_more_fields": False,
                        "fields": [],
                        "current_url": "https://example.com/",
                        "error": "",
                    }
                )
            )
        raise AssertionError(f"unexpected subprocess.run command: {cmd}")

    def fake_popen(cmd, *args, **kwargs):
        proc = _Popen(cmd, *args, **kwargs)
        popen_calls.append(cmd)
        return proc

    monkeypatch.setattr(discover_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(crawl_mod.subprocess, "Popen", fake_popen)

    discover_data = _client().post("/api/discover", data={"url": "https://example.com"}).get_json()
    assert discover_data["pages"][0]["login_required"] is True

    login_data = (
        _client()
        .post(
            "/api/login/simple",
            data={
                "domain": "example.com",
                "login_url": "https://example.com/login",
                "username": "user",
                "password": "pass",
            },
        )
        .get_json()
    )
    assert login_data["success"] is True
    auth_path = Path(login_data["auth_path"])
    auth_path.write_text("{}", encoding="utf-8")

    run_stream = (
        _client()
        .post(
            "/run",
            data={
                "urls": discover_data["pages"][0]["url"],
                "format": "md,html",
                "auth": str(auth_path),
            },
        )
        .get_data(as_text=True)
    )

    assert "RUN_ID:" in run_stream
    assert "--auth" in popen_calls[0]
    assert str(auth_path) in popen_calls[0]


def test_result_api_returns_expected_structure(tmp_path: Path, monkeypatch) -> None:
    _patch_output_dirs(tmp_path, monkeypatch)
    _write_report_files(tmp_path)

    res = _client().get("/api/result?domain=example.com")
    data = res.get_json()

    assert res.status_code == 200
    assert {"files", "summary", "screenshots"} <= set(data)
    assert data["summary"] == {"screens": 1, "forms": 0, "fields": 0, "buttons": 0}
    assert data["files"]["json"].endswith("report.json")
