"""web/services/qa/markdown_lite.py のユニットテスト。

static/js/markdown-lite.js のサーバーサイド移植版。QAレポート内のMarkdown文書を
生の `<pre>` テキストではなく構造化HTMLへ変換するために使う。
"""

from __future__ import annotations

from web.services.qa.markdown_lite import render_markdown_lite


class TestHeadings:
    def test_h1_and_h2(self) -> None:
        html_doc = render_markdown_lite("# タイトル\n\n## サブ見出し\n")
        assert '<h1 class="md-h1">タイトル</h1>' in html_doc
        assert '<h2 class="md-h2">サブ見出し</h2>' in html_doc


class TestInline:
    def test_bold_italic_code(self) -> None:
        html_doc = render_markdown_lite("**太字** と *斜体* と `code`")
        assert "<strong>太字</strong>" in html_doc
        assert "<em>斜体</em>" in html_doc
        assert "<code>code</code>" in html_doc

    def test_link_only_http_scheme(self) -> None:
        html_doc = render_markdown_lite("[example](https://example.com/)")
        assert (
            '<a href="https://example.com/" target="_blank" rel="noopener noreferrer">example</a>'
            in html_doc
        )


class TestLists:
    def test_unordered_list(self) -> None:
        html_doc = render_markdown_lite("- a\n- b\n")
        assert "<ul>" in html_doc
        assert "<li>a</li>" in html_doc
        assert "<li>b</li>" in html_doc
        assert "</ul>" in html_doc

    def test_ordered_list(self) -> None:
        html_doc = render_markdown_lite("1. a\n2. b\n")
        assert "<ol>" in html_doc
        assert "<li>a</li>" in html_doc
        assert "<li>b</li>" in html_doc
        assert "</ol>" in html_doc


class TestTable:
    def test_table_with_header_and_rows(self) -> None:
        md = "| A | B |\n|---|---|\n| 1 | 2 |\n"
        html_doc = render_markdown_lite(md)
        assert '<table class="md-table">' in html_doc
        assert "<th>A</th>" in html_doc
        assert "<th>B</th>" in html_doc
        assert "<td>1</td>" in html_doc
        assert "<td>2</td>" in html_doc


class TestCodeBlock:
    def test_fenced_code_block_preserved(self) -> None:
        md = "```\nline1\nline2\n```"
        html_doc = render_markdown_lite(md)
        assert '<pre class="md-code"><code>line1\nline2</code></pre>' in html_doc


class TestParagraph:
    def test_plain_text_becomes_paragraph(self) -> None:
        html_doc = render_markdown_lite("これは段落です。")
        assert "<p>これは段落です。</p>" in html_doc


class TestSecurity:
    def test_html_in_source_is_escaped_not_rendered(self) -> None:
        """入力由来のタグは決して出現しない（先にエスケープしてから自前タグのみ挿入）。"""
        html_doc = render_markdown_lite("<script>alert(1)</script>")
        assert "<script>" not in html_doc
        assert "&lt;script&gt;" in html_doc

    def test_non_http_link_scheme_not_rendered_as_link(self) -> None:
        html_doc = render_markdown_lite("[click](javascript:alert(1))")
        assert "<a href=" not in html_doc
