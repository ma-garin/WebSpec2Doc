"""main.py — CLI モード・カバレッジ補完テスト"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from analyzer.form_analyzer import summarize_forms
from analyzer.html_analyzer import analyze_pages
from crawler.page_crawler import PageData
from graph.transition_graph import build_graph
from main import (
    _domain_name,
    _parse_formats,
    _parse_url_list,
    run,
    save_outputs,
)


def _fake_pages():
    return [
        PageData(
            url="https://example.com/",
            title="Top",
            headings=(),
            links=(),
            forms=(),
            screenshot_path=None,
        )
    ]


def _fake_analyzed_pages():
    return analyze_pages(_fake_pages())


def _fake_graph(analyzed):
    return build_graph(analyzed)


def test_parse_formats_requested_patterns() -> None:
    assert _parse_formats("md,html,excel") == ("md", "html", "excel")
    assert _parse_formats("pdf,json") == ("pdf", "json")
    assert _parse_formats("unknown") in {("md",), ()}


def test_domain_name_requested_patterns() -> None:
    assert _domain_name("https://example.com/path") == "example.com"
    assert _domain_name("https://sub.domain.co.jp") == "sub.domain.co.jp"


def test_parse_url_list_requested_patterns() -> None:
    assert _parse_url_list("https://a.com,https://b.com") == [
        "https://a.com",
        "https://b.com",
    ]
    assert _parse_url_list(None) == []
    assert _parse_url_list("") == []


def test_save_outputs_md_format_creates_markdown_files(tmp_path: Path) -> None:
    analyzed = _fake_analyzed_pages()
    graph = _fake_graph(analyzed)
    forms = summarize_forms(analyzed)

    save_outputs(analyzed, graph, forms, tmp_path, ("md",))

    assert (tmp_path / "screens.md").exists()
    assert (tmp_path / "forms.md").exists()
    assert (tmp_path / "transition.mmd").exists()


def test_save_outputs_html_format_creates_report(tmp_path: Path) -> None:
    analyzed = _fake_analyzed_pages()
    graph = _fake_graph(analyzed)
    forms = summarize_forms(analyzed)

    save_outputs(analyzed, graph, forms, tmp_path, ("html",))

    assert (tmp_path / "report.html").exists()


def test_save_outputs_json_format_creates_report(tmp_path: Path) -> None:
    analyzed = _fake_analyzed_pages()
    graph = _fake_graph(analyzed)
    forms = summarize_forms(analyzed)

    save_outputs(analyzed, graph, forms, tmp_path, ("json",))

    assert (tmp_path / "report.json").exists()


def test_save_outputs_excel_format_creates_workbook(tmp_path: Path) -> None:
    analyzed = _fake_analyzed_pages()
    graph = _fake_graph(analyzed)
    forms = summarize_forms(analyzed)

    save_outputs(analyzed, graph, forms, tmp_path, ("excel",))

    assert (tmp_path / "spec.xlsx").exists()


def test_scrape_login_success_outputs_json(capsys) -> None:
    from crawler.auto_login import LoginField, ScrapeResult
    from main import _scrape_login

    result = ScrapeResult(
        ok=True,
        fields=(
            LoginField(
                name="username",
                field_type="text",
                label="User",
                placeholder="ID",
                required=True,
                element_id="user",
            ),
        ),
        current_url="https://example.com/login",
        error="",
    )
    with patch("crawler.auto_login.scrape_login_fields", return_value=result):
        _scrape_login("https://example.com/login")

    import json

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["fields"][0]["name"] == "username"


def test_scrape_login_failure_result_outputs_json(capsys) -> None:
    from crawler.auto_login import ScrapeResult
    from main import _scrape_login

    result = ScrapeResult(
        ok=False,
        fields=(),
        current_url="https://example.com/login",
        error="boom",
    )
    with patch("crawler.auto_login.scrape_login_fields", return_value=result):
        _scrape_login("https://example.com/login")

    import json

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "boom"


def test_submit_login_simple_success_outputs_json(capsys, tmp_path: Path, monkeypatch) -> None:
    import io
    import json

    from crawler.auto_login import SubmitResult
    from main import _submit_login_simple

    args = argparse.Namespace(
        login_simple_url="https://example.com/login",
        auth=tmp_path / "auth.json",
    )
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"username": "alice", "password": "pw"})),
    )
    result = SubmitResult(
        success=True,
        needs_more_fields=False,
        fields=(),
        current_url="https://example.com/home",
        error="",
    )

    with patch("crawler.auto_login.submit_login_simple", return_value=result):
        _submit_login_simple(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True


def test_submit_login_simple_failure_outputs_json(capsys, tmp_path: Path, monkeypatch) -> None:
    import io
    import json

    from crawler.auto_login import SubmitResult
    from main import _submit_login_simple

    args = argparse.Namespace(
        login_simple_url="https://example.com/login",
        auth=tmp_path / "auth.json",
    )
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"username": "alice", "password": "bad"})),
    )
    result = SubmitResult(
        success=False,
        needs_more_fields=False,
        fields=(),
        current_url="https://example.com/login",
        error="認証に失敗しました",
    )

    with patch("crawler.auto_login.submit_login_simple", return_value=result):
        _submit_login_simple(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False


def test_submit_login_simple_missing_url_outputs_json(capsys, tmp_path: Path) -> None:
    import json

    from main import _submit_login_simple

    args = argparse.Namespace(login_simple_url=None, auth=tmp_path / "auth.json")

    _submit_login_simple(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert "error" in payload


def test_submit_login_simple_invalid_json_outputs_error(
    capsys, tmp_path: Path, monkeypatch
) -> None:
    import io
    import json

    from main import _submit_login_simple

    args = argparse.Namespace(
        login_simple_url="https://example.com/login",
        auth=tmp_path / "auth.json",
    )
    monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))

    _submit_login_simple(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert "JSON" in payload["error"]


def test_submit_login_outputs_success_json(capsys, tmp_path: Path, monkeypatch) -> None:
    import io
    import json

    from crawler.auto_login import SubmitResult
    from main import _submit_login

    args = argparse.Namespace(
        login_current_url="https://example.com/login",
        auth=tmp_path / "auth.json",
        login_temp_session=tmp_path / "temp.json",
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"code": "123456"})))
    result = SubmitResult(
        success=True,
        needs_more_fields=False,
        fields=(),
        current_url="https://example.com/home",
        error="",
    )

    with patch("crawler.auto_login.submit_login_form", return_value=result):
        _submit_login(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert payload["current_url"] == "https://example.com/home"


def test_submit_login_missing_url_outputs_error(capsys, tmp_path: Path) -> None:
    import json

    from main import _submit_login

    args = argparse.Namespace(
        login_current_url=None,
        auth=tmp_path / "auth.json",
        login_temp_session=None,
    )

    _submit_login(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert "error" in payload


def test_submit_login_invalid_json_outputs_error(capsys, tmp_path: Path, monkeypatch) -> None:
    import io
    import json

    from main import _submit_login

    args = argparse.Namespace(
        login_current_url="https://example.com/login",
        auth=tmp_path / "auth.json",
        login_temp_session=None,
    )
    monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))

    _submit_login(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert "JSON" in payload["error"]


def test_capture_login_without_signal_uses_capture_auth_state(tmp_path: Path) -> None:
    from main import _capture_login

    auth_path = tmp_path / "auth.json"
    with patch("main.capture_auth_state", return_value=auth_path) as capture:
        _capture_login("https://example.com/login", auth_path)

    capture.assert_called_once_with("https://example.com/login", auth_path)


def test_capture_login_with_signal_saves_auth_state(tmp_path: Path) -> None:
    from main import _capture_login

    auth_path = tmp_path / "auth.json"
    signal_path = tmp_path / "done.signal"
    with patch("crawler.auth.capture_auth_state_via_signal", return_value=auth_path) as capture:
        _capture_login("https://example.com/login", auth_path, signal_path)

    capture.assert_called_once_with("https://example.com/login", auth_path, signal_path)


def test_capture_login_signal_timeout_exits(tmp_path: Path) -> None:

    from main import _capture_login

    with patch("crawler.auth.capture_auth_state_via_signal", return_value=None):
        with pytest.raises(SystemExit) as exc_info:
            _capture_login(
                "https://example.com/login",
                tmp_path / "auth.json",
                tmp_path / "done.signal",
            )

    assert exc_info.value.code == 1


def test_discover_without_url_outputs_error(capsys) -> None:
    import json

    from main import _discover

    args = argparse.Namespace(url=None, depth=1, max_pages=2)

    _discover(args, None)

    payload = json.loads(capsys.readouterr().out)
    assert payload["pages"] == []
    assert "error" in payload


def test_discover_outputs_pages(capsys, tmp_path: Path) -> None:
    import json

    from main import _discover

    args = argparse.Namespace(url="https://example.com", depth=1, max_pages=2)
    pages = [{"url": "https://example.com", "title": "Top"}]

    with patch("main.discover_pages", return_value=pages) as discover:
        _discover(args, tmp_path / "auth.json")

    discover.assert_called_once()
    payload = json.loads(capsys.readouterr().out)
    assert payload["pages"] == pages


def test_save_diff_report_without_prior_logs_only(tmp_path: Path) -> None:
    from main import _save_diff_report

    _save_diff_report(None, tmp_path / "new.json", _fake_pages(), tmp_path, "https://example.com")

    assert not (tmp_path / "diff_report.html").exists()


def test_save_diff_report_writes_html(tmp_path: Path) -> None:
    from main import _save_diff_report

    prior = tmp_path / "old.json"
    new = tmp_path / "new.json"
    with (
        patch("main.load_snapshot", return_value=[]),
        patch("main.compute_diff", return_value={"changed": []}),
        patch("main.generate_diff_report", return_value="<html>diff</html>") as generate,
    ):
        _save_diff_report(prior, new, _fake_pages(), tmp_path, "https://example.com")

    generate.assert_called_once()
    assert (tmp_path / "diff_report.html").read_text(encoding="utf-8") == "<html>diff</html>"


def test_save_outputs_pdf_format_invokes_pdf_generator(tmp_path: Path) -> None:
    analyzed = _fake_analyzed_pages()
    graph = _fake_graph(analyzed)
    forms = summarize_forms(analyzed)

    with patch("generator.pdf_reporter.generate_pdf") as generate_pdf:
        save_outputs(analyzed, graph, forms, tmp_path, ("pdf",))

    generate_pdf.assert_called_once_with(tmp_path / "report.html", tmp_path / "report.pdf")
    assert (tmp_path / "report.html").exists()


def test_run_routes_login_modes_without_crawling() -> None:
    with patch("main._submit_login_simple") as submit_simple:
        run(argparse.Namespace(login_simple=True))
    submit_simple.assert_called_once()

    with patch("main._scrape_login") as scrape:
        run(argparse.Namespace(login_scrape="https://example.com/login"))
    scrape.assert_called_once_with("https://example.com/login")

    with patch("main._submit_login") as submit:
        run(argparse.Namespace(login_submit=True))
    submit.assert_called_once()

    with patch("main._capture_login") as capture:
        run(
            argparse.Namespace(
                login="https://example.com/login",
                auth=Path("auth.json"),
                login_signal=None,
            )
        )
    capture.assert_called_once()

    with patch("main._discover") as discover:
        run(argparse.Namespace(discover=True, auth=None))
    discover.assert_called_once()


def test_run_without_primary_url_logs_error(caplog) -> None:
    args = argparse.Namespace(
        url=None,
        urls=None,
        login=None,
        auth=None,
        login_signal=None,
        discover=False,
        login_simple=False,
        login_scrape=None,
        login_submit=False,
    )

    with caplog.at_level(logging.ERROR):
        run(args)

    assert "--url" in caplog.text


def test_run_urls_branch_and_compare(tmp_path: Path) -> None:
    args = argparse.Namespace(
        url=None,
        urls="https://example.com/,https://example.com/about",
        depth=1,
        max_pages=2,
        output=tmp_path,
        llm=False,
        format="md",
        compare=True,
        auth=tmp_path / "auth.json",
        login=None,
        login_signal=None,
        discover=False,
        login_simple=False,
        login_scrape=None,
        login_submit=False,
    )

    with (
        patch("main.latest_snapshot", return_value=tmp_path / "old.json"),
        patch("main.crawl_urls", return_value=_fake_pages()) as crawl_urls_mock,
        patch("main.save_snapshot", return_value=tmp_path / "new.json"),
        patch("main._save_diff_report") as diff_report,
    ):
        run(args)

    crawl_urls_mock.assert_called_once()
    diff_report.assert_called_once()


def test_run_session_expired_outputs_marker(tmp_path: Path, capsys) -> None:

    from crawler.session_guard import SessionExpiredError

    args = argparse.Namespace(
        url="https://example.com/",
        urls=None,
        depth=1,
        max_pages=2,
        output=tmp_path,
        llm=False,
        format="md",
        compare=False,
        auth=None,
        login=None,
        login_signal=None,
        discover=False,
        login_simple=False,
        login_scrape=None,
        login_submit=False,
    )

    with patch("main.crawl_site", side_effect=SessionExpiredError("expired")):
        with pytest.raises(SystemExit) as exc_info:
            run(args)

    assert exc_info.value.code == 2
    assert capsys.readouterr().out == "SESSION_EXPIRED\n"


def test_main_loads_env_and_runs_parsed_args() -> None:
    import main as main_module

    parsed = argparse.Namespace(url=None)
    with (
        patch("main.logging.basicConfig") as basic_config,
        patch("main.load_dotenv") as load_env,
        patch("main.parse_args", return_value=parsed),
        patch("main.run") as run_mock,
    ):
        main_module.main()

    basic_config.assert_called_once()
    load_env.assert_called_once()
    run_mock.assert_called_once_with(parsed)
