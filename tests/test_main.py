"""main.py のユニットテスト"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from unittest.mock import patch

import networkx as nx

from analyzer.form_analyzer import summarize_forms
from analyzer.html_analyzer import analyze_pages
from graph.transition_graph import build_graph
from main import (
    _domain_name,
    _parse_formats,
    _parse_url_list,
    parse_args,
    run,
    save_outputs,
)

# ---------- _parse_formats ----------


class TestParseFormats:
    def test_single_format(self) -> None:
        assert _parse_formats("md") == ("md",)

    def test_multiple_formats(self) -> None:
        result = _parse_formats("md,html,excel")
        assert set(result) == {"md", "html", "excel"}

    def test_unknown_format_excluded(self) -> None:
        result = _parse_formats("md,unknown")
        assert "unknown" not in result
        assert "md" in result

    def test_whitespace_stripped(self) -> None:
        result = _parse_formats(" md , html ")
        assert set(result) == {"md", "html"}

    def test_empty_string_returns_empty(self) -> None:
        assert _parse_formats("") == ()

    def test_case_insensitive(self) -> None:
        result = _parse_formats("MD,HTML")
        assert "md" in result
        assert "html" in result

    def test_all_unknown_returns_empty(self) -> None:
        assert _parse_formats("foo,bar") == ()


# ---------- _parse_url_list ----------


class TestParseUrlList:
    def test_none_returns_empty(self) -> None:
        assert _parse_url_list(None) == []

    def test_empty_returns_empty(self) -> None:
        assert _parse_url_list("") == []

    def test_splits_on_comma(self) -> None:
        result = _parse_url_list("https://a.com/,https://a.com/x")
        assert result == ["https://a.com/", "https://a.com/x"]

    def test_strips_whitespace(self) -> None:
        result = _parse_url_list(" https://a.com/ , https://a.com/x ")
        assert result == ["https://a.com/", "https://a.com/x"]

    def test_dedupes_preserving_order(self) -> None:
        result = _parse_url_list("https://a.com/,https://a.com/,https://a.com/x")
        assert result == ["https://a.com/", "https://a.com/x"]

    def test_ignores_blank_segments(self) -> None:
        result = _parse_url_list("https://a.com/,,  ,https://a.com/x")
        assert result == ["https://a.com/", "https://a.com/x"]


# ---------- _domain_name ----------


class TestDomainName:
    def test_standard_url(self) -> None:
        assert _domain_name("https://example.com/path") == "example.com"

    def test_url_with_port(self) -> None:
        assert _domain_name("https://example.com:8080/") == "example.com:8080"

    def test_empty_url_fallback(self) -> None:
        assert _domain_name("") == "site"

    def test_bare_path_replaces_slash(self) -> None:
        result = _domain_name("/some/path")
        assert "/" not in result or result == "site"

    def test_root_url(self) -> None:
        assert _domain_name("https://example.com/") == "example.com"


# ---------- generate_html_report ----------


class TestHtmlReport:
    def _make_report(self, page_top) -> str:
        from generator.html_reporter import generate_html_report

        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        summary = summarize_forms(analyzed)
        mermaid = 'graph LR\n  P001["P001"]'
        return generate_html_report(analyzed, graph, summary, page_top.url, mermaid)

    def test_contains_doctype(self, page_top) -> None:
        result = self._make_report(page_top)
        assert "<!doctype html>" in result

    def test_ends_with_html_close_tag(self, page_top) -> None:
        result = self._make_report(page_top)
        assert result.endswith("</html>")

    def test_contains_target_url(self, page_top) -> None:
        result = self._make_report(page_top)
        assert "example.com" in result

    def test_contains_page_id(self, page_top) -> None:
        result = self._make_report(page_top)
        assert "P001" in result

    def test_escapes_xss(self, page_top) -> None:
        from crawler.page_crawler import PageData

        page = PageData(
            url="https://example.com/",
            title='<script>alert("xss")</script>',
            headings=(),
            links=(),
            forms=(),
            screenshot_path=None,
        )
        analyzed = analyze_pages([page])
        graph = build_graph(analyzed)
        from generator.html_reporter import generate_html_report

        result = generate_html_report(analyzed, graph, [], page.url, "graph LR")
        assert "<script>alert" not in result


# ---------- parse_args ----------


class TestParseArgs:
    def test_no_url_does_not_raise(self) -> None:
        # --login を代替手段として追加したため --url は必須ではない
        with patch("sys.argv", ["main.py"]):
            args = parse_args()
            assert args.url is None
            assert args.login is None

    def test_url_parsed(self) -> None:
        with patch("sys.argv", ["main.py", "--url", "https://example.com"]):
            args = parse_args()
            assert args.url == "https://example.com"

    def test_default_depth(self) -> None:
        with patch("sys.argv", ["main.py", "--url", "https://example.com"]):
            args = parse_args()
            assert args.depth == 3

    def test_default_max_pages(self) -> None:
        with patch("sys.argv", ["main.py", "--url", "https://example.com"]):
            args = parse_args()
            assert args.max_pages == 50

    def test_custom_depth(self) -> None:
        with patch("sys.argv", ["main.py", "--url", "https://example.com", "--depth", "2"]):
            args = parse_args()
            assert args.depth == 2

    def test_llm_flag_defaults_false(self) -> None:
        with patch("sys.argv", ["main.py", "--url", "https://example.com"]):
            args = parse_args()
            assert args.llm is False

    def test_llm_flag_set(self) -> None:
        with patch("sys.argv", ["main.py", "--url", "https://example.com", "--llm"]):
            args = parse_args()
            assert args.llm is True


# ---------- save_outputs ----------


class TestSaveOutputs:
    def test_creates_md_files(self, tmp_path: Path, page_top) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        summary = summarize_forms(analyzed)

        save_outputs(analyzed, graph, summary, tmp_path, ("md",))

        assert (tmp_path / "screens.md").exists()
        assert (tmp_path / "forms.md").exists()
        assert (tmp_path / "transition.mmd").exists()

    def test_creates_html_report(self, tmp_path: Path, page_top) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        summary = summarize_forms(analyzed)

        save_outputs(analyzed, graph, summary, tmp_path, ("md", "html"))

        assert (tmp_path / "report.html").exists()

    def test_creates_excel_file(self, tmp_path: Path, page_top) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        summary = summarize_forms(analyzed)

        save_outputs(analyzed, graph, summary, tmp_path, ("excel",))

        assert (tmp_path / "spec.xlsx").exists()

    def test_no_html_without_html_format(self, tmp_path: Path, page_top) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        summary = summarize_forms(analyzed)

        save_outputs(analyzed, graph, summary, tmp_path, ("md",))

        assert not (tmp_path / "report.html").exists()

    def test_no_excel_without_excel_format(self, tmp_path: Path, page_top) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        summary = summarize_forms(analyzed)

        save_outputs(analyzed, graph, summary, tmp_path, ("md",))

        assert not (tmp_path / "spec.xlsx").exists()

    def test_empty_pages(self, tmp_path: Path) -> None:
        save_outputs([], nx.DiGraph(), [], tmp_path, ("md",))
        assert (tmp_path / "screens.md").exists()

    def test_creates_output_dir(self, tmp_path: Path, page_top) -> None:
        nested = tmp_path / "a" / "b"
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        save_outputs(analyzed, graph, [], nested, ("md",))
        assert nested.is_dir()

    def test_llm_insights_warning(self, tmp_path: Path, page_top, caplog) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)

        with caplog.at_level(logging.WARNING):
            save_outputs(analyzed, graph, [], tmp_path, ("md",), llm_insights={"data": 1})

        assert "llm_insights" in caplog.text


# ---------- run ----------


class TestRun:
    def test_run_creates_output_files(self, tmp_path: Path, page_top) -> None:
        args = argparse.Namespace(
            url="https://example.com/",
            depth=2,
            max_pages=10,
            output=tmp_path,
            llm=False,
            format="md",
        )
        with patch("main.crawl_site", return_value=[page_top]):
            run(args)

        output_dir = tmp_path / "example.com"
        assert (output_dir / "screens.md").exists()
        assert (output_dir / "forms.md").exists()

    def test_run_llm_flag_logs_warning(self, tmp_path: Path, page_top, caplog) -> None:
        args = argparse.Namespace(
            url="https://example.com/",
            depth=2,
            max_pages=10,
            output=tmp_path,
            llm=True,
            format="md",
        )
        with patch("main.crawl_site", return_value=[page_top]):
            with caplog.at_level(logging.WARNING):
                run(args)

        assert "llm" in caplog.text.lower() or "未実装" in caplog.text

    def test_run_empty_crawl(self, tmp_path: Path) -> None:
        args = argparse.Namespace(
            url="https://example.com/",
            depth=1,
            max_pages=5,
            output=tmp_path,
            llm=False,
            format="md",
        )
        with patch("main.crawl_site", return_value=[]):
            run(args)

        output_dir = tmp_path / "example.com"
        assert (output_dir / "screens.md").exists()
